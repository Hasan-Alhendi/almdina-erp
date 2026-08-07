from __future__ import annotations

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
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
        if not frappe.db.exists("Almdina Role Metadata", {"role": ROLE}):
            frappe.get_doc(
                {
                    "doctype": "Almdina Role Metadata",
                    "role": ROLE,
                    "role_uid": str(uuid.uuid4()),
                    "description": "Permission migration integration role.",
                    "managed_by_almdina": 1,
                }
            ).insert(ignore_permissions=True)
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        sync_permission_types()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete("Almdina Role Metadata", {"role": ROLE})
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def test_granular_migration_preserves_legacy_workforce_access_without_factory_grants(self) -> None:
        legacy_field = "manage_users"
        if not frappe.get_meta("Custom DocPerm").has_field(legacy_field):
            self.skipTest("Legacy manage_users field is not present on this fresh schema.")

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
                legacy_field: 1,
            }
        ).insert(ignore_permissions=True)

        from almdina_erp.patches.v1_0.migrate_granular_administration_permissions import (
            execute as migrate_granular_administration_permissions,
        )
        from almdina_erp.patches.v1_0.materialize_permission_prerequisites import (
            execute as materialize_permission_prerequisites,
        )

        migrate_granular_administration_permissions()
        materialize_permission_prerequisites()

        state = FrappePermissionMatrixRepository().role_state(ROLE)["capabilities"]
        for capability in (
            Capability.VIEW_USERS,
            Capability.CREATE_USERS,
            Capability.EDIT_USERS,
            Capability.ASSIGN_USER_ROLES,
            Capability.ENABLE_USERS,
            Capability.DISABLE_USERS,
            Capability.RESET_USER_PASSWORD,
        ):
            self.assertTrue(state[capability], capability)
        self.assertFalse(state[Capability.VIEW_FACTORY_SETTINGS])
        self.assertFalse(state[Capability.EDIT_FACTORY_CUTTING_DEFAULTS])
        self.assertFalse(state[Capability.EDIT_FACTORY_COST_DEFAULTS])
        self.assertFalse(state[Capability.EDIT_FACTORY_PRODUCTION_CONTROLS])

        row = frappe.db.get_value(
            "Custom DocPerm",
            {
                "parent": "Almdina ERP Settings",
                "role": ROLE,
                "permlevel": 0,
            },
            ["read", "write"],
            as_dict=True,
        )
        self.assertIsNotNone(row)
        self.assertEqual(int(row.read), 0)
        self.assertEqual(int(row.write), 0)

    def test_prerequisite_migration_materializes_customer_and_edge_reads_for_existing_order_editor(self) -> None:
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

        from almdina_erp.patches.v1_0.materialize_permission_prerequisites import (
            execute as materialize_permission_prerequisites,
        )

        materialize_permission_prerequisites()

        state = FrappePermissionMatrixRepository().role_state(ROLE)["capabilities"]
        self.assertTrue(state[Capability.CREATE_ORDER])
        self.assertTrue(state[Capability.EDIT_ORDER])
        self.assertTrue(state[Capability.VIEW_CUSTOMERS])
        self.assertTrue(state[Capability.VIEW_EDGE_BANDING_TYPES])

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
