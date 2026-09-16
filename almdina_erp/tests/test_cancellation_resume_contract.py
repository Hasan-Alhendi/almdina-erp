from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.orders.lifecycle_permissions import (
    OrderLifecycleAction,
    decide_lifecycle_action,
)
from almdina_erp.almdina_erp.application.security.cancellation_resume_migration import (
    resume_cancelled_state_updates,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "order_lifecycle_service.py"
DOCTYPE = (
    ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
)
PATCHES = ROOT / "patches.txt"
MIGRATION = (
    ROOT / "almdina_erp" / "application" / "security" / "cancellation_resume_migration.py"
)


class TestCancellationResumeContract(unittest.TestCase):
    def test_policy_allows_resume_only_when_cancelled(self) -> None:
        allowed = decide_lifecycle_action(
            action=OrderLifecycleAction.RESUME_CANCELLED,
            status="Cancelled",
            revision_state="Current",
            has_capability=True,
        )
        self.assertTrue(allowed.allowed)
        denied_capability = decide_lifecycle_action(
            action=OrderLifecycleAction.RESUME_CANCELLED,
            status="Cancelled",
            revision_state="Current",
            has_capability=False,
        )
        self.assertFalse(denied_capability.allowed)
        for status in ("Draft", "At CNC", "Ready for Delivery", "Delivered"):
            with self.subTest(status=status):
                decision = decide_lifecycle_action(
                    action=OrderLifecycleAction.RESUME_CANCELLED,
                    status=status,
                    revision_state="Current",
                    has_capability=True,
                )
                self.assertFalse(decision.allowed)

    def test_presentation_and_schema_are_hidden_and_non_financial(self) -> None:
        presentation = CAPABILITY_PRESENTATION[Capability.RESUME_CANCELLED_ORDER]
        self.assertEqual(presentation["label"], "استئناف الطلب الملغى")
        self.assertEqual(presentation["risk"], "critical")
        payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
        field = next(
            item
            for item in payload["fields"]
            if item["fieldname"] == "cancellation_snapshot"
        )
        self.assertEqual(field["fieldtype"], "JSON")
        self.assertEqual(field["hidden"], 1)
        self.assertEqual(field["read_only"], 1)
        self.assertEqual(field["no_copy"], 1)
        self.assertIn("cancellation_snapshot", payload["field_order"])

    def test_service_writes_snapshot_and_restores_without_reopen_reset(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        cancel_fn = source.split("def cancel_order", 1)[1].split(
            "def resume_cancelled_order", 1
        )[0]
        resume_fn = source.split("def resume_cancelled_order", 1)[1].split(
            "_IN_PLACE_DRAFT_FIELDS", 1
        )[0]
        self.assertIn("_cancellation_snapshot_for(order)", cancel_fn)
        self.assertIn("previous_status", source)
        self.assertIn("cancellation_snapshot", cancel_fn)
        self.assertIn("OrderLifecycleAction.RESUME_CANCELLED", resume_fn)
        self.assertIn("restore_cancelled_stage", resume_fn)
        self.assertIn("select_resume_plan", resume_fn)
        self.assertNotIn("Resume reason is required.", resume_fn)
        self.assertIn("lifecycle_context_for_order(order)", cancel_fn)
        self.assertIn("lifecycle_context_for_order(order)", resume_fn)
        self.assertNotIn("reopen_stage", source)
        self.assertIn('"cancellation_snapshot": None', source)

    def test_supervisor_migration_is_idempotent_and_role_name_free(self) -> None:
        migration = MIGRATION.read_text(encoding="utf-8")
        self.assertNotIn("Production Manager", migration)
        self.assertNotIn("System Manager", migration)
        states = {
            "Supervisor": {
                Capability.RETURN_ORDER_TO_DRAFT: True,
                Capability.RESUME_CANCELLED_ORDER: False,
            },
            "AlreadyGranted": {
                Capability.RETURN_ORDER_TO_DRAFT: True,
                Capability.RESUME_CANCELLED_ORDER: True,
            },
            "Clerk": {
                Capability.CANCEL_ORDER: True,
                Capability.RETURN_ORDER_TO_DRAFT: False,
                Capability.RESUME_CANCELLED_ORDER: False,
            },
        }
        updates = resume_cancelled_state_updates(states)
        self.assertEqual(set(updates), {"Supervisor"})
        self.assertTrue(updates["Supervisor"][Capability.RESUME_CANCELLED_ORDER])
        migrated = {role: dict(state) for role, state in states.items()}
        migrated.update(updates)
        self.assertEqual(resume_cancelled_state_updates(migrated), {})
        self.assertIn(
            "almdina_erp.patches.v1_0.grant_resume_cancelled_order_capability",
            PATCHES.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
