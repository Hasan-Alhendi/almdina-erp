from __future__ import annotations

import json
import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.security.permission_matrix import validate_capability_dependencies
from almdina_erp.almdina_erp.application.security.permission_transfer import (
    PERMISSION_TRANSFER_SCHEMA,
    PERMISSION_TRANSFER_VERSION,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import sync_permission_types


ADMIN_ROLE = "Almdina Transfer Admin Test"
SOURCE_ROLE = "Almdina Transfer Source Test"
TARGET_ROLE = "Almdina Transfer Target Test"
UNAUTHORIZED_ROLE = "Almdina Transfer Unauthorized Test"
ADMIN_USER = "almdina.transfer.admin@example.com"
UNAUTHORIZED_USER = "almdina.transfer.unauthorized@example.com"


def manual_state(*capabilities: str) -> dict[str, bool]:
    return validate_capability_dependencies({capability: True for capability in capabilities})


class TestPermissionTransferIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (ADMIN_ROLE, SOURCE_ROLE, TARGET_ROLE, UNAUTHORIZED_ROLE):
            cls._ensure_role(role)
            cls._ensure_managed_role(role)
        cls._ensure_user(ADMIN_USER, ADMIN_ROLE)
        cls._ensure_user(UNAUTHORIZED_USER, UNAUTHORIZED_ROLE)
        cls._replace_role_permissions(
            ADMIN_ROLE,
            "Almdina ERP Settings",
            {"read": 1, Capability.MANAGE_PERMISSIONS: 1},
        )
        frappe.clear_cache(user=ADMIN_USER)
        frappe.clear_cache(user=UNAUTHORIZED_USER)
        frappe.clear_cache(doctype="Almdina ERP Settings")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        roles = [ADMIN_ROLE, SOURCE_ROLE, TARGET_ROLE, UNAUTHORIZED_ROLE]
        frappe.db.delete("Almdina Permission Audit", {"role": ["in", roles]})
        frappe.db.delete("Almdina Role Metadata", {"role": ["in", roles]})
        for role in roles:
            frappe.db.delete("Custom DocPerm", {"role": role})
        for user in (ADMIN_USER, UNAUTHORIZED_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in roles:
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

    @classmethod
    def _ensure_managed_role(cls, role: str) -> None:
        if frappe.db.exists("Almdina Role Metadata", {"role": role}):
            return
        frappe.get_doc(
            {
                "doctype": "Almdina Role Metadata",
                "role": role,
                "role_uid": str(uuid.uuid4()),
                "description": "Permission transfer integration role",
                "managed_by_almdina": 1,
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
    def _replace_role_permissions(cls, role: str, doctype: str, values: dict[str, int]) -> None:
        frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                **values,
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina Permission Audit", {"role": ["in", [SOURCE_ROLE, TARGET_ROLE]]})
        for role in (SOURCE_ROLE, TARGET_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
        frappe.clear_cache()
        super().tearDown()

    def test_console_is_manual_only_and_does_not_persist_on_open(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import get_permission_console

        frappe.set_user(ADMIN_USER)
        before_rows = frappe.db.count("Custom DocPerm", {"role": TARGET_ROLE})
        before_audit = frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE})
        console = get_permission_console(TARGET_ROLE)
        self.assertNotIn("templates", console)
        self.assertTrue(console["catalog"])
        self.assertEqual(console["transfer"]["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(console["transfer"]["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(console["selected"]["role"], TARGET_ROLE)
        self.assertEqual(frappe.db.count("Custom DocPerm", {"role": TARGET_ROLE}), before_rows)
        self.assertEqual(frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}), before_audit)

    def test_export_import_preview_and_explicit_save_round_trip(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            export_role_permissions,
            preview_permission_import,
            update_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        source_state = manual_state(
            Capability.VIEW_ORDERS,
            Capability.VIEW_CUTTING_PLAN,
            Capability.VIEW_DRAWING_WORKSPACE,
            Capability.UPLOAD_DXF,
            Capability.APPROVE_DXF,
        )
        update_role_permissions(SOURCE_ROLE, source_state)
        exported = export_role_permissions(SOURCE_ROLE)
        self.assertEqual(exported["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(exported["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(exported["role"], SOURCE_ROLE)
        self.assertNotIn("users", exported)
        self.assertNotIn("password", json.dumps(exported).lower())

        imported = preview_permission_import(TARGET_ROLE, json.dumps(exported, ensure_ascii=False))
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
        from almdina_erp.almdina_erp.services.permission_management_service import export_role_permissions, preview_permission_import

        frappe.set_user(ADMIN_USER)
        document = export_role_permissions(SOURCE_ROLE)
        document["capabilities"] = [Capability.APPROVE_ORDER]
        with self.assertRaises(frappe.ValidationError):
            preview_permission_import(TARGET_ROLE, document)

        frappe.set_user(UNAUTHORIZED_USER)
        for call in (
            lambda: export_role_permissions(SOURCE_ROLE),
            lambda: preview_permission_import(TARGET_ROLE, document),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()


if __name__ == "__main__":
    import unittest

    unittest.main()
