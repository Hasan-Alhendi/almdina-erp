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
    validate_temporary_password,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.workforce import (
    PROFILES,
    WorkforceAction,
    WorkforceFacts,
    decide_workforce_action,
    expand_workforce_capabilities,
    infer_profile,
)


class TestWorkforceAuthorization(unittest.TestCase):
    def test_legacy_manage_users_expands_to_every_workforce_action(self) -> None:
        expanded = expand_workforce_capabilities({Capability.MANAGE_USERS})
        for capability in (
            Capability.VIEW_USERS,
            Capability.CREATE_USERS,
            Capability.EDIT_USERS,
            Capability.ASSIGN_WORKFORCE_PROFILE,
            Capability.ENABLE_USERS,
            Capability.DISABLE_USERS,
            Capability.RESET_USER_PASSWORD,
        ):
            self.assertIn(capability, expanded)

    def test_permission_matrix_adds_view_dependency_and_legacy_expansion(self) -> None:
        granular = normalize_capability_state({Capability.DISABLE_USERS: True})
        self.assertTrue(granular[Capability.DISABLE_USERS])
        self.assertTrue(granular[Capability.VIEW_USERS])
        self.assertFalse(granular[Capability.CREATE_USERS])

        legacy = normalize_capability_state({Capability.MANAGE_USERS: True})
        self.assertTrue(legacy[Capability.VIEW_USERS])
        self.assertTrue(legacy[Capability.CREATE_USERS])
        self.assertTrue(legacy[Capability.RESET_USER_PASSWORD])

    def test_self_disable_and_active_assignments_are_blocked(self) -> None:
        self_disable = decide_workforce_action(
            {Capability.DISABLE_USERS},
            action=WorkforceAction.DISABLE,
            facts=WorkforceFacts(
                actor="manager@example.com",
                target_user="manager@example.com",
            ),
        )
        self.assertFalse(self_disable.allowed)
        self.assertEqual(self_disable.code, "self_disable")

        active = decide_workforce_action(
            {Capability.DISABLE_USERS},
            action=WorkforceAction.DISABLE,
            facts=WorkforceFacts(
                actor="manager@example.com",
                target_user="worker@example.com",
                active_assignments=2,
            ),
        )
        self.assertFalse(active.allowed)
        self.assertEqual(active.code, "active_assignments")

        profile_change = decide_workforce_action(
            {Capability.ASSIGN_WORKFORCE_PROFILE},
            action=WorkforceAction.ASSIGN_PROFILE,
            facts=WorkforceFacts(
                actor="manager@example.com",
                target_user="worker@example.com",
                active_assignments=1,
            ),
        )
        self.assertFalse(profile_change.allowed)
        self.assertEqual(profile_change.code, "active_assignments")

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
            facts=WorkforceFacts(
                actor="manager",
                target_user="outside@example.com",
                target_is_almdina=False,
            ),
        )
        self.assertEqual(external.code, "outside_scope")

    def test_profiles_are_operational_and_inferred_without_unrelated_roles(self) -> None:
        drawing = PROFILES["drawing_operator"]
        self.assertEqual(infer_profile((*drawing.roles, "Some Unrelated Role")), "drawing_operator")
        self.assertEqual(
            infer_profile(("عامل رسم", "عامل CNC")),
            "custom",
        )
        self.assertNotIn("approve_order", drawing.roles)

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
        self.assertEqual(
            validate_temporary_password("SecurePass123!", email=identity.email),
            "SecurePass123!",
        )
        with self.assertRaisesRegex(ValueError, "10 characters"):
            validate_temporary_password("Short1")
        with self.assertRaisesRegex(ValueError, "email name"):
            validate_temporary_password("WorkerSecure123", email=identity.email)

    def test_audit_snapshot_never_contains_password_material(self) -> None:
        snapshot = audit_snapshot(
            {
                "email": "worker@example.com",
                "first_name": "Worker",
                "enabled": True,
                "temporary_password": "NeverLog123",
                "new_password": "NeverLog456",
            }
        )
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
