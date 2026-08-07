from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


MANAGER_ROLE = "Almdina Workforce Manager Test"
VIEWER_ROLE = "Almdina Workforce Viewer Test"
WORKER_ROLE_A = "Almdina Workforce Worker A Test"
WORKER_ROLE_B = "Almdina Workforce Worker B Test"
MANAGER_USER = "almdina.workforce.manager@example.com"
VIEWER_USER = "almdina.workforce.viewer@example.com"
WORKER_USER = "almdina.workforce.worker@example.com"


class TestWorkforceManagementIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (MANAGER_ROLE, VIEWER_ROLE, WORKER_ROLE_A, WORKER_ROLE_B):
            cls._ensure_role(role)
        cls._ensure_user(MANAGER_USER, MANAGER_ROLE, almdina=True)
        cls._ensure_user(VIEWER_USER, VIEWER_ROLE)
        cls._replace_role_permissions(
            MANAGER_ROLE,
            {
                "read": 1,
                Capability.VIEW_USERS: 1,
                Capability.CREATE_USERS: 1,
                Capability.EDIT_USERS: 1,
                Capability.ASSIGN_USER_ROLES: 1,
                Capability.ENABLE_USERS: 1,
                Capability.DISABLE_USERS: 1,
                Capability.RESET_USER_PASSWORD: 1,
            },
        )
        cls._replace_role_permissions(
            VIEWER_ROLE,
            {"read": 1, Capability.VIEW_USERS: 1},
        )
        frappe.clear_cache()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "Almdina User Audit",
            {"target_user": ["in", [MANAGER_USER, VIEWER_USER, WORKER_USER]]},
        )
        for user in (WORKER_USER, MANAGER_USER, VIEWER_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in (MANAGER_ROLE, VIEWER_ROLE, WORKER_ROLE_A, WORKER_ROLE_B):
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
            ).insert(ignore_permissions=True)

    @classmethod
    def _ensure_user(cls, email: str, role: str, *, almdina: bool = False) -> None:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": role,
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
        roles = {row.role for row in (user.roles or [])}
        for required in ("Desk User", role):
            if required not in roles and frappe.db.exists("Role", required):
                user.append("roles", {"role": required})
        if almdina:
            user.default_app = "almdina_erp"
            user.default_workspace = "Almdina Settings"
        user.save(ignore_permissions=True)

    @classmethod
    def _replace_role_permissions(cls, role: str, values: dict[str, int]) -> None:
        frappe.db.delete(
            "Custom DocPerm",
            {
                "parent": "Almdina ERP Settings",
                "role": role,
                "permlevel": 0,
            },
        )
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Almdina ERP Settings",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                **values,
            }
        ).insert(ignore_permissions=True)

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina User Audit", {"target_user": WORKER_USER})
        if frappe.db.exists("User", WORKER_USER):
            frappe.delete_doc("User", WORKER_USER, force=True, ignore_permissions=True)
        frappe.clear_cache(user=MANAGER_USER)
        frappe.clear_cache(user=VIEWER_USER)
        frappe.clear_cache(doctype="Almdina ERP Settings")

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina User Audit", {"target_user": WORKER_USER})
        if frappe.db.exists("User", WORKER_USER):
            frappe.delete_doc("User", WORKER_USER, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def test_manager_can_run_full_workforce_lifecycle_with_direct_roles(self) -> None:
        from almdina_erp.almdina_erp.services.workforce_service import (
            create_workforce_user,
            get_workforce_console,
            reset_workforce_password,
            set_workforce_user_enabled,
            update_workforce_user,
        )

        frappe.set_user(MANAGER_USER)
        result = create_workforce_user(
            {
                "email": WORKER_USER,
                "first_name": "عامل",
                "last_name": "اختبار",
                "language": "ar",
                "roles": [WORKER_ROLE_A],
                "temporary_password": "SecureTemp123!",
            }
        )
        self.assertEqual(result["user"]["email"], WORKER_USER)
        self.assertEqual(result["user"]["roles"], [WORKER_ROLE_A])
        self.assertTrue(result["user"]["enabled"])

        roles = set(
            frappe.get_all(
                "Has Role",
                filters={"parent": WORKER_USER, "parenttype": "User"},
                pluck="role",
            )
        )
        self.assertIn(WORKER_ROLE_A, roles)
        self.assertNotIn(WORKER_ROLE_B, roles)

        updated = update_workforce_user(
            WORKER_USER,
            {
                "first_name": "عامل محدث",
                "roles": [WORKER_ROLE_B],
                "language": "ar",
            },
        )["user"]
        self.assertEqual(updated["roles"], [WORKER_ROLE_B])
        roles = set(
            frappe.get_all(
                "Has Role",
                filters={"parent": WORKER_USER, "parenttype": "User"},
                pluck="role",
            )
        )
        self.assertIn(WORKER_ROLE_B, roles)
        self.assertNotIn(WORKER_ROLE_A, roles)

        reset = reset_workforce_password(WORKER_USER, "AnotherSecure123!")
        self.assertFalse(reset["password_logged"])
        self.assertNotIn("AnotherSecure123", repr(reset))

        disabled = set_workforce_user_enabled(WORKER_USER, 0)["user"]
        self.assertFalse(disabled["enabled"])
        enabled = set_workforce_user_enabled(WORKER_USER, 1)["user"]
        self.assertTrue(enabled["enabled"])

        console = get_workforce_console(search=WORKER_USER)
        self.assertEqual(len(console["users"]), 1)
        self.assertEqual(console["users"][0]["email"], WORKER_USER)
        role_names = {row["name"] for row in console["roles"]}
        self.assertIn(WORKER_ROLE_A, role_names)
        self.assertIn(WORKER_ROLE_B, role_names)
        self.assertNotIn("System Manager", role_names)

        audits = frappe.get_all(
            "Almdina User Audit",
            filters={"target_user": WORKER_USER},
            fields=["action", "before_json", "after_json"],
        )
        actions = {row.action for row in audits}
        self.assertTrue(
            {"Created", "Identity Updated", "Roles Changed", "Password Reset", "Disabled", "Enabled"}.issubset(actions)
        )
        for row in audits:
            serialized = f"{row.before_json}\n{row.after_json}"
            self.assertNotIn("SecureTemp123", serialized)
            self.assertNotIn("AnotherSecure123", serialized)

    def test_viewer_can_list_but_cannot_create(self) -> None:
        from almdina_erp.almdina_erp.services.workforce_service import (
            create_workforce_user,
            get_workforce_console,
        )

        frappe.set_user(VIEWER_USER)
        self.assertIn("users", get_workforce_console())
        with self.assertRaises(frappe.PermissionError):
            create_workforce_user(
                {
                    "email": WORKER_USER,
                    "first_name": "Denied",
                    "roles": [WORKER_ROLE_A],
                    "temporary_password": "DeniedSecure123!",
                }
            )

    def test_workforce_capabilities_are_explicit_not_aggregate(self) -> None:
        frappe.set_user(VIEWER_USER)
        self.assertTrue(doctype_has_capability(Capability.VIEW_USERS))
        self.assertFalse(doctype_has_capability(Capability.CREATE_USERS))
        self.assertFalse(doctype_has_capability(Capability.ASSIGN_USER_ROLES))
        self.assertFalse(doctype_has_capability(Capability.DISABLE_USERS))

        frappe.set_user(MANAGER_USER)
        for capability in (
            Capability.VIEW_USERS,
            Capability.CREATE_USERS,
            Capability.EDIT_USERS,
            Capability.ASSIGN_USER_ROLES,
            Capability.ENABLE_USERS,
            Capability.DISABLE_USERS,
            Capability.RESET_USER_PASSWORD,
        ):
            self.assertTrue(doctype_has_capability(capability), capability)

    def test_manager_cannot_disable_own_account(self) -> None:
        from almdina_erp.almdina_erp.services.workforce_service import (
            set_workforce_user_enabled,
        )

        frappe.set_user(MANAGER_USER)
        with self.assertRaises(frappe.ValidationError):
            set_workforce_user_enabled(MANAGER_USER, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
