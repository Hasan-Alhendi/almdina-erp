from __future__ import annotations

import unittest

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


class TestPermissionTypeIntegration(unittest.TestCase):
    def test_drawing_permission_types_are_installed_without_role_grants(self) -> None:
        drawing_capabilities = (
            Capability.RECALCULATE_PLAN,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.APPROVE_DXF,
        )
        for permission_type in drawing_capabilities:
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

    def test_permission_type_sync_is_idempotent(self) -> None:
        before = frappe.db.count("Permission Type")
        sync_permission_types()
        sync_permission_types()
        self.assertEqual(frappe.db.count("Permission Type"), before)


if __name__ == "__main__":
    unittest.main()
