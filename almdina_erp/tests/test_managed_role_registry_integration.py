from __future__ import annotations

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.role_repository import FrappeRoleRepository
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_repository import FrappeWorkforceRepository


MANAGED_ROLE = "Almdina Registry Managed Test"
EXTERNAL_ROLE = "Almdina Registry External Frappe Test"


class TestManagedRoleRegistryIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        for role in (MANAGED_ROLE, EXTERNAL_ROLE):
            if not frappe.db.exists("Role", role):
                frappe.get_doc(
                    {"doctype": "Role", "role_name": role, "desk_access": 1}
                ).insert(ignore_permissions=True)
        if not frappe.db.exists("Almdina Role Metadata", {"role": MANAGED_ROLE}):
            frappe.get_doc(
                {
                    "doctype": "Almdina Role Metadata",
                    "role": MANAGED_ROLE,
                    "role_uid": str(uuid.uuid4()),
                    "description": "Managed registry integration role",
                    "managed_by_almdina": 1,
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina Role Metadata", {"role": ["in", [MANAGED_ROLE, EXTERNAL_ROLE]]})
        frappe.db.delete("Custom DocPerm", {"role": ["in", [MANAGED_ROLE, EXTERNAL_ROLE]]})
        for role in (MANAGED_ROLE, EXTERNAL_ROLE):
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    def test_role_console_exposes_only_registered_role(self) -> None:
        repository = FrappeRoleRepository()
        names = {row["name"] for row in repository.list_roles(limit=200)}
        self.assertIn(MANAGED_ROLE, names)
        self.assertNotIn(EXTERNAL_ROLE, names)
        self.assertEqual(repository.get_role(MANAGED_ROLE)["name"], MANAGED_ROLE)
        with self.assertRaisesRegex(ValueError, "outside the Almdina managed-role registry"):
            repository.get_role(EXTERNAL_ROLE)

    def test_permission_matrix_rejects_external_role(self) -> None:
        repository = FrappePermissionMatrixRepository()
        names = {row["name"] for row in repository.list_roles()}
        self.assertIn(MANAGED_ROLE, names)
        self.assertNotIn(EXTERNAL_ROLE, names)
        self.assertEqual(repository.validate_role(MANAGED_ROLE), MANAGED_ROLE)
        with self.assertRaisesRegex(ValueError, "outside the Almdina managed-role registry"):
            repository.validate_role(EXTERNAL_ROLE)

    def test_workforce_assignment_exposes_only_registered_role(self) -> None:
        repository = FrappeWorkforceRepository()
        names = {row["name"] for row in repository.list_assignable_roles()}
        self.assertIn(MANAGED_ROLE, names)
        self.assertNotIn(EXTERNAL_ROLE, names)
        repository.ensure_assignable_roles((MANAGED_ROLE,))
        with self.assertRaisesRegex(ValueError, "not managed by Almdina"):
            repository.ensure_assignable_roles((EXTERNAL_ROLE,))


if __name__ == "__main__":
    import unittest

    unittest.main()
