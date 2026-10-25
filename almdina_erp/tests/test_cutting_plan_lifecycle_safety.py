from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_runtime_repository as runtime
from almdina_erp.almdina_erp.services import dxf_export_service
from almdina_erp.almdina_erp.services import cutting_plan_fingerprint_audit as audit
from almdina_erp.almdina_erp.services import cutting_plan_workspace_query_service as workspace_query


def _plan(status: str, name: str = "CP-HISTORICAL") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        door_cutting_order="DCO-ANON-1",
        plan_kind="Order",
        source_type="System",
        status=status,
        snapshot_json="{}",
        input_fingerprint="verified",
        plan_needs_recalculation=0,
    )


class TestManufacturingLifecycleEligibility(TestCase):
    def _facts(self, plan: SimpleNamespace | None) -> runtime.ProductionPlanFacts:
        order = SimpleNamespace(name="DCO-ANON-1", approved_plan=None)

        def latest(_name: str, **filters):
            requested_status = filters.get("status")
            if requested_status == "Draft":
                return plan if plan and plan.status == "Draft" else None
            if requested_status == "Approved":
                return plan if plan and plan.status == "Approved" else None
            return plan

        with (
            patch.object(runtime, "approved_plan_for_order", return_value=None),
            patch.object(runtime, "latest_plan", side_effect=latest),
            patch.object(runtime, "_plan_is_stale", return_value=False),
        ):
            return runtime.production_plan_facts(order)

    def test_cancelled_superseded_and_detached_approved_are_not_production_candidates(self):
        for status in ("Cancelled", "Superseded", "Approved"):
            with self.subTest(status=status):
                facts = self._facts(_plan(status))
                self.assertIsNone(facts.plan_name)
                self.assertFalse(facts.has_cutting_plan)
                self.assertFalse(facts.has_approved_plan)
                action = decide_production_action(
                    "start_assigned_stage",
                    capabilities={"start_assigned_stage"},
                    facts=ProductionActionFacts(
                        order_status="At CNC",
                        production_path="dynamic-route",
                        current_stage_name="STAGE-1",
                        stage_name="STAGE-1",
                        stage_status="Pending",
                        assigned_to="Administrator",
                        actor="Administrator",
                        is_admin=True,
                        has_cutting_plan=facts.has_cutting_plan,
                        plan_needs_recalculation=facts.plan_needs_recalculation,
                    ),
                )
                self.assertFalse(action.allowed)

    def test_valid_draft_remains_a_candidate_under_existing_preapproval_policy(self):
        draft = _plan("Draft", "CP-DRAFT")
        facts = self._facts(draft)
        self.assertEqual("CP-DRAFT", facts.plan_name)
        self.assertTrue(facts.has_cutting_plan)
        self.assertFalse(facts.plan_needs_recalculation)
        self.assertFalse(facts.has_approved_plan)

    def test_exact_order_approved_relation_remains_the_approved_candidate(self):
        order = SimpleNamespace(name="DCO-ANON-1", approved_plan="CP-APPROVED")
        approved = _plan("Approved", "CP-APPROVED")
        with (
            patch.object(runtime, "approved_plan_for_order", return_value=approved),
            patch.object(runtime, "latest_plan", side_effect=AssertionError("fallback is not current approval")),
            patch.object(runtime, "_plan_is_stale", return_value=False),
        ):
            facts = runtime.production_plan_facts(order)
        self.assertEqual("CP-APPROVED", facts.plan_name)
        self.assertTrue(facts.has_approved_plan)

    def test_dynamic_routing_blocks_new_work_but_preserves_planning_and_running_work(self):
        capabilities = {
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
        }
        pending = ProductionActionFacts(
            order_status="At CNC",
            production_path="dynamic:planning>cnc",
            current_stage_name="STAGE-CNC",
            has_cutting_plan=False,
            plan_needs_recalculation=True,
            stage_name="STAGE-CNC",
            stage_type="manufacturing",
            stage_status="Pending",
            assigned_to="Administrator",
            actor="Administrator",
            is_admin=True,
        )
        for action in (Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE):
            with self.subTest(action=action):
                decision = decide_production_action(action, capabilities=capabilities, facts=pending)
                self.assertFalse(decision.allowed)
                self.assertEqual("production_plan_unverified", decision.code)

        planning = replace(
            pending,
            current_stage_name="STAGE-PLAN",
            stage_name="STAGE-PLAN",
            stage_type="Planning",
            stage_is_planning=True,
        )
        start = decide_production_action(
            Capability.START_ASSIGNED_STAGE, capabilities=capabilities, facts=planning
        )
        self.assertTrue(start.allowed)

        running = replace(
            pending,
            has_cutting_plan=True,
            plan_needs_recalculation=True,
            stage_status="In Progress",
        )
        finish = decide_production_action(
            Capability.HANDOFF_ASSIGNED_STAGE, capabilities=capabilities, facts=running
        )
        self.assertTrue(finish.allowed)

    def test_offcut_customer_only_plan_cannot_start_or_handoff_factory_work(self):
        facts = ProductionActionFacts(
            order_status="At CNC",
            production_path="dynamic:cnc",
            current_stage_name="STAGE-CNC",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_factory_work=False,
            stage_name="STAGE-CNC",
            stage_status="Pending",
            assigned_to="Administrator",
            actor="Administrator",
            is_admin=True,
        )
        for action in (Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE):
            with self.subTest(action=action):
                decision = decide_production_action(
                    action,
                    capabilities={Capability.START_ASSIGNED_STAGE, Capability.HANDOFF_ASSIGNED_STAGE},
                    facts=facts,
                )
                self.assertFalse(decision.allowed)
                self.assertEqual("customer_only_offcut", decision.code)

    def test_manufacturing_regeneration_rejects_history_but_keeps_current_draft(self):
        for status in ("Cancelled", "Superseded", "Approved"):
            with self.subTest(status=status), self.assertRaises(dxf_export_service.frappe.ValidationError):
                with (
                    patch.object(dxf_export_service, "_saved_plan_for_source", return_value=_plan(status)),
                    patch.object(dxf_export_service, "_", side_effect=lambda message: message),
                ):
                    dxf_export_service._required_saved_plan(
                        SimpleNamespace(name="DCO-ANON-1", approved_plan=None), "system"
                    )

        draft = _plan("Draft", "CP-CURRENT")
        with (
            patch.object(dxf_export_service, "_saved_plan_for_source", return_value=draft),
            patch.object(dxf_export_service, "_", side_effect=lambda message: message),
        ):
            self.assertIs(
                draft,
                dxf_export_service._required_saved_plan(
                    SimpleNamespace(name="DCO-ANON-1", approved_plan=None), "system"
                ),
            )

    def test_manufacturing_regeneration_allows_only_the_exact_linked_approval(self):
        approved = _plan("Approved", "CP-APPROVED")
        order = SimpleNamespace(name="DCO-ANON-1", approved_plan="CP-APPROVED")
        with patch.object(dxf_export_service, "_saved_plan_for_source", return_value=approved):
            self.assertIs(
                approved,
                dxf_export_service._required_saved_plan(order, "approved"),
            )

        detached = _plan("Approved", "CP-DETACHED")
        with (
            patch.object(dxf_export_service, "_saved_plan_for_source", return_value=detached),
            patch.object(dxf_export_service, "_", side_effect=lambda message: message),
            self.assertRaises(dxf_export_service.frappe.ValidationError),
        ):
            dxf_export_service._required_saved_plan(order, "system")

    def test_persisted_order_payload_cannot_use_editable_export_bypass(self):
        order = SimpleNamespace(name="DCO-ANON-1", approved_plan=None)
        with (
            patch.object(dxf_export_service, "_require_export_access", return_value=order),
            patch.object(
                dxf_export_service,
                "_required_saved_plan",
                side_effect=dxf_export_service.frappe.ValidationError("historical plan blocked"),
            ) as required,
            patch.object(
                dxf_export_service.legacy_export,
                "_strict_editable_snapshot",
                side_effect=AssertionError("persisted order payload reached editable export"),
            ),
        ):
            with self.assertRaisesRegex(
                dxf_export_service.frappe.ValidationError, "historical plan blocked"
            ):
                dxf_export_service.get_validated_dxf_plan(doc={"name": order.name})
        required.assert_called_once_with(order, None)

    def test_read_only_audit_covers_system_uploaded_and_lifecycle_candidates(self):
        order = SimpleNamespace(
            name="DCO-ANON-1",
            approved_plan="CP-APPROVED",
            status="Draft",
            doctype="Door Cutting Order",
            is_new=lambda: False,
            check_permission=lambda _permission: None,
        )
        rows = [
            {"name": "CP-DRAFT", "door_cutting_order": order.name, "revision": 3,
             "status": "Draft", "source_type": "System"},
            {"name": "CP-CANCELLED", "door_cutting_order": order.name, "revision": 2,
             "status": "Cancelled", "source_type": "Uploaded DXF"},
            {"name": "CP-APPROVED", "door_cutting_order": order.name, "revision": 1,
             "status": "Approved", "source_type": "System"},
        ]
        plans = {
            row["name"]: SimpleNamespace(
                input_fingerprint="fingerprint",
                plan_needs_recalculation=int(row["name"] == "CP-DRAFT"),
            )
            for row in rows
        }
        writes = []
        with (
            patch.object(audit.frappe, "get_list", side_effect=[rows, []], create=True),
            patch.object(
                audit.frappe,
                "get_doc",
                side_effect=lambda doctype, name: order if doctype == "Door Cutting Order" else plans[name],
                create=True,
            ),
            patch.object(audit.frappe.db, "set_value", side_effect=lambda *args, **kwargs: writes.append(args), create=True),
            patch.object(audit, "cutting_plan_capability_allowed", return_value=True),
            patch.object(
                audit,
                "plan_fingerprint_compatibility",
                return_value=SimpleNamespace(state="COMPATIBLE", reason="match", contract="v3"),
            ),
        ):
            result = audit.audit_cutting_plan_lifecycles()

        by_name = {row["plan"]: row for row in result}
        self.assertEqual("PERSISTED_STALE", by_name["CP-DRAFT"]["classification"])
        self.assertTrue(by_name["CP-DRAFT"]["manufacturing_candidate"])
        self.assertEqual("HISTORICAL_REVIEW_REQUIRED", by_name["CP-CANCELLED"]["classification"])
        self.assertFalse(by_name["CP-CANCELLED"]["manufacturing_candidate"])
        self.assertTrue(by_name["CP-APPROVED"]["current_approval"])
        self.assertTrue(by_name["CP-APPROVED"]["manufacturing_candidate"])
        self.assertEqual([], writes)

    def test_workspace_marks_historical_rows_without_hiding_their_geometry(self):
        order = SimpleNamespace(name="DCO-ANON-1", approved_plan="CP-CURRENT")
        base_row = {"validation": {"needs_recalculation": False}}
        compatibility = SimpleNamespace(
            state="MATCH", compatible=True, reason="match", contract="v3"
        )
        for status, name, expected in (
            ("Cancelled", "CP-CANCELLED", "historical"),
            ("Superseded", "CP-SUPERSEDED", "historical"),
            ("Approved", "CP-DETACHED", "historical"),
            ("Draft", "CP-DRAFT", "current_draft"),
            ("Approved", "CP-CURRENT", "current_approved"),
        ):
            plan = {"name": name, "status": status, "input_fingerprint": "fingerprint"}
            with (
                self.subTest(status=status, name=name),
                patch.object(workspace_query, "_plan_row", return_value=base_row.copy()),
                patch.object(workspace_query, "plan_fingerprint_compatibility", return_value=compatibility),
            ):
                row = workspace_query._plan_row_with_freshness(order, plan, "snapshot")
            self.assertEqual(expected, row["display_context"])
            self.assertIn("validation", row)
