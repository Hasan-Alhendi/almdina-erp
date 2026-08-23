from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.workforce_repository import (
    FrappeWorkforceRepository,
)


EXTERNAL_USER = "almdina.workforce.adoption@example.com"
EXISTING_ROLE = "Almdina Adoption Existing Role Test"


class TestWorkforceAdoptionIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        if not frappe.db.exists("Role", EXISTING_ROLE):
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": EXISTING_ROLE,
                    "desk_access": 1,
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina User Audit", {"target_user": EXTERNAL_USER})
        if frappe.db.exists("User", EXTERNAL_USER):
            frappe.delete_doc("User", EXTERNAL_USER, force=True, ignore_permissions=True)
        if frappe.db.exists("Role", EXISTING_ROLE):
            frappe.delete_doc("Role", EXISTING_ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina User Audit", {"target_user": EXTERNAL_USER})
        if frappe.db.exists("User", EXTERNAL_USER):
            frappe.delete_doc("User", EXTERNAL_USER, force=True, ignore_permissions=True)

        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": EXTERNAL_USER,
                "first_name": "External",
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
                "default_app": "",
                "default_workspace": "",
            }
        )
        for role in ("Desk User", EXISTING_ROLE, "System Manager"):
            if frappe.db.exists("Role", role):
                user.append("roles", {"role": role})
        user.insert(ignore_permissions=True)
        frappe.clear_cache(user=EXTERNAL_USER)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina User Audit", {"target_user": EXTERNAL_USER})
        if frappe.db.exists("User", EXTERNAL_USER):
            frappe.delete_doc("User", EXTERNAL_USER, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def test_existing_system_user_moves_from_available_to_workforce(self) -> None:
        repository = FrappeWorkforceRepository()

        available_before = {
            row["email"]
            for row in repository.list_available_users(search=EXTERNAL_USER)
        }
        workforce_before = {
            row["email"] for row in repository.list_users(search=EXTERNAL_USER)
        }
        navigation_before = frappe.db.get_value(
            "User",
            EXTERNAL_USER,
            ["default_app", "default_workspace"],
            as_dict=True,
        )
        self.assertIn(EXTERNAL_USER, available_before)
        self.assertNotIn(EXTERNAL_USER, workforce_before)

        adopted = repository.adopt_user(EXTERNAL_USER)
        self.assertTrue(adopted["is_almdina"])
        self.assertEqual(adopted["default_app"], navigation_before.default_app or "")
        self.assertEqual(
            adopted["default_workspace"],
            navigation_before.default_workspace or "",
        )

        direct_roles = set(
            frappe.get_all(
                "Has Role",
                filters={"parent": EXTERNAL_USER, "parenttype": "User"},
                pluck="role",
            )
        )
        self.assertIn("Desk User", direct_roles)
        self.assertIn(EXISTING_ROLE, direct_roles)
        self.assertNotIn("System Manager", direct_roles)

        available_after = {
            row["email"]
            for row in repository.list_available_users(search=EXTERNAL_USER)
        }
        workforce_after = {
            row["email"] for row in repository.list_users(search=EXTERNAL_USER)
        }
        self.assertNotIn(EXTERNAL_USER, available_after)
        self.assertIn(EXTERNAL_USER, workforce_after)


if __name__ == "__main__":
    import unittest

    unittest.main()
