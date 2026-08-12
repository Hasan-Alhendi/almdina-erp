from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_SETTINGS,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.application.security.workforce_management import (
    audit_snapshot,
    normalize_identity,
    normalize_role_selection,
    validate_temporary_password,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.workforce import (
    WorkforceAction,
    WorkforceFacts,
    decide_workforce_action,
)


class TestWorkforceAuthorization(unittest.TestCase):
    def test_granular_workforce_action_adds_view_dependency_only(self) -> None:
        state = normalize_capability_state({Capability.DISABLE_USERS: True})
        self.assertTrue(state[Capability.DISABLE_USERS])
        self.assertTrue(state[Capability.VIEW_USERS])
        self.assertFalse(state[Capability.CREATE_USERS])
        self.assertFalse(state[Capability.ASSIGN_USER_ROLES])

    def test_role_assignment_is_independent_capability(self) -> None:
        decision = decide_workforce_action(
            {Capability.CREATE_USERS},
            action=WorkforceAction.ASSIGN_ROLES,
            facts=WorkforceFacts(actor="manager@example.com", target_user="worker@example.com"),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "missing_capability")

    def test_self_role_change_and_active_assignments_are_blocked(self) -> None:
        self_change = decide_workforce_action(
            {Capability.ASSIGN_USER_ROLES},
            action=WorkforceAction.ASSIGN_ROLES,
            facts=WorkforceFacts(actor="manager@example.com", target_user="manager@example.com"),
        )
        self.assertEqual(self_change.code, "self_role_change")

        active = decide_workforce_action(
            {Capability.ASSIGN_USER_ROLES},
            action=WorkforceAction.ASSIGN_ROLES,
            facts=WorkforceFacts(actor="manager@example.com", target_user="worker@example.com", active_assignments=1),
        )
        self.assertEqual(active.code, "active_assignments")

    def test_self_disable_and_active_assignments_are_blocked(self) -> None:
        self_disable = decide_workforce_action(
            {Capability.DISABLE_USERS},
            action=WorkforceAction.DISABLE,
            facts=WorkforceFacts(actor="manager@example.com", target_user="manager@example.com"),
        )
        self.assertEqual(self_disable.code, "self_disable")

        active = decide_workforce_action(
            {Capability.DISABLE_USERS},
            action=WorkforceAction.DISABLE,
            facts=WorkforceFacts(actor="manager@example.com", target_user="worker@example.com", active_assignments=2),
        )
        self.assertEqual(active.code, "active_assignments")

    def test_protected_and_external_users_are_blocked(self) -> None:
        protected = decide_workforce_action(
            {Capability.EDIT_USERS},
            action=WorkforceAction.EDIT,
            facts=WorkforceFacts(actor="manager", target_user="Administrator"),
        )
        self.assertEqual(protected.code, "protected_user")

        external = decide_workforce_action(
            {Capability.RESET_USER_PASSWORD},
            action=WorkforceAction.RESET_PASSWORD,
            facts=WorkforceFacts(actor="manager", target_user="outside@example.com", target_is_almdina=False),
        )
        self.assertEqual(external.code, "outside_scope")

    def test_role_selection_is_normalized_without_profiles(self) -> None:
        self.assertEqual(normalize_role_selection(["عامل CNC", " عامل رسم ", "عامل CNC"]), ("عامل CNC", "عامل رسم"))
        with self.assertRaisesRegex(ValueError, "قائمة"):
            normalize_role_selection("عامل CNC")

    def test_identity_and_password_validation_are_deterministic(self) -> None:
        identity = normalize_identity(
            email="  Worker@Example.COM ",
            first_name="  محمد   أحمد ",
            last_name=" العامل ",
            language="ar",
        )
        self.assertEqual(identity.email, "worker@example.com")
        self.assertEqual(identity.first_name, "محمد أحمد")
        self.assertEqual(identity.last_name, "العامل")
        self.assertEqual(validate_temporary_password("SecurePass123!", email=identity.email), "SecurePass123!")
        with self.assertRaisesRegex(ValueError, "10"):
            validate_temporary_password("Short1")
        with self.assertRaisesRegex(ValueError, "اسم البريد الإلكتروني"):
            validate_temporary_password("WorkerSecure123", email=identity.email)

    def test_validation_messages_are_clear_arabic(self) -> None:
        checks = (
            lambda: normalize_identity(email="bad", first_name="محمد"),
            lambda: normalize_identity(email="worker@example.com", first_name=""),
            lambda: normalize_role_selection("عامل CNC"),
            lambda: validate_temporary_password("Short1"),
        )
        for operation in checks:
            with self.assertRaises(ValueError) as raised:
                operation()
            message = str(raised.exception)
            self.assertTrue(any("\u0600" <= char <= "\u06ff" for char in message), message)

    def test_audit_snapshot_never_contains_password_material(self) -> None:
        snapshot = audit_snapshot({
            "email": "worker@example.com",
            "first_name": "Worker",
            "enabled": True,
            "roles": ["عامل CNC"],
            "temporary_password": "NeverLog123",
            "new_password": "NeverLog456",
        })
        self.assertEqual(snapshot["roles"], ["عامل CNC"])
        self.assertNotIn("temporary_password", snapshot)
        self.assertNotIn("new_password", snapshot)
        self.assertNotIn("NeverLog", repr(snapshot))

    def test_workforce_grant_opens_settings_without_reports(self) -> None:
        navigation = build_navigation_context({Capability.VIEW_USERS})
        self.assertIn(WORKSPACE_SETTINGS, navigation["workspaces"])
        self.assertTrue(navigation["sections"]["workforce"])
        self.assertFalse(navigation["sections"]["reports"])


if __name__ == "__main__":
    unittest.main()
