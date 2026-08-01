from __future__ import annotations

import unittest

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


class TestPermissionTypeIntegration(unittest.TestCase):
    def test_business_permission_types_are_installed_without_role_grants(self) -> None:
        capabilities = (
            Capability.RECALCULATE_PLAN,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.APPROVE_DXF,
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.PRINT_CUSTOMER_INVOICE,
            Capability.PRINT_INTERNAL_COST_REPORT,
        )
        for permission_type in capabilities:
            with self.subTest(permission_type=permission_type):
                self.assertTrue(
                    frappe.db.exists(
                        "Permission Type",
                        {
                            "perm_type": permission_type,
                            "doc_type": "Door Cutting Order",
                        },
                    )
                )
                self.assertTrue(frappe.get_meta("DocPerm").has_field(permission_type))
                self.assertTrue(
                    frappe.get_meta("Custom DocPerm").has_field(permission_type)
                )
                self.assertEqual(
                    frappe.db.count(
                        "Custom DocPerm",
                        filters={
                            "parent": "Door Cutting Order",
                            permission_type: 1,
                        },
                    ),
                    0,
                )

    def test_administrator_can_grant_approval_to_an_arbitrary_role(self) -> None:
        role_name = "Almdina Dynamic Approval Test"
        user_email = "almdina.dynamic.approval@example.com"

        if not frappe.db.exists("Role", role_name):
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role_name,
                    "desk_access": 1,
                }
            ).insert(ignore_permissions=True)

        if frappe.db.exists("User", user_email):
            user = frappe.get_doc("User", user_email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": user_email,
                    "first_name": "Dynamic Approval",
                    "enabled": 1,
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        if role_name not in {row.role for row in (user.roles or [])}:
            user.append("roles", {"role": role_name})
            user.save(ignore_permissions=True)

        frappe.db.delete(
            "Custom DocPerm",
            {"parent": "Door Cutting Order", "role": role_name},
        )
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Door Cutting Order",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role_name,
                "permlevel": 0,
                "read": 1,
                Capability.APPROVE_DXF: 1,
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Door Cutting Order")

        try:
            self.assertTrue(
                frappe.has_permission(
                    "Door Cutting Order",
                    ptype=Capability.APPROVE_DXF,
                    user=user_email,
                )
            )
        finally:
            frappe.db.delete(
                "Custom DocPerm",
                {"parent": "Door Cutting Order", "role": role_name},
            )
            frappe.clear_cache(doctype="Door Cutting Order")

    def test_permission_type_sync_is_idempotent(self) -> None:
        before = frappe.db.count("Permission Type")
        sync_permission_types()
        sync_permission_types()
        self.assertEqual(frappe.db.count("Permission Type"), before)


if __name__ == "__main__":
    unittest.main()
