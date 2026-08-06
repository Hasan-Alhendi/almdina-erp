from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.application.security.permission_transfer import (
    build_permission_bundle,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


ROLE_ENTRY = "Almdina Portability Entry Test"
ROLE_OPERATOR = "Almdina Portability Operator Test"
MISSING_ROLE = "Almdina Portability Missing Test"


def manual_state(*capabilities: str) -> dict[str, bool]:
    return normalize_capability_state(
        {capability: True for capability in capabilities}
    )


class TestPermissionPortabilityIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        cls.repository = FrappePermissionMatrixRepository()
        for role in (ROLE_ENTRY, ROLE_OPERATOR):
            if not frappe.db.exists("Role", role):
                frappe.get_doc(
                    {
                        "doctype": "Role",
                        "role_name": role,
                        "desk_access": 1,
                    }
                ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "Almdina Permission Audit",
            {"role": ["in", [ROLE_ENTRY, ROLE_OPERATOR, MISSING_ROLE]]},
        )
        frappe.db.delete(
            "Custom DocPerm",
            {"role": ["in", [ROLE_ENTRY, ROLE_OPERATOR, MISSING_ROLE]]},
        )
        for role in (ROLE_ENTRY, ROLE_OPERATOR):
            if frappe.db.exists("Role", role):
                frappe.delete_doc(
                    "Role",
                    role,
                    force=True,
                    ignore_permissions=True,
                )
        frappe.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        frappe.db.delete(
            "Almdina Permission Audit",
            {"role": ["in", [ROLE_ENTRY, ROLE_OPERATOR]]},
        )
        self.repository.save_role_states(
            {
                ROLE_ENTRY: {},
                ROLE_OPERATOR: {},
            }
        )

    def test_full_matrix_export_preview_and_atomic_import(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            export_permission_bundle,
            import_permission_bundle,
            preview_permission_bundle_import,
        )

        desired = {
            ROLE_ENTRY: manual_state(
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.SUBMIT_ORDER,
            ),
            ROLE_OPERATOR: manual_state(
                Capability.VIEW_ORDERS,
                Capability.VIEW_CUTTING_PLAN,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            ),
        }
        bundle = build_permission_bundle(
            desired,
            exported_by="Administrator",
            exported_at="2026-08-01 22:00:00",
            app_version="1.0.0-dev",
        )

        preview = preview_permission_bundle_import(bundle)
        self.assertEqual(preview["summary"]["role_count"], 2)
        self.assertEqual(preview["summary"]["changed_role_count"], 2)
        self.assertGreater(preview["summary"]["change_count"], 0)
        self.assertTrue(preview["has_sensitive_changes"])

        with self.assertRaises(frappe.PermissionError):
            import_permission_bundle(bundle)

        result = import_permission_bundle(bundle, confirm_sensitive=1)
        self.assertTrue(result["changed"])
        self.assertEqual(len(result["audit_names"]), 2)

        entry = self.repository.role_state(ROLE_ENTRY)["capabilities"]
        operator = self.repository.role_state(ROLE_OPERATOR)["capabilities"]
        self.assertTrue(entry[Capability.CREATE_ORDER])
        self.assertTrue(entry[Capability.SUBMIT_ORDER])
        self.assertFalse(entry[Capability.APPROVE_ORDER])
        self.assertTrue(operator[Capability.START_ASSIGNED_STAGE])
        self.assertTrue(operator[Capability.HANDOFF_ASSIGNED_STAGE])
        self.assertFalse(operator[Capability.DISPATCH_ORDER])

        audits = frappe.get_all(
            "Almdina Permission Audit",
            filters={"role": ["in", [ROLE_ENTRY, ROLE_OPERATOR]]},
            fields=["role", "source"],
        )
        self.assertEqual(len(audits), 2)
        self.assertTrue(
            all(row.source == "Almdina Permission Import" for row in audits)
        )

        exported = export_permission_bundle()
        self.assertEqual(exported["kind"], "role_matrix")
        self.assertTrue(exported["checksum"])
        self.assertNotIn("users", exported)
        self.assertNotIn("passwords", exported)
        self.assertNotIn("audit", exported)
        exported_roles = {row["role"] for row in exported["roles"]}
        self.assertIn(ROLE_ENTRY, exported_roles)
        self.assertIn(ROLE_OPERATOR, exported_roles)

    def test_missing_target_role_aborts_before_any_write(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            preview_permission_bundle_import,
        )

        before = self.repository.role_state(ROLE_ENTRY)["capabilities"]
        bundle = build_permission_bundle(
            {
                ROLE_ENTRY: manual_state(
                    Capability.VIEW_ORDERS,
                    Capability.CREATE_ORDER,
                ),
                MISSING_ROLE: manual_state(
                    Capability.VIEW_ORDERS,
                    Capability.START_ASSIGNED_STAGE,
                ),
            },
            exported_by="Administrator",
            exported_at="2026-08-01 22:00:00",
            app_version="1.0.0-dev",
        )

        with self.assertRaises(frappe.ValidationError):
            preview_permission_bundle_import(bundle)

        after = self.repository.role_state(ROLE_ENTRY)["capabilities"]
        self.assertEqual(after, before)
        self.assertEqual(
            frappe.db.count(
                "Almdina Permission Audit",
                {"role": ROLE_ENTRY},
            ),
            0,
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
