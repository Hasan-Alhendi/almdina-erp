from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.workforce_security_cleanup import (
    revoke_hidden_system_manager_from_almdina_workforce,
)


ALMDINA_USER = "almdina.hidden.system.manager@example.com"
OUTSIDE_USER = "outside.hidden.system.manager@example.com"


class TestWorkforceSecurityCleanup(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        for user in (ALMDINA_USER, OUTSIDE_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        self._create_user(ALMDINA_USER, default_app="almdina_erp")
        self._create_user(OUTSIDE_USER, default_app="")

    def tearDown(self):
        frappe.set_user("Administrator")
        for user in (ALMDINA_USER, OUTSIDE_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    @staticmethod
    def _create_user(email: str, *, default_app: str) -> None:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Security Cleanup",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
                "default_app": default_app,
            }
        )
        for role in ("Desk User", "System Manager"):
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.insert(ignore_permissions=True)

    @staticmethod
    def _has_system_manager(user: str) -> bool:
        return bool(
            frappe.db.exists(
                "Has Role",
                {
                    "parent": user,
                    "parenttype": "User",
                    "role": "System Manager",
                },
            )
        )

    def test_cleanup_removes_hidden_system_manager_only_from_almdina_users(self) -> None:
        self.assertTrue(self._has_system_manager(ALMDINA_USER))
        self.assertTrue(self._has_system_manager(OUTSIDE_USER))

        removed = revoke_hidden_system_manager_from_almdina_workforce()

        self.assertEqual(removed, 1)
        self.assertFalse(self._has_system_manager(ALMDINA_USER))
        self.assertTrue(self._has_system_manager(OUTSIDE_USER))


if __name__ == "__main__":
    import unittest

    unittest.main()
