from __future__ import annotations

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import sync_permission_types


MANAGER_ROLE = "Almdina Workforce Manager Test"
VIEWER_ROLE = "Almdina Workforce Viewer Test"
DRAWING_ROLE = "Almdina Drawing Worker Test"
CNC_ROLE = "Almdina CNC Worker Test"
UNRELATED_ROLE = "Almdina Workforce Unrelated Test"
MANAGER_USER = "almdina.workforce.manager@example.com"
VIEWER_USER = "almdina.workforce.viewer@example.com"
WORKER_USER = "almdina.workforce.worker@example.com"


class TestWorkforceManagementIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (MANAGER_ROLE, VIEWER_ROLE, DRAWING_ROLE, CNC_ROLE, UNRELATED_ROLE):
            cls._ensure_role(role)
        for role in (DRAWING_ROLE, CNC_ROLE):
            cls._ensure_managed_role(role)
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
        cls._replace_role_permissions(VIEWER_ROLE, {"read": 1, Capability.VIEW_USERS: 1})
        frappe.clear_cache()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina User Audit", {"target_user": ["in", [MANAGER_USER, VIEWER_USER, WORKER_USER]]})
        for user in (WORKER_USER, MANAGER_USER, VIEWER_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.delete("Almdina Role Metadata", {"role": ["in", [DRAWING_ROLE, CNC_ROLE]]})
        for role in (MANAGER_ROLE, VIEWER_ROLE, DRAWING_ROLE, CNC_ROLE, UNRELATED_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

    @classmethod
    def _ensure_managed_role(cls, role: str) -> None:
        if frappe.db.exists("Almdina Role Metadata", {"role": role}):
            return
        frappe.get_doc(
            {
                "doctype": "Almdina Role Metadata",
                "role": role,
                "role_uid": str(uuid.uuid4()),
                "description": "Integration-test managed role",
                "managed_by_almdina": 1,
            }
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
        if role not in {row.role for row in (user.roles or [])}:
            user.append("roles", {"role": role})
        if almdina:
            user.default_app = "almdina_erp"
            user.default_workspace = "Almdina Settings"
        user.save(ignore_permissions=True)

    @classmethod
    def _replace_role_permissions(cls, role: str, values: dict[str, int]) -> None:
        frappe.db.delete("Custom DocPerm", {"parent": "Almdina ERP Settings", "role": role, "permlevel": 0})
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

    def test_manager_can_run_multi_role_workforce_lifecycle(self) -> None:
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
                "roles": [DRAWING_ROLE, CNC_ROLE],
                "temporary_password": "SecureTemp123!",
            }
        )
        self.assertEqual(set(result["user"]["workforce_roles"]), {DRAWING_ROLE, CNC_ROLE})
        self.assertNotIn("profile", result["user"])

        frappe.set_user("Administrator")
        worker = frappe.get_doc("User", WORKER_USER)
        worker.append("roles", {"role": UNRELATED_ROLE})
        worker.save(ignore_permissions=True)
        frappe.clear_cache(user=WORKER_USER)

        frappe.set_user(MANAGER_USER)
        updated = update_workforce_user(
            WORKER_USER,
            {"first_name": "عامل CNC", "roles": [CNC_ROLE], "language": "ar"},
        )["user"]
        self.assertEqual(updated["workforce_roles"], [CNC_ROLE])
        self.assertNotIn("profile", updated)
        roles = set(frappe.get_all("Has Role", filters={"parent": WORKER_USER, "parenttype": "User"}, pluck="role"))
        self.assertIn(CNC_ROLE, roles)
        self.assertIn(UNRELATED_ROLE, roles)
        self.assertNotIn(DRAWING_ROLE, roles)

        reset = reset_workforce_password(WORKER_USER, "AnotherSecure123!")
        self.assertFalse(reset["password_logged"])
        disabled = set_workforce_user_enabled(WORKER_USER, 0)["user"]
        self.assertFalse(disabled["enabled"])
        self.assertTrue(set_workforce_user_enabled(WORKER_USER, 1)["user"]["enabled"])

        console = get_workforce_console(search=WORKER_USER)
        self.assertEqual(console["users"][0]["email"], WORKER_USER)
        self.assertNotIn("profiles", console)
        assignable = {role["name"] for role in console["roles"]}
        self.assertEqual(assignable, {DRAWING_ROLE, CNC_ROLE})

        audits = frappe.get_all("Almdina User Audit", filters={"target_user": WORKER_USER}, fields=["action", "before_json", "after_json"])
        actions = {row.action for row in audits}
        self.assertTrue({"Created", "Identity Updated", "Roles Changed", "Password Reset", "Disabled", "Enabled"}.issubset(actions))
        for row in audits:
            serialized = f"{row.before_json}\n{row.after_json}"
            self.assertNotIn("SecureTemp123", serialized)
            self.assertNotIn("AnotherSecure123", serialized)
            self.assertNotIn('"profile"', serialized)

    def test_role_selection_is_required_and_profile_payload_is_rejected(self) -> None:
        from almdina_erp.almdina_erp.services.workforce_service import create_workforce_user

        frappe.set_user(MANAGER_USER)
        for payload in (
            {"email": WORKER_USER, "first_name": "عامل", "temporary_password": "SecureTemp123!"},
            {"email": WORKER_USER, "first_name": "عامل", "profile": "drawing_operator", "temporary_password": "SecureTemp123!"},
        ):
            with self.assertRaises(frappe.ValidationError):
                create_workforce_user(payload)

    def test_viewer_can_list_but_cannot_create(self) -> None:
        from almdina_erp.almdina_erp.services.workforce_service import create_workforce_user, get_workforce_console

        frappe.set_user(VIEWER_USER)
        self.assertIn("users", get_workforce_console())
        with self.assertRaises(frappe.PermissionError):
            create_workforce_user(
                {
                    "email": WORKER_USER,
                    "first_name": "Denied",
                    "roles": [DRAWING_ROLE],
                    "temporary_password": "DeniedSecure123!",
                }
            )

    def test_manager_cannot_disable_own_account(self) -> None:
        from almdina_erp.almdina_erp.services.workforce_service import set_workforce_user_enabled

        frappe.set_user(MANAGER_USER)
        with self.assertRaises(frappe.ValidationError):
            set_workforce_user_enabled(MANAGER_USER, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
