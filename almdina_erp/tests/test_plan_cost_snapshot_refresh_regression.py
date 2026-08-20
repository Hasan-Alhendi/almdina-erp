from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_command_repository as repository_module
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_costing_workspace as workspace


class _Flags(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


class _Plan:
    def __init__(self, *, status: str = "Draft", wipe_protected_fields_on_save: bool = False):
        self.name = "CP-COST-REGRESSION-001"
        self.status = status
        self.flags = _Flags()
        self.cost_snapshot_version = workspace.COST_SNAPSHOT_VERSION
        self.board_rate_usd = 20
        self.cutting_cost_per_board_usd = 2
        self.mdf_cost_usd = 80
        self.cutting_cost_usd = 8
        self.edge_cost_usd = 5
        self.total_cost_usd = 93
        self._wipe_protected_fields_on_save = wipe_protected_fields_on_save

    def save(self) -> None:
        if not self._wipe_protected_fields_on_save:
            return
        # Reproduce the failure mode seen when Frappe restores permlevel-1
        # financial fields for a plan editor who is allowed to save geometry
        # but is not allowed to edit cost inputs.
        self.cost_snapshot_version = 0
        self.board_rate_usd = 0
        self.cutting_cost_per_board_usd = 0
        self.mdf_cost_usd = 0
        self.cutting_cost_usd = 0
        self.edge_cost_usd = 0
        self.total_cost_usd = 0

    def insert(self) -> None:
        self.save()


class TestPlanCostSnapshotRefreshRegression(unittest.TestCase):
    def test_server_snapshot_boundary_persists_all_protected_cost_fields(self) -> None:
        plan = _Plan()
        expected = {
            "cost_snapshot_version": workspace.COST_SNAPSHOT_VERSION,
            "board_rate_usd": 20.0,
            "cutting_cost_per_board_usd": 2.0,
            "mdf_cost_usd": 80.0,
            "cutting_cost_usd": 8.0,
            "edge_cost_usd": 5.0,
            "total_cost_usd": 93.0,
        }

        with patch.object(workspace.frappe.db, "set_value") as set_value:
            with patch.object(workspace.frappe.db, "get_value", return_value=expected):
                result = workspace.persist_plan_cost_snapshot(plan)

        set_value.assert_called_once_with(
            "Cutting Plan",
            plan.name,
            expected,
            update_modified=False,
        )
        self.assertEqual(result, expected)

    def test_server_snapshot_boundary_fails_closed_on_round_trip_mismatch(self) -> None:
        plan = _Plan()
        persisted = {
            "cost_snapshot_version": 0,
            "board_rate_usd": 20,
            "cutting_cost_per_board_usd": 2,
            "mdf_cost_usd": 80,
            "cutting_cost_usd": 8,
            "edge_cost_usd": 5,
            "total_cost_usd": 93,
        }

        with patch.object(workspace.frappe.db, "set_value"):
            with patch.object(workspace.frappe.db, "get_value", return_value=persisted):
                with self.assertRaises(frappe.ValidationError):
                    workspace.persist_plan_cost_snapshot(plan)

    def test_plan_repository_restores_trusted_snapshot_after_frappe_field_sanitization(self) -> None:
        plan = _Plan(wipe_protected_fields_on_save=True)
        snapshots: list[dict[str, float | int]] = []

        def capture(saved_plan) -> None:
            snapshots.append(
                {
                    "cost_snapshot_version": saved_plan.cost_snapshot_version,
                    **{
                        fieldname: getattr(saved_plan, fieldname)
                        for fieldname in workspace.PLAN_COST_FIELDS
                    },
                }
            )

        repository = repository_module.FrappeCuttingPlanCommandRepository(
            Capability.RECALCULATE_PLAN
        )
        with patch.object(repository_module, "persist_plan_cost_snapshot", side_effect=capture):
            repository.save_document(plan)

        self.assertEqual(
            snapshots,
            [
                {
                    "cost_snapshot_version": workspace.COST_SNAPSHOT_VERSION,
                    "board_rate_usd": 20.0,
                    "cutting_cost_per_board_usd": 2.0,
                    "mdf_cost_usd": 80.0,
                    "cutting_cost_usd": 8.0,
                    "edge_cost_usd": 5.0,
                    "total_cost_usd": 93.0,
                }
            ],
        )
        self.assertEqual(plan.cost_snapshot_version, workspace.COST_SNAPSHOT_VERSION)
        self.assertEqual(plan.total_cost_usd, 93.0)
        self.assertNotIn("almdina_cutting_plan_command_capability", plan.flags)

    def test_approved_status_transition_does_not_rewrite_financial_snapshot(self) -> None:
        plan = _Plan(status="Approved")
        repository = repository_module.FrappeCuttingPlanCommandRepository(
            Capability.APPROVE_DXF
        )

        with patch.object(repository_module, "persist_plan_cost_snapshot") as persist:
            repository.save_document(plan, allow_status_transition=True)

        persist.assert_not_called()
        self.assertNotIn("almdina_cutting_plan_command_capability", plan.flags)
        self.assertNotIn("allow_status_transition", plan.flags)


if __name__ == "__main__":
    unittest.main()
