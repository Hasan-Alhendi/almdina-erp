from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.security.permission_transfer import (
    PERMISSION_TRANSFER_SCHEMA,
    PERMISSION_TRANSFER_VERSION,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


ADMIN_ROLE = "Almdina Transfer Admin Test"
SOURCE_ROLE = "Almdina Transfer Source Test"
TARGET_ROLE = "Almdina Transfer Target Test"
UNAUTHORIZED_ROLE = "Almdina Transfer Unauthorized Test"
ADMIN_USER = "almdina.transfer.admin@example.com"
UNAUTHORIZED_USER = "almdina.transfer.unauthorized@example.com"

PLANNER_GRANTS = {
    Capability.VIEW_ORDERS: True,
    Capability.VIEW_CUTTING_PLAN: True,
    Capability.RECALCULATE_PLAN: True,
    Capability.EDIT_OPTIMIZER_SETTINGS: True,
    Capability.PRINT_CUTTING_PLAN: True,
    Capability.VIEW_DRAWING_WORKSPACE: True,
    Capability.EDIT_SPECIAL_DRAWING: True,
    Capability.EXPORT_DXF: True,
    Capability.UPLOAD_DXF: True,
    Capability.REPLACE_DXF: True,
    Capability.APPROVE_DXF: True,
    Capability.START_ASSIGNED_STAGE: True,
    Capability.HANDOFF_ASSIGNED_STAGE: True,
}


class TestPermissionTransferIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (ADMIN_ROLE, SOURCE_ROLE, TARGET_ROLE, UNAUTHORIZED_ROLE):
            cls._ensure_role(role)
        cls._ensure_user(ADMIN_USER, ADMIN_ROLE)
        cls._ensure_user(UNAUTHORIZED_USER, UNAUTHORIZED_ROLE)
        FrappePermissionMatrixRepository().save_role_state(
            ADMIN_ROLE,
            {Capability.MANAGE_PERMISSIONS: True},
        )
        frappe.clear_cache(user=ADMIN_USER)
        frappe.clear_cache(user=UNAUTHORIZED_USER)
        frappe.clear_cache(doctype="Almdina ERP Settings")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        managed_roles = [ADMIN_ROLE, SOURCE_ROLE, TARGET_ROLE, UNAUTHORIZED_ROLE]
        frappe.db.delete(
            "Almdina Permission Audit",
            {"role": ["in", managed_roles]},
        )
        for role in managed_roles:
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("Almdina Role Capability State", {"role": role})
        for user in (ADMIN_USER, UNAUTHORIZED_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in managed_roles:
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
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

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "Almdina Permission Audit",
            {"role": ["in", [SOURCE_ROLE, TARGET_ROLE]]},
        )
        for role in (SOURCE_ROLE, TARGET_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("Almdina Role Capability State", {"role": role})
        frappe.clear_cache()
        super().tearDown()

    def test_console_exposes_transfer_without_templates_or_writes(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            get_permission_console,
        )

        frappe.set_user(ADMIN_USER)
        before_rows = frappe.db.count("Custom DocPerm", {"role": TARGET_ROLE})
        before_audit = frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE})
        console = get_permission_console(TARGET_ROLE)

        self.assertNotIn("templates", console)
        self.assertEqual(console["transfer"]["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(console["transfer"]["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(console["selected"]["role"], TARGET_ROLE)
        self.assertEqual(frappe.db.count("Custom DocPerm", {"role": TARGET_ROLE}), before_rows)
        self.assertEqual(frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}), before_audit)

    def test_manual_preview_is_least_privilege_and_does_not_persist(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            preview_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        preview = preview_role_permissions(
            TARGET_ROLE,
            {
                Capability.START_ASSIGNED_STAGE: True,
                Capability.HANDOFF_ASSIGNED_STAGE: True,
            },
        )
        self.assertTrue(preview["capabilities"][Capability.START_ASSIGNED_STAGE])
        self.assertTrue(preview["capabilities"][Capability.HANDOFF_ASSIGNED_STAGE])
        self.assertFalse(preview["capabilities"][Capability.DISPATCH_ORDER])
        self.assertFalse(preview["capabilities"][Capability.VIEW_FINANCIAL_REPORTS])
        self.assertEqual(frappe.db.count("Custom DocPerm", {"role": TARGET_ROLE}), 0)
        self.assertEqual(frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}), 0)

    def test_export_import_preview_and_explicit_save_round_trip(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            export_role_permissions,
            preview_permission_import,
            preview_role_permissions,
            update_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        source_preview = preview_role_permissions(SOURCE_ROLE, PLANNER_GRANTS)
        update_role_permissions(SOURCE_ROLE, source_preview["capabilities"])
        exported = export_role_permissions(SOURCE_ROLE)

        self.assertEqual(exported["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(exported["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(exported["role"], SOURCE_ROLE)
        self.assertNotIn("users", exported)
        self.assertNotIn("password", json.dumps(exported).lower())

        imported = preview_permission_import(
            TARGET_ROLE,
            json.dumps(exported, ensure_ascii=False),
        )
        self.assertEqual(imported["source"]["kind"], "import")
        self.assertEqual(imported["source"]["role"], SOURCE_ROLE)
        self.assertTrue(imported["capabilities"][Capability.APPROVE_DXF])
        self.assertFalse(imported["capabilities"][Capability.VIEW_COSTS])
        self.assertEqual(frappe.db.count("Custom DocPerm", {"role": TARGET_ROLE}), 0)

        saved = update_role_permissions(TARGET_ROLE, imported["capabilities"])
        self.assertTrue(saved["changed"])
        self.assertTrue(saved["capabilities"][Capability.APPROVE_DXF])
        self.assertEqual(frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}), 1)

    def test_tampered_and_unauthorized_transfers_are_rejected(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            export_role_permissions,
            preview_permission_import,
            preview_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        source_preview = preview_role_permissions(SOURCE_ROLE, PLANNER_GRANTS)
        from almdina_erp.almdina_erp.services.permission_management_service import (
            update_role_permissions,
        )
        update_role_permissions(SOURCE_ROLE, source_preview["capabilities"])
        document = export_role_permissions(SOURCE_ROLE)
        document["capabilities"] = [Capability.APPROVE_ORDER]
        with self.assertRaises(frappe.ValidationError):
            preview_permission_import(TARGET_ROLE, document)

        frappe.set_user(UNAUTHORIZED_USER)
        for call in (
            lambda: export_role_permissions(SOURCE_ROLE),
            lambda: preview_role_permissions(TARGET_ROLE, PLANNER_GRANTS),
            lambda: preview_permission_import(TARGET_ROLE, document),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()


if __name__ == "__main__":
    import unittest

    unittest.main()
