from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


ROLE = "Almdina Legacy Projection Migration Test"


class TestPermissionProjectionMigrationIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        if not frappe.db.exists("Role", ROLE):
            frappe.get_doc(
                {"doctype": "Role", "role_name": ROLE, "desk_access": 1}
            ).insert(ignore_permissions=True)
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        sync_permission_types()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def test_migrate_removes_stale_settings_read_write_without_new_business_grants(self) -> None:
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Almdina ERP Settings",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": ROLE,
                "permlevel": 0,
                "read": 1,
                "write": 1,
                Capability.MANAGE_USERS: 1,
            }
        ).insert(ignore_permissions=True)

        sync_permission_types()

        row = frappe.db.get_value(
            "Custom DocPerm",
            {
                "parent": "Almdina ERP Settings",
                "role": ROLE,
                "permlevel": 0,
            },
            [
                "read",
                "write",
                Capability.MANAGE_USERS,
                Capability.VIEW_USERS,
                Capability.CREATE_USERS,
                Capability.MANAGE_PERMISSIONS,
                Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
                Capability.EDIT_FACTORY_COST_DEFAULTS,
                Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
            ],
            as_dict=True,
        )
        self.assertEqual(
            int(row.read),
            0,
            "view_factory_settings reuses the standard read column and must be removed.",
        )
        self.assertEqual(int(row.write), 0)
        self.assertEqual(int(row.get(Capability.MANAGE_USERS)), 1)
        self.assertEqual(int(row.get(Capability.VIEW_USERS)), 1)
        self.assertEqual(int(row.get(Capability.CREATE_USERS)), 1)
        self.assertEqual(int(row.get(Capability.MANAGE_PERMISSIONS)), 0)
        for capability in (
            Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
            Capability.EDIT_FACTORY_COST_DEFAULTS,
            Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
        ):
            self.assertEqual(int(row.get(capability)), 0)

    def test_migrate_repairs_customer_and_edge_reads_for_order_editors(self) -> None:
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Door Cutting Order",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": ROLE,
                "permlevel": 0,
                "read": 1,
                "create": 1,
                "write": 1,
            }
        ).insert(ignore_permissions=True)

        sync_permission_types()

        for doctype in ("Customer", "Edge Banding Type"):
            permission = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": doctype, "role": ROLE, "permlevel": 0},
                ["read", "select"],
                as_dict=True,
            )
            self.assertIsNotNone(permission, doctype)
            self.assertEqual(int(permission.read), 1, doctype)
            self.assertEqual(int(permission.select), 1, doctype)


__all__ = ["TestPermissionProjectionMigrationIntegration"]
