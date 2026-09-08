from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.services import cutting_plan_command_service as command


class TestCuttingPlanRecalculationState(TestCase):
    @staticmethod
    def order(**overrides):
        values = {
            "name": "DCO-RECALC-001",
            "status": "Draft",
            "approved_plan": "",
            "current_production_stage": None,
            "production_path": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @patch.object(command, "require_stage_assignment_access")
    @patch.object(command, "user_can_recalculate_drawing_system_plan", return_value=True)
    def test_draft_with_approved_plan_and_planned_route_can_recalculate(
        self,
        _allowed,
        assignment,
    ) -> None:
        command._assert_recalculation_state(
            self.order(
                approved_plan="CP-0001",
                production_path="Drawing",
            )
        )
        assignment.assert_called_once()

    @patch.object(command, "require_stage_assignment_access")
    @patch.object(command, "user_can_recalculate_drawing_system_plan", return_value=False)
    def test_approved_plan_stays_locked_outside_draft_and_drawing(
        self,
        _denied,
        assignment,
    ) -> None:
        thrown = {}

        def throw(message, *args, **kwargs):
            thrown["message"] = str(message)
            raise frappe.ValidationError(message)

        with patch.object(command.frappe, "throw", side_effect=throw):
            with self.assertRaises(frappe.ValidationError):
                command._assert_recalculation_state(
                    self.order(
                        status="At CNC",
                        approved_plan="CP-0001",
                        current_production_stage="STAGE-CNC",
                        production_path="ROUTE-1",
                    )
                )
        self.assertIn(
            "خطة القص المعتمدة لا يمكن إعادة حسابها خارج مرحلة الرسم",
            thrown["message"],
        )
        assignment.assert_not_called()
