from __future__ import annotations

import unittest
from dataclasses import replace

from almdina_erp.almdina_erp.application.security.drawing_action_policy import (
    DrawingActionDenied,
    DrawingActionState,
    required_upload_capability,
    validate_assigned_drawing_action,
)
from almdina_erp.almdina_erp.application.shop_floor import commands
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.tests.test_stage14_end_to_end_regression import (
    StatefulFactoryRepository,
)


class TestStage14PreproductionRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = StatefulFactoryRepository()
        self.repository.orders["DCO-E2E-DRAFT"] = commands.OrderState(
            name="DCO-E2E-DRAFT",
            status="Draft",
            production_path=None,
            current_stage=None,
            has_cutting_plan=False,
            plan_needs_recalculation=False,
            has_approved_plan=False,
        )

    def test_new_draft_requires_a_valid_cutting_plan_before_production_dispatch(self) -> None:
        repository = self.repository
        repository.as_actor("supervisor@example.com")

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "احسب خطة القص"):
            commands.dispatch_order(
                repository,
                "DCO-E2E-DRAFT",
                "Drawing",
                "drawing@example.com",
            )
        self.assertIsNone(repository.orders["DCO-E2E-DRAFT"].current_stage)

        repository.orders["DCO-E2E-DRAFT"] = replace(
            repository.orders["DCO-E2E-DRAFT"],
            has_cutting_plan=True,
        )
        dispatched = commands.dispatch_order(
            repository,
            "DCO-E2E-DRAFT",
            "Drawing",
            "drawing@example.com",
        )

        drawing_stage = repository.stages[dispatched["stage"]]
        self.assertEqual(repository.orders["DCO-E2E-DRAFT"].status, "At Drawing")
        self.assertEqual(drawing_stage.stage_type, "Drawing")
        self.assertEqual(drawing_stage.assigned_to, "drawing@example.com")

    def test_dxf_actions_follow_current_drawing_assignment_not_role_name(self) -> None:
        repository = self.repository
        repository.orders["DCO-E2E-DRAFT"] = replace(
            repository.orders["DCO-E2E-DRAFT"],
            has_cutting_plan=True,
        )
        repository.as_actor("supervisor@example.com")
        dispatched = commands.dispatch_order(
            repository,
            "DCO-E2E-DRAFT",
            "Drawing",
            "drawing@example.com",
        )
        drawing_stage = repository.stages[dispatched["stage"]]
        order = repository.orders["DCO-E2E-DRAFT"]

        drawing_state = DrawingActionState(
            status=order.status,
            production_path=order.production_path or "",
            current_department=drawing_stage.department_label or "",
            current_assignee=drawing_stage.assigned_to or "",
            session_user="drawing@example.com",
            approved_plan="",
            production_dxf="",
        )
        validate_assigned_drawing_action(drawing_state)
        self.assertEqual(required_upload_capability(drawing_state), Capability.UPLOAD_DXF)
        self.assertIn(
            Capability.UPLOAD_DXF,
            repository.profiles["drawing@example.com"]["capabilities"],
        )
        self.assertNotIn(
            Capability.UPLOAD_DXF,
            repository.profiles["cnc@example.com"]["capabilities"],
        )

        with self.assertRaises(DrawingActionDenied) as denied:
            validate_assigned_drawing_action(
                replace(drawing_state, session_user="cnc@example.com")
            )
        self.assertEqual(denied.exception.code, "not_assigned_designer")

        replacement_state = replace(
            drawing_state,
            production_dxf="FILE-DXF-E2E",
        )
        self.assertEqual(
            required_upload_capability(replacement_state),
            Capability.REPLACE_DXF,
        )


if __name__ == "__main__":
    unittest.main()
