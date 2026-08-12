from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.orders.lifecycle_permissions import (
    ACTION_CAPABILITIES,
    OrderLifecycleAction,
    build_lifecycle_context,
    decide_lifecycle_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    ROOT
    / "almdina_erp"
    / "application"
    / "orders"
    / "lifecycle_permissions.py"
)


class TestOrderLifecyclePermissions(unittest.TestCase):
    def test_policy_has_no_frappe_dependency(self) -> None:
        source = POLICY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("frappe.", source)

    def test_action_capabilities_are_explicit(self) -> None:
        self.assertEqual(
            ACTION_CAPABILITIES[OrderLifecycleAction.EDIT],
            Capability.EDIT_ORDER,
        )
        self.assertEqual(
            ACTION_CAPABILITIES[OrderLifecycleAction.SUBMIT_FOR_REVIEW],
            Capability.SUBMIT_ORDER,
        )
        self.assertEqual(
            ACTION_CAPABILITIES[OrderLifecycleAction.APPROVE],
            Capability.APPROVE_ORDER,
        )
        self.assertEqual(
            ACTION_CAPABILITIES[OrderLifecycleAction.CREATE_REVISION],
            Capability.CREATE_ORDER_REVISION,
        )
        self.assertEqual(
            ACTION_CAPABILITIES[OrderLifecycleAction.RETURN_TO_DRAFT],
            Capability.RETURN_ORDER_TO_DRAFT,
        )
        self.assertEqual(
            ACTION_CAPABILITIES[OrderLifecycleAction.CANCEL],
            Capability.CANCEL_ORDER,
        )

    def test_permission_is_required_before_state(self) -> None:
        decision = decide_lifecycle_action(
            action=OrderLifecycleAction.APPROVE,
            status="Pending Review",
            revision_state="Current",
            has_capability=False,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("permission", decision.reason.lower())

    def test_submit_and_approve_are_retired(self) -> None:
        for action, status in (
            (OrderLifecycleAction.SUBMIT_FOR_REVIEW, "Draft"),
            (OrderLifecycleAction.SUBMIT_FOR_REVIEW, "Rejected"),
            (OrderLifecycleAction.APPROVE, "Draft"),
            (OrderLifecycleAction.APPROVE, "Pending Review"),
            (OrderLifecycleAction.APPROVE, "Rejected"),
        ):
            with self.subTest(action=action, status=status):
                decision = decide_lifecycle_action(
                    action=action,
                    status=status,
                    revision_state="Current",
                    has_capability=True,
                )
                self.assertFalse(decision.allowed)
                self.assertIn("أُلغي", decision.reason)

    def test_revision_actions_remain_separate(self) -> None:
        self.assertTrue(
            decide_lifecycle_action(
                action=OrderLifecycleAction.CREATE_REVISION,
                status="Approved",
                revision_state="Current",
                has_capability=True,
            ).allowed
        )
        self.assertTrue(
            decide_lifecycle_action(
                action=OrderLifecycleAction.RETURN_TO_DRAFT,
                status="At CNC",
                revision_state="Current",
                has_capability=True,
            ).allowed
        )
        self.assertFalse(
            decide_lifecycle_action(
                action=OrderLifecycleAction.CREATE_REVISION,
                status="Draft",
                revision_state="Current",
                has_capability=True,
            ).allowed
        )
        self.assertTrue(
            decide_lifecycle_action(
                action=OrderLifecycleAction.EDIT,
                status="Draft",
                revision_state="Current",
                has_capability=True,
            ).allowed
        )
        for status in ("Rejected", "Approved", "At Drawing", "At Sharyoun", "At CNC", "Delivered"):
            with self.subTest(status=status):
                self.assertFalse(
                    decide_lifecycle_action(
                        action=OrderLifecycleAction.EDIT,
                        status=status,
                        revision_state="Current",
                        has_capability=True,
                    ).allowed
                )

    def test_terminal_and_historical_orders_are_locked(self) -> None:
        for action in ACTION_CAPABILITIES:
            with self.subTest(action=action):
                decision = decide_lifecycle_action(
                    action=action,
                    status="Approved",
                    revision_state="Superseded",
                    has_capability=True,
                )
                self.assertFalse(decision.allowed)

        for status in ("Delivered", "Completed", "Cancelled"):
            with self.subTest(status=status):
                self.assertFalse(
                    decide_lifecycle_action(
                        action=OrderLifecycleAction.CANCEL,
                        status=status,
                        revision_state="Current",
                        has_capability=True,
                    ).allowed
                )

    def test_context_is_complete_and_json_safe(self) -> None:
        context = build_lifecycle_context(
            status="Pending Review",
            revision_state="Current",
            capability_flags={
                Capability.EDIT_ORDER: True,
                Capability.APPROVE_ORDER: True,
            },
        )
        self.assertEqual(set(context["actions"]), set(ACTION_CAPABILITIES))
        self.assertFalse(context["editable"])
        self.assertFalse(context["actions"][OrderLifecycleAction.APPROVE]["allowed"])
        self.assertFalse(
            context["actions"][OrderLifecycleAction.CANCEL]["allowed"]
        )

        draft = build_lifecycle_context(
            status="Draft",
            revision_state="Current",
            capability_flags={Capability.EDIT_ORDER: True},
        )
        self.assertTrue(draft["editable"])


if __name__ == "__main__":
    unittest.main()
