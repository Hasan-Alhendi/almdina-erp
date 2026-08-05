from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.drawing_action_policy import (
    DrawingActionDenied,
    DrawingActionState,
    required_upload_capability,
    validate_assigned_drawing_action,
    validate_plan_source,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def state(**overrides: str) -> DrawingActionState:
    values = {
        "status": "At Drawing",
        "production_path": "Drawing",
        "current_department": "رسم",
        "current_assignee": "designer@example.com",
        "session_user": "designer@example.com",
        "approved_plan": "",
        "production_dxf": "",
    }
    values.update(overrides)
    return DrawingActionState(**values)


class TestDrawingActionPolicy(unittest.TestCase):
    def test_assigned_designer_can_use_drawing_actions(self) -> None:
        validate_assigned_drawing_action(state())

    def test_unassigned_or_different_user_is_rejected(self) -> None:
        with self.assertRaisesRegex(DrawingActionDenied, "designer_not_assigned"):
            validate_assigned_drawing_action(state(current_assignee=""))
        with self.assertRaisesRegex(DrawingActionDenied, "not_assigned_designer"):
            validate_assigned_drawing_action(state(session_user="other@example.com"))

    def test_wrong_stage_and_locked_plan_are_rejected(self) -> None:
        with self.assertRaisesRegex(DrawingActionDenied, "not_at_drawing"):
            validate_assigned_drawing_action(
                state(status="At CNC", current_department="CNC")
            )
        with self.assertRaisesRegex(DrawingActionDenied, "plan_already_approved"):
            validate_assigned_drawing_action(state(approved_plan="CP-0001"))

    def test_upload_and_replace_have_distinct_capabilities(self) -> None:
        self.assertEqual(required_upload_capability(state()), Capability.UPLOAD_DXF)
        self.assertEqual(
            required_upload_capability(state(production_dxf="/private/files/a.dxf")),
            Capability.REPLACE_DXF,
        )

    def test_designer_can_approve_system_or_valid_custom_plan(self) -> None:
        self.assertEqual(
            validate_plan_source(
                "System",
                has_system_plan=True,
                has_custom_plan=False,
                has_production_dxf=False,
            ),
            "System",
        )
        self.assertEqual(
            validate_plan_source(
                "Custom",
                has_system_plan=True,
                has_custom_plan=True,
                has_production_dxf=True,
            ),
            "Custom",
        )

    def test_custom_approval_requires_both_imported_plan_and_dxf(self) -> None:
        for has_custom, has_dxf in ((False, False), (True, False), (False, True)):
            with self.subTest(has_custom=has_custom, has_dxf=has_dxf):
                with self.assertRaisesRegex(DrawingActionDenied, "custom_plan_missing"):
                    validate_plan_source(
                        "Custom",
                        has_system_plan=True,
                        has_custom_plan=has_custom,
                        has_production_dxf=has_dxf,
                    )


if __name__ == "__main__":
    unittest.main()
