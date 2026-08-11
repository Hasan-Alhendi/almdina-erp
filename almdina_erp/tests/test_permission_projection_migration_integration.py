from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.patches.v1_0.migrate_legacy_administration_capabilities import (
    execute as migrate_legacy_administration_capabilities,
)


ROLE = "Almdina Legacy Projection Migration Test"
LEGACY_MANAGE_USERS = "manage_users"


class TestPermissionProjectionMigrationIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        if not frappe.db.exists("Role", ROLE):
            frappe.get_doc(
                {"doctype": "Role", "role_name": ROLE, "desk_access": 1}
            ).insert(ignore_permissions=True)
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete("Almdina Role Capability State", {"role": ROLE})
        sync_permission_types()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete("Almdina Role Capability State", {"role": ROLE})
        legacy_name = frappe.db.get_value(
            "Permission Type",
            {"perm_type": LEGACY_MANAGE_USERS, "doc_type": "Almdina ERP Settings"},
        )
        if legacy_name:
            frappe.delete_doc(
                "Permission Type",
                legacy_name,
                force=True,
                ignore_permissions=True,
            )
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def _ensure_legacy_permission_type(self) -> None:
        if frappe.db.exists(
            "Permission Type",
            {"perm_type": LEGACY_MANAGE_USERS, "doc_type": "Almdina ERP Settings"},
        ):
            return
        frappe.get_doc(
            {
                "doctype": "Permission Type",
                "perm_type": LEGACY_MANAGE_USERS,
                "doc_type": "Almdina ERP Settings",
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Custom DocPerm")

    def test_migrate_converts_legacy_workforce_grant_without_stale_settings_read(self) -> None:
        self._ensure_legacy_permission_type()
        self.assertTrue(frappe.get_meta("Custom DocPerm").has_field(LEGACY_MANAGE_USERS))

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
                LEGACY_MANAGE_USERS: 1,
            }
        ).insert(ignore_permissions=True)

        migrate_legacy_administration_capabilities()

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
                LEGACY_MANAGE_USERS,
                Capability.VIEW_USERS,
                Capability.CREATE_USERS,
                Capability.EDIT_USERS,
                Capability.ASSIGN_USER_ROLES,
                Capability.ENABLE_USERS,
                Capability.DISABLE_USERS,
                Capability.RESET_USER_PASSWORD,
                Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
                Capability.EDIT_FACTORY_COST_DEFAULTS,
                Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
            ],
            as_dict=True,
        )
        self.assertEqual(int(row.read), 0)
        self.assertEqual(int(row.write), 0)
        self.assertEqual(int(row.get(LEGACY_MANAGE_USERS)), 1)
        for capability in (
            Capability.VIEW_USERS,
            Capability.CREATE_USERS,
            Capability.EDIT_USERS,
            Capability.ASSIGN_USER_ROLES,
            Capability.ENABLE_USERS,
            Capability.DISABLE_USERS,
            Capability.RESET_USER_PASSWORD,
        ):
            self.assertEqual(int(row.get(capability)), 1, capability)
        for capability in (
            Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
            Capability.EDIT_FACTORY_COST_DEFAULTS,
            Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
        ):
            self.assertEqual(int(row.get(capability)), 0, capability)

    def test_sync_repairs_customer_and_edge_reads_from_canonical_order_editor_state(self) -> None:
        repository = FrappePermissionMatrixRepository()
        repository.save_role_state(
            ROLE,
            {
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
            },
        )

        # Simulate stale or accidentally removed Frappe projections. The
        # canonical role capability state remains the sole business authority.
        for doctype in ("Customer", "Edge Banding Type"):
            frappe.db.delete(
                "Custom DocPerm",
                {"parent": doctype, "role": ROLE},
            )

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
