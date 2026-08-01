from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


ADMIN_ROLE = "Almdina Permission Console Admin Test"
TARGET_ROLE = "Almdina Permission Console Target Test"
ADMIN_USER = "almdina.permission.console.admin@example.com"
TARGET_USER = "almdina.permission.console.target@example.com"


class TestPermissionManagementIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        cls._ensure_role(ADMIN_ROLE)
        cls._ensure_role(TARGET_ROLE)
        cls._ensure_user(ADMIN_USER, ADMIN_ROLE)
        cls._ensure_user(TARGET_USER, TARGET_ROLE)
        cls._replace_role_permissions(
            ADMIN_ROLE,
            "Almdina ERP Settings",
            {
                "read": 1,
                Capability.MANAGE_PERMISSIONS: 1,
                Capability.MANAGE_FACTORY_SETTINGS: 1,
            },
        )
        frappe.clear_cache(user=ADMIN_USER)
        frappe.clear_cache(doctype="Almdina ERP Settings")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina Permission Audit", {"role": ["in", [ADMIN_ROLE, TARGET_ROLE]]})
        for role in (ADMIN_ROLE, TARGET_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
        for user in (ADMIN_USER, TARGET_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in (ADMIN_ROLE, TARGET_ROLE):
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role,
                    "desk_access": 1,
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def _ensure_user(cls, email: str, role: str) -> None:
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
            user.save(ignore_permissions=True)

    @classmethod
    def _replace_role_permissions(
        cls,
        role: str,
        doctype: str,
        values: dict[str, int],
    ) -> None:
        frappe.db.delete(
            "Custom DocPerm",
            {"parent": doctype, "role": role, "permlevel": 0},
        )
        payload = {
            "doctype": "Custom DocPerm",
            "parent": doctype,
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": role,
            "permlevel": 0,
            **values,
        }
        frappe.get_doc(payload).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina Permission Audit", {"role": TARGET_ROLE})
        frappe.db.delete("Custom DocPerm", {"role": TARGET_ROLE})
        frappe.clear_cache(user=TARGET_USER)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.clear_cache(doctype="Almdina ERP Settings")
        super().tearDown()

    def test_arbitrary_role_can_manage_matrix_and_grant_capabilities(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            get_permission_console,
            update_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        console = get_permission_console()
        self.assertTrue(any(row["name"] == TARGET_ROLE for row in console["roles"]))
        self.assertTrue(console["catalog"])

        result = update_role_permissions(
            TARGET_ROLE,
            {
                Capability.APPROVE_DXF: True,
                Capability.MANAGE_FACTORY_SETTINGS: True,
            },
        )
        self.assertTrue(result["changed"])
        self.assertTrue(result["capabilities"][Capability.VIEW_ORDERS])
        self.assertTrue(result["capabilities"][Capability.APPROVE_DXF])
        self.assertTrue(result["capabilities"][Capability.MANAGE_FACTORY_SETTINGS])

        order_permission = frappe.db.get_value(
            "Custom DocPerm",
            {
                "parent": "Door Cutting Order",
                "role": TARGET_ROLE,
                "permlevel": 0,
            },
            ["read", Capability.APPROVE_DXF],
            as_dict=True,
        )
        settings_permission = frappe.db.get_value(
            "Custom DocPerm",
            {
                "parent": "Almdina ERP Settings",
                "role": TARGET_ROLE,
                "permlevel": 0,
            },
            ["read", "write", Capability.MANAGE_FACTORY_SETTINGS],
            as_dict=True,
        )
        self.assertEqual(int(order_permission.read), 1)
        self.assertEqual(int(order_permission.get(Capability.APPROVE_DXF)), 1)
        self.assertEqual(int(settings_permission.read), 1)
        self.assertEqual(int(settings_permission.write), 1)
        self.assertEqual(
            int(settings_permission.get(Capability.MANAGE_FACTORY_SETTINGS)),
            1,
        )

        frappe.clear_cache(user=TARGET_USER)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.clear_cache(doctype="Almdina ERP Settings")
        self.assertTrue(
            frappe.has_permission(
                "Door Cutting Order",
                ptype=Capability.APPROVE_DXF,
                user=TARGET_USER,
            )
        )
        self.assertTrue(
            frappe.has_permission(
                "Almdina ERP Settings",
                ptype=Capability.MANAGE_FACTORY_SETTINGS,
                user=TARGET_USER,
            )
        )
        self.assertEqual(
            frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}),
            1,
        )

    def test_self_lockout_requires_explicit_confirmation(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            preview_role_permissions,
            update_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        preview = preview_role_permissions(
            ADMIN_ROLE,
            {Capability.MANAGE_FACTORY_SETTINGS: True},
        )
        self.assertTrue(preview["requires_self_lockout_confirmation"])
        with self.assertRaises(frappe.PermissionError):
            update_role_permissions(
                ADMIN_ROLE,
                {Capability.MANAGE_FACTORY_SETTINGS: True},
            )

    def test_factory_settings_are_capability_managed(self) -> None:
        from almdina_erp.almdina_erp.services.production_settings_service import (
            get_production_settings,
        )

        frappe.set_user(ADMIN_USER)
        settings = get_production_settings()
        self.assertIn("default_production_routing", settings)
        self.assertIn("packing_options", settings)

        frappe.set_user(TARGET_USER)
        with self.assertRaises(frappe.PermissionError):
            get_production_settings()


if __name__ == "__main__":
    import unittest

    unittest.main()
