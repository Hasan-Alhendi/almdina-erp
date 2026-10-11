from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "services"
    / "order_edit_policy.py"
)


class FakeDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.stage_types: dict[str, str] = {}

    def get_value(self, *args: Any) -> str | None:
        self.calls.append(args)
        if len(args) >= 2:
            return self.stage_types.get(str(args[1]))
        return None


class AdapterHarness:
    def __init__(self, *, can_recalculate: bool = False) -> None:
        self.can_recalculate = can_recalculate
        self.capability_calls: list[tuple[str, str | None]] = []
        self.db = FakeDatabase()

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = self.db
        fake_frappe._ = lambda message: message

        def throw(message: str) -> None:
            raise RuntimeError(message)

        fake_frappe.throw = throw

        previous = sys.modules.get("frappe")
        sys.modules["frappe"] = fake_frappe
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_order_edit_policy_adapter_test",
                SERVICE_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load order edit policy adapter")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.doctype_has_capability = lambda capability, user=None: (
                self.capability_calls.append((capability, user))
                or self.can_recalculate
            )
            return module
        finally:
            if previous is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = previous


class TestOrderEditPolicyAdapter(unittest.TestCase):
    def test_editability_checks_are_draft_only(self) -> None:
        denied = AdapterHarness(can_recalculate=False)
        denied_policy = denied.load()

        self.assertTrue(denied_policy.user_can_edit_order("Draft"))
        self.assertFalse(denied_policy.user_can_edit_order("Rejected"))
        self.assertFalse(denied_policy.user_can_edit_order("Approved"))
        self.assertFalse(denied_policy.user_can_edit_order("At Drawing", "editor@example.com"))
        self.assertFalse(denied_policy.user_can_edit_order("Cutting In Progress", "worker@example.com"))
        self.assertFalse(denied_policy.user_can_edit_order("Delivered"))
        self.assertEqual(denied.capability_calls, [])

        allowed = AdapterHarness(can_recalculate=True)
        allowed_policy = allowed.load()
        self.assertTrue(allowed_policy.user_can_edit_order("Draft"))
        self.assertFalse(allowed_policy.user_can_edit_order("Approved"))
        self.assertFalse(allowed_policy.user_can_edit_order("At Drawing", "editor@example.com"))
        self.assertFalse(allowed_policy.user_can_edit_order("At Sharyoun", "editor@example.com"))
        self.assertFalse(allowed_policy.user_can_edit_order("At CNC", "editor@example.com"))
        self.assertFalse(allowed_policy.user_can_edit_order("Draft", revision_state="Superseded"))

    def test_active_dynamic_stage_blocks_edit_offer_and_ordinary_save_with_stale_draft_status(self) -> None:
        harness = AdapterHarness(can_recalculate=False)
        policy = harness.load()
        for stage_id in ("DYNAMIC-STAGE-ALPHA-9", "DYNAMIC-STAGE-OMEGA-27"):
            with self.subTest(stage_id=stage_id):
                self.assertFalse(policy.user_can_edit_order(
                    "Draft",
                    current_production_stage=stage_id,
                ))
                with self.assertRaises(RuntimeError):
                    policy.assert_order_editable({
                        "name": "DCO-TEST-1",
                        "status": "Draft",
                        "current_production_stage": stage_id,
                    })
                with self.assertRaises(RuntimeError):
                    policy.enforce_order_immutability_on_save(
                        types.SimpleNamespace(
                            status="Draft",
                            current_production_stage=stage_id,
                            revision_state="Current",
                            flags={},
                            is_new=lambda: False,
                        ),
                        {
                            "status": "Draft",
                            "current_production_stage": stage_id,
                            "revision_state": "Current",
                        },
                    )

    def test_ordinary_save_requires_both_persisted_and_proposed_states_pre_dispatch(self) -> None:
        policy = AdapterHarness().load()
        old_draft = {
            "name": "DCO-TEST-1",
            "status": "Draft",
            "current_production_stage": None,
            "revision_state": "Current",
        }

        route_only = types.SimpleNamespace(
            name="DCO-TEST-1",
            status="Draft",
            production_path="DYNAMIC-ROUTE-ALPHA",
            current_production_stage=None,
            revision_state="Current",
            flags={},
            is_new=lambda: False,
        )
        policy.enforce_order_immutability_on_save(route_only, old_draft)

        dispatched_proposal = types.SimpleNamespace(
            **{**route_only.__dict__, "current_production_stage": "DYNAMIC-STAGE-ALPHA-9"}
        )
        with self.assertRaises(RuntimeError):
            policy.enforce_order_immutability_on_save(dispatched_proposal, old_draft)

        dispatched_old = {
            **old_draft,
            "status": "In Production",
            "current_production_stage": "DYNAMIC-STAGE-OMEGA-27",
        }
        cleared_without_override = types.SimpleNamespace(
            **{**route_only.__dict__, "production_path": None}
        )
        with self.assertRaises(RuntimeError):
            policy.enforce_order_immutability_on_save(cleared_without_override, dispatched_old)

        superseded_old = {**old_draft, "revision_state": "Superseded"}
        with self.assertRaises(RuntimeError):
            policy.enforce_order_immutability_on_save(route_only, superseded_old)

    def test_allow_approved_edit_is_limited_to_the_cleared_return_to_draft_shape(self) -> None:
        policy = AdapterHarness().load()
        dispatched_old = {
            "name": "DCO-TEST-1",
            "status": "In Production",
            "production_path": "ROUTE-OLD",
            "current_department": "CUTTING",
            "current_assignee": "operator@example.test",
            "department_status": "Active",
            "current_production_stage": "DYNAMIC-STAGE-ALPHA-9",
            "approved_plan": "PLAN-1",
            "revision_state": "Current",
        }
        cleared_return = types.SimpleNamespace(
            name="DCO-TEST-1",
            status="Draft",
            production_path=None,
            current_department=None,
            current_assignee=None,
            department_status=None,
            current_production_stage=None,
            approved_plan=None,
            revision_state="Current",
            flags={"allow_approved_edit": True},
            is_new=lambda: False,
        )
        policy.enforce_order_immutability_on_save(cleared_return, dispatched_old)

        active_stage_return = types.SimpleNamespace(
            **{**cleared_return.__dict__, "current_production_stage": "DYNAMIC-STAGE-ALPHA-9"}
        )
        with self.assertRaises(RuntimeError):
            policy.enforce_order_immutability_on_save(active_stage_return, dispatched_old)

        uncleared_route = types.SimpleNamespace(
            **{**cleared_return.__dict__, "production_path": "ROUTE-RETAINED"}
        )
        with self.assertRaises(RuntimeError):
            policy.enforce_order_immutability_on_save(uncleared_route, dispatched_old)

    def test_capability_guarded_plan_recalculation_exception_remains_scoped(self) -> None:
        allowed_harness = AdapterHarness(can_recalculate=True)
        allowed_policy = allowed_harness.load()
        recalc_only = types.SimpleNamespace(
            name="DCO-PLAN-ONLY",
            status="Draft",
            current_production_stage="DYNAMIC-STAGE-ALPHA-9",
            production_path="Route A",
            approved_plan="PLAN-1",
            revision_state="Current",
            flags={"force_cutting_plan_recalculation": True},
            is_new=lambda: False,
        )
        allowed_policy.enforce_order_immutability_on_save(
            recalc_only,
            {
                "status": "Draft",
                "current_production_stage": "DYNAMIC-STAGE-ALPHA-9",
                "revision_state": "Current",
            },
        )

        denied_harness = AdapterHarness(can_recalculate=False)
        denied_policy = denied_harness.load()
        recalc_without_capability = types.SimpleNamespace(
            **{**recalc_only.__dict__, "flags": {"force_cutting_plan_recalculation": True}}
        )
        with self.assertRaises(RuntimeError):
            denied_policy.enforce_order_immutability_on_save(
                recalc_without_capability,
                {
                    "status": "Draft",
                    "current_production_stage": "DYNAMIC-STAGE-ALPHA-9",
                    "revision_state": "Current",
                },
            )

    def test_drawing_recalculation_permission_still_short_circuits_before_stage_lookup(self) -> None:
        denied = AdapterHarness(can_recalculate=False)
        denied_policy = denied.load()
        order = {
            "status": "Production In Progress",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": "PLAN-0001",
        }
        self.assertFalse(denied_policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(denied.db.calls, [])

    def test_approved_plan_can_prepare_replacement_at_explicit_drawing_status(self) -> None:
        harness = AdapterHarness(can_recalculate=True)
        policy = harness.load()
        order = {
            "status": "At Drawing",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": "PLAN-0001",
        }

        self.assertTrue(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(harness.db.calls, [])

    def test_draft_approved_plan_can_be_recalculated_before_dispatch(self) -> None:
        harness = AdapterHarness(can_recalculate=True)
        policy = harness.load()
        order = {
            "status": "Draft",
            "production_path": "Drawing",
            "current_production_stage": None,
            "approved_plan": "PLAN-0001",
        }

        self.assertTrue(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(harness.db.calls, [])

    def test_drawing_stage_fallback_reads_only_the_current_stage_type(self) -> None:
        harness = AdapterHarness(can_recalculate=True)
        harness.db.stage_types["STAGE-DRAWING"] = "Drawing"
        policy = harness.load()
        order = {
            "status": "Production In Progress",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": "PLAN-0001",
        }

        self.assertTrue(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(
            harness.db.calls,
            [("Production Stage", "STAGE-DRAWING", "stage_type")],
        )

    def test_non_drawing_stage_keeps_approved_plan_recalculation_closed(self) -> None:
        harness = AdapterHarness(can_recalculate=True)
        harness.db.stage_types["STAGE-CNC"] = "CNC"
        policy = harness.load()
        order = {
            "status": "At CNC",
            "production_path": "Production Route",
            "current_production_stage": "STAGE-CNC",
            "approved_plan": "PLAN-0001",
        }

        self.assertFalse(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(
            harness.db.calls,
            [("Production Stage", "STAGE-CNC", "stage_type")],
        )

    def test_explicit_at_drawing_status_avoids_database_lookup(self) -> None:
        harness = AdapterHarness(can_recalculate=True)
        policy = harness.load()
        order = {
            "status": "At Drawing",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": None,
        }

        self.assertTrue(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(harness.db.calls, [])


if __name__ == "__main__":
    unittest.main()
