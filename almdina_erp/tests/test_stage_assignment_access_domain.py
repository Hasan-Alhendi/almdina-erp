from __future__ import annotations

import unittest
import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from almdina_erp.almdina_erp.domain.orders.stage_assignment_access import (
    decide_stage_assignment_access,
)


class TestStageAssignmentAccessDomain(unittest.TestCase):
    def test_administrator_bypasses_only_active_stage_assignment(self) -> None:
        decision = decide_stage_assignment_access(
            actor="Administrator",
            assigned_to="worker@example.com",
            has_current_stage=True,
            has_production_path=True,
            is_admin=True,
            order_status="At CNC",
        )
        self.assertTrue(decision.allowed)

        unassigned = decide_stage_assignment_access(
            actor="Administrator",
            assigned_to=None,
            has_current_stage=True,
            has_production_path=True,
            is_admin=True,
            order_status="At CNC",
        )
        self.assertTrue(unassigned.allowed)

    def test_admin_does_not_reopen_a_finished_route(self) -> None:
        decision = decide_stage_assignment_access(
            actor="Administrator",
            assigned_to=None,
            has_current_stage=False,
            has_production_path=True,
            is_admin=True,
            order_status="Ready for Delivery",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "no_active_stage")

    def test_employees_remain_bound_to_assignment(self) -> None:
        for actor, assignee, expected_code in (
            ("worker@example.com", "worker@example.com", "allowed"),
            ("worker@example.com", "other@example.com", "not_assigned"),
            ("worker@example.com", None, "stage_unassigned"),
        ):
            with self.subTest(assignee=assignee):
                decision = decide_stage_assignment_access(
                    actor=actor,
                    assigned_to=assignee,
                    has_current_stage=True,
                    has_production_path=True,
                )
                self.assertEqual(decision.code, expected_code)

    def test_start_records_administrator_without_assigning_the_stage_to_them(self) -> None:
        stage = types.SimpleNamespace(
            flags={},
            assigned_to="",
            assignment_time=None,
            creation=datetime(2026, 1, 1),
            save=lambda **kwargs: None,
        )
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.get_doc = lambda *args: stage
        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)
        fake_utils.now_datetime = lambda: datetime(2026, 1, 2)
        fake_utils.time_diff_in_seconds = lambda end, start: (end - start).total_seconds()
        path = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "production_stage_repository.py"
        )
        spec = importlib.util.spec_from_file_location("stage_repository_test_target", path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        with patch.dict(sys.modules, {"frappe": fake_frappe, "frappe.utils": fake_utils}):
            spec.loader.exec_module(module)
            module.start_stage(
                "PST-1",
                actor="Administrator",
                target_status="In Progress",
            )

        self.assertEqual(stage.assigned_to, "")
        self.assertEqual(stage.started_by, "Administrator")
        self.assertEqual(stage.status, "In Progress")
        self.assertIsNone(stage.assignment_time)


if __name__ == "__main__":
    unittest.main()
