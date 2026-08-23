from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_costing_workspace as workspace
from almdina_erp.almdina_erp.services import cost_permission_service as cost_service
from almdina_erp.almdina_erp.services import cutting_plan_command_service as plan_commands
from almdina_erp.almdina_erp.services import cutting_plan_cost_command_service as cost_commands


class TestA3PlanCostingOwnership(unittest.TestCase):
    def test_plan_cost_formula_uses_plan_geometry_and_rates(self) -> None:
        plan = SimpleNamespace(
            required_boards=3,
            board_rate_usd=10,
            cutting_cost_per_board_usd=2,
            edge_cost_usd=5,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            total_cost_usd=0,
            cost_snapshot_version=0,
        )

        result = workspace.apply_plan_costs(plan)

        self.assertEqual(result["mdf_cost_usd"], 30)
        self.assertEqual(result["cutting_cost_usd"], 6)
        self.assertEqual(result["edge_cost_usd"], 5)
        self.assertEqual(result["total_cost_usd"], 41)
        self.assertEqual(plan.cost_snapshot_version, workspace.COST_SNAPSHOT_VERSION)

    def test_focused_cost_edit_preserves_geometry_and_freshness(self) -> None:
        plan = SimpleNamespace(
            name="CP-A3-001",
            source_type="System",
            status="Draft",
            required_boards=2,
            board_rate_usd=5,
            cutting_cost_per_board_usd=1,
            mdf_cost_usd=10,
            cutting_cost_usd=2,
            edge_cost_usd=3,
            total_cost_usd=15,
            cost_snapshot_version=1,
            snapshot_json='{"sheets":[{"sheet_no":1}]}',
            input_fingerprint="geometry-fingerprint",
            metadata_fingerprint="metadata-fingerprint",
            validation_status="Valid",
            plan_needs_recalculation=0,
        )
        order = SimpleNamespace(name="DCO-A3-001", cutting_plan_source="System")
        saved: list[SimpleNamespace] = []

        class FakeRepository:
            def __init__(self, capability: str):
                self.capability = capability

            def ensure_system_draft(self, _order):
                return plan

            def ensure_uploaded_dxf_draft(self, _order):
                raise AssertionError("System order must not create a DXF draft")

            def save_document(self, saved_plan):
                saved.append(saved_plan)
                return saved_plan

        with patch.object(cost_commands, "require_cutting_plan_capability"):
            with patch.object(cost_commands, "current_working_plan", return_value=plan):
                with patch.object(cost_commands, "FrappeCuttingPlanCommandRepository", FakeRepository):
                    with patch.object(cost_commands, "initialize_draft_plan_cost_snapshot", return_value=False):
                        with patch.object(cost_commands, "refresh_order_commercial_totals"):
                            with patch.object(
                                cost_commands.frappe.db,
                                "get_value",
                                return_value={
                                    "board_rate_usd": 8,
                                    "cutting_cost_per_board_usd": 2,
                                },
                            ):
                                result = cost_commands.update_plan_cost_settings(
                                    order,
                                    board_rate_usd=8,
                                    cutting_cost_per_board_usd=2,
                                )

        self.assertEqual(len(saved), 1)
        self.assertEqual(plan.board_rate_usd, 8)
        self.assertEqual(plan.cutting_cost_per_board_usd, 2)
        self.assertEqual(plan.mdf_cost_usd, 16)
        self.assertEqual(plan.cutting_cost_usd, 4)
        self.assertEqual(plan.edge_cost_usd, 3)
        self.assertEqual(plan.total_cost_usd, 23)
        self.assertEqual(result["total_cost_usd"], 23)
        self.assertEqual(plan.snapshot_json, '{"sheets":[{"sheet_no":1}]}')
        self.assertEqual(plan.input_fingerprint, "geometry-fingerprint")
        self.assertEqual(plan.metadata_fingerprint, "metadata-fingerprint")
        self.assertEqual(plan.validation_status, "Valid")
        self.assertEqual(plan.plan_needs_recalculation, 0)

    def test_cost_edit_fails_closed_if_frappe_restores_old_permlevel_values(self) -> None:
        plan = SimpleNamespace(name="CP-A3-PERMLEVEL")

        with patch.object(
            cost_commands.frappe.db,
            "get_value",
            return_value={
                "board_rate_usd": 0,
                "cutting_cost_per_board_usd": 1,
            },
        ):
            with self.assertRaises(frappe.ValidationError):
                cost_commands._assert_cost_inputs_persisted(
                    plan,
                    board_rate_usd=22,
                    cutting_cost_per_board_usd=2.5,
                )

    def test_cost_save_response_uses_exact_saved_plan_revision(self) -> None:
        order = SimpleNamespace(
            name="DCO-A3-ROUNDTRIP",
            pieces=[],
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            edge_cost_usd=0,
            total_cost_usd=0,
            special_shapes_baseline_cost_usd=0,
            special_shapes_estimated_total_usd=0,
            special_shapes_final_total_usd=0,
            customer_quote_total_usd=0,
            customer_quote_status="",
            material_variance_cost_usd=0,
            internal_loss_cost_usd=0,
            actual_cost_usd=0,
        )
        saved_plan = SimpleNamespace(
            name="CP-A3-SAVED",
            status="Draft",
            cost_snapshot_version=workspace.COST_SNAPSHOT_VERSION,
            required_boards=2,
            board_rate_usd=22,
            cutting_cost_per_board_usd=2.5,
            mdf_cost_usd=44,
            cutting_cost_usd=5,
            edge_cost_usd=3,
            total_cost_usd=52,
        )

        payload = cost_service._cost_snapshot(order, plan=saved_plan)

        self.assertEqual(payload["cutting_plan"], "CP-A3-SAVED")
        self.assertEqual(payload["order"]["board_rate_usd"], 22)
        self.assertEqual(payload["order"]["cutting_cost_per_board_usd"], 2.5)
        self.assertEqual(payload["order"]["required_boards"], 2)
        self.assertEqual(payload["order"]["total_cost_usd"], 52)

    def test_legacy_draft_read_falls_back_without_mutating_it(self) -> None:
        order = SimpleNamespace(
            name="DCO-A3-002",
            board_rate_usd=12,
            cutting_cost_per_board_usd=3,
            mdf_cost_usd=24,
            cutting_cost_usd=6,
            edge_cost_usd=4,
            total_cost_usd=34,
        )
        legacy_draft = SimpleNamespace(
            status="Draft",
            cost_snapshot_version=0,
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            edge_cost_usd=0,
            total_cost_usd=0,
        )

        values = workspace.authoritative_cost_values(order, plan=legacy_draft)

        self.assertEqual(values["board_rate_usd"], 12)
        self.assertEqual(values["total_cost_usd"], 34)
        self.assertEqual(legacy_draft.cost_snapshot_version, 0)

    def test_legacy_approved_snapshot_remains_historical_authority(self) -> None:
        order = SimpleNamespace(
            name="DCO-A3-003",
            board_rate_usd=99,
            cutting_cost_per_board_usd=99,
            mdf_cost_usd=99,
            cutting_cost_usd=99,
            edge_cost_usd=99,
            total_cost_usd=99,
        )
        approved = SimpleNamespace(
            status="Approved",
            cost_snapshot_version=0,
            board_rate_usd=7,
            cutting_cost_per_board_usd=1,
            mdf_cost_usd=14,
            cutting_cost_usd=2,
            edge_cost_usd=3,
            total_cost_usd=19,
        )

        values = workspace.authoritative_cost_values(order, plan=approved)

        self.assertEqual(values["board_rate_usd"], 7)
        self.assertEqual(values["total_cost_usd"], 19)

    def test_approval_rejects_pre_a3_draft_cost_snapshot(self) -> None:
        order = SimpleNamespace(name="DCO-A3-004")
        plan = SimpleNamespace(
            status="Draft",
            validation_status="Valid",
            snapshot_json='{"validation":{"is_valid":true},"sheets":[{"sheet_no":1}]}',
            plan_needs_recalculation=0,
            cost_snapshot_version=0,
        )

        with self.assertRaises(frappe.ValidationError):
            plan_commands._assert_plan_ready_for_approval(order, plan)


if __name__ == "__main__":
    unittest.main()
