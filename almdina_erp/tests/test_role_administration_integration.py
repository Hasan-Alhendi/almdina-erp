from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


ROLE_ORIGINAL = "Almdina Dynamic Role Test"
ROLE_RENAMED = "Almdina Dynamic Role Renamed Test"
ROLE_ASSIGNED = "Almdina Assigned Role Test"
ROLE_PERMISSIONED = "Almdina Permissioned Role Test"
ASSIGNED_USER = "almdina.role.assigned@example.com"
UNAUTHORIZED_USER = "almdina.role.unauthorized@example.com"


class TestRoleAdministrationIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls._cleanup_all()
        cls._ensure_user(UNAUTHORIZED_USER)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup_all()
        for user in (ASSIGNED_USER, UNAUTHORIZED_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc(
                    "User",
                    user,
                    force=True,
                    ignore_permissions=True,
                )
        frappe.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._cleanup_roles()

    def tearDown(self):
        frappe.set_user("Administrator")
        if frappe.db.exists("User", ASSIGNED_USER):
            frappe.delete_doc(
                "User",
                ASSIGNED_USER,
                force=True,
                ignore_permissions=True,
            )
        self._cleanup_roles()
        frappe.clear_cache()
        super().tearDown()

    @classmethod
    def _ensure_user(cls, email: str, role: str | None = None) -> None:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "Role Test",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
        if role and role not in {row.role for row in user.roles or []}:
            user.append("roles", {"role": role})
            user.save(ignore_permissions=True)
        frappe.clear_cache(user=email)

    @classmethod
    def _cleanup_all(cls) -> None:
        for user in (ASSIGNED_USER,):
            if frappe.db.exists("User", user):
                frappe.delete_doc(
                    "User",
                    user,
                    force=True,
                    ignore_permissions=True,
                )
        cls._cleanup_roles()

    @classmethod
    def _cleanup_roles(cls) -> None:
        roles = [ROLE_ORIGINAL, ROLE_RENAMED, ROLE_ASSIGNED, ROLE_PERMISSIONED]
        frappe.db.delete("Almdina Role Audit", {"role_name": ["in", roles]})
        for role in roles:
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("DocPerm", {"role": role})
            metadata = frappe.db.get_value(
                "Almdina Role Metadata",
                {"role": role},
                "name",
            )
            if metadata:
                frappe.delete_doc(
                    "Almdina Role Metadata",
                    metadata,
                    force=True,
                    ignore_permissions=True,
                )
            if frappe.db.exists("Role", role):
                frappe.delete_doc(
                    "Role",
                    role,
                    force=True,
                    ignore_permissions=True,
                )

    def test_full_role_lifecycle_starts_without_permissions(self) -> None:
        from almdina_erp.almdina_erp.services.role_management_service import (
            create_factory_role,
            delete_factory_role,
            get_factory_role_audit,
            get_role_console,
            set_factory_role_enabled,
            update_factory_role,
        )

        created = create_factory_role(
            {
                "name": ROLE_ORIGINAL,
                "description": "Role created completely from scratch.",
            }
        )["role"]
        self.assertEqual(created["name"], ROLE_ORIGINAL)
        self.assertTrue(created["enabled"])
        self.assertTrue(created["desk_access"])
        self.assertTrue(created["is_custom"])
        self.assertEqual(created["permission_count"], 0)
        self.assertEqual(
            frappe.db.count("Custom DocPerm", {"role": ROLE_ORIGINAL}),
            0,
        )
        self.assertEqual(
            frappe.db.count("DocPerm", {"role": ROLE_ORIGINAL}),
            0,
        )

        renamed = update_factory_role(
            ROLE_ORIGINAL,
            {
                "name": ROLE_RENAMED,
                "description": "Updated Arabic-ready role description.",
            },
        )["role"]
        self.assertEqual(renamed["name"], ROLE_RENAMED)
        self.assertEqual(renamed["role_uid"], created["role_uid"])
        self.assertFalse(frappe.db.exists("Role", ROLE_ORIGINAL))

        disabled = set_factory_role_enabled(ROLE_RENAMED, 0)["role"]
        self.assertFalse(disabled["enabled"])
        enabled = set_factory_role_enabled(ROLE_RENAMED, 1)["role"]
        self.assertTrue(enabled["enabled"])

        console = get_role_console(search="Dynamic Role Renamed")
        selected = next(
            row for row in console["roles"] if row["name"] == ROLE_RENAMED
        )
        self.assertEqual(selected["assigned_users"], 0)
        self.assertEqual(selected["reference_total"], 0)

        audit = get_factory_role_audit(ROLE_RENAMED)
        self.assertEqual(
            [row["action"] for row in audit["events"][:4]],
            ["Enabled", "Disabled", "Updated", "Created"],
        )

        with self.assertRaises(frappe.ValidationError):
            delete_factory_role(ROLE_RENAMED, 0)
        deleted = delete_factory_role(ROLE_RENAMED, 1)
        self.assertTrue(deleted["deleted"])
        self.assertFalse(frappe.db.exists("Role", ROLE_RENAMED))
        self.assertEqual(
            frappe.db.count(
                "Almdina Role Audit",
                {"role_name": ROLE_RENAMED, "action": "Deleted"},
            ),
            1,
        )

    def test_assigned_role_cannot_be_disabled_or_deleted(self) -> None:
        from almdina_erp.almdina_erp.services.role_management_service import (
            create_factory_role,
            delete_factory_role,
            set_factory_role_enabled,
        )

        create_factory_role({"name": ROLE_ASSIGNED})
        self._ensure_user(ASSIGNED_USER, ROLE_ASSIGNED)
        self.assertTrue(
            frappe.db.exists(
                "Has Role",
                {
                    "parent": ASSIGNED_USER,
                    "parenttype": "User",
                    "role": ROLE_ASSIGNED,
                },
            )
        )
        with self.assertRaises(frappe.ValidationError):
            set_factory_role_enabled(ROLE_ASSIGNED, 0)
        with self.assertRaises(frappe.ValidationError):
            delete_factory_role(ROLE_ASSIGNED, 1)
        self.assertTrue(frappe.db.exists("Role", ROLE_ASSIGNED))
        self.assertTrue(
            frappe.db.exists(
                "Has Role",
                {"parent": ASSIGNED_USER, "role": ROLE_ASSIGNED},
            )
        )

    def test_permission_rows_block_role_deletion(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            update_role_permissions,
        )
        from almdina_erp.almdina_erp.services.role_management_service import (
            create_factory_role,
            delete_factory_role,
            get_role_details,
        )

        create_factory_role({"name": ROLE_PERMISSIONED})
        update_role_permissions(
            ROLE_PERMISSIONED,
            {"view_orders": True},
        )
        snapshot = get_role_details(ROLE_PERMISSIONED)
        self.assertGreater(snapshot["permission_count"], 0)
        with self.assertRaises(frappe.ValidationError):
            delete_factory_role(ROLE_PERMISSIONED, 1)
        self.assertTrue(frappe.db.exists("Role", ROLE_PERMISSIONED))

    def test_unauthorized_user_cannot_call_role_services(self) -> None:
        from almdina_erp.almdina_erp.services.role_management_service import (
            get_role_console,
        )

        frappe.set_user(UNAUTHORIZED_USER)
        with self.assertRaises(frappe.PermissionError):
            get_role_console()


if __name__ == "__main__":
    import unittest

    unittest.main()
