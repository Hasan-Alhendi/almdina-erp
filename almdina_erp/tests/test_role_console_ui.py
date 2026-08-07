from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_roles" / "factory_roles.js"
PAGE_JSON = PAGE.with_suffix(".json")
WORKSPACE = (
    ROOT
    / "almdina_erp"
    / "workspace"
    / "almdina_settings"
    / "almdina_settings.json"
)
SERVICE = ROOT / "almdina_erp" / "services" / "role_management_service.py"


class TestRoleConsoleUI(unittest.TestCase):
    def test_page_is_registered_without_fixed_role_metadata(self) -> None:
        page = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(page["name"], "factory-roles")
        self.assertEqual(page["page_name"], "factory-roles")
        self.assertEqual(page["roles"], [])
        self.assertEqual(page["module"], "Almdina ERP")

    def test_workspace_opens_the_custom_role_console(self) -> None:
        workspace = json.loads(WORKSPACE.read_text(encoding="utf-8"))
        shortcuts = {
            row["label"]: (row["type"], row["link_to"])
            for row in workspace["shortcuts"]
        }
        links = {
            row["label"]: (row["link_type"], row["link_to"])
            for row in workspace["links"]
        }
        self.assertEqual(
            shortcuts["إدارة الأدوار"],
            ("Page", "factory-roles"),
        )
        self.assertEqual(
            links["إدارة الأدوار"],
            ("Page", "factory-roles"),
        )

    def test_console_is_arabic_responsive_and_uses_server_actions(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        for text in (
            "إدارة الأدوار",
            "أدوار ديناميكية من الصفر",
            "إنشاء دور",
            "منح الصلاحيات",
            "إسناده للمستخدم",
            "اكتب اسم الدور للتأكيد",
        ):
            self.assertIn(text, source)
        for endpoint in (
            "get_role_console",
            "create_factory_role",
            "update_factory_role",
            "set_factory_role_enabled",
            "delete_factory_role",
            "get_factory_role_audit",
        ):
            self.assertIn(endpoint, source)
        self.assertIn("requestId", source)
        self.assertIn("actionAllowed", source)
        self.assertIn("arc-table-wrap", source)
        self.assertIn("arc-mobile-list", source)
        self.assertIn("@media(max-width:760px)", source)
        self.assertIn("frappe.utils.escape_html", source)
        self.assertIn("confirm_delete: 1", source)
        self.assertNotIn("frappe.user_roles", source)

    def test_console_hides_actions_without_their_granular_capabilities(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("window.AlmdinaPermissions", source)
        self.assertIn('this.can("create_roles")', source)
        self.assertIn('this.can("edit_roles")', source)
        self.assertIn('this.can("delete_roles")', source)
        self.assertIn('this.can("view_roles")', source)
        self.assertIn('this.can("manage_permissions")', source)
        self.assertIn("عرض فقط", source)

    def test_console_contains_no_fixed_factory_role_catalog_or_templates(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        for role in (
            "Order Entry",
            "Production Manager",
            "عامل رسم",
            "عامل CNC",
            "عامل شريون",
            "عامل تقشيط",
        ):
            self.assertNotIn(role, source)
        self.assertNotIn("PermissionTemplate", source)
        self.assertNotIn("permission_template", source)
        self.assertNotIn("الملف التشغيلي", source)

    def test_client_never_writes_role_documents_directly(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        self.assertNotIn('frappe.db.set_value("Role"', source)
        self.assertNotIn('frappe.client.insert', source)
        self.assertNotIn('frappe.client.delete', source)
        self.assertIn("role_management_service", source)
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("_require_role_capability(", service)
        self.assertNotIn("_require_role_management()", service)


if __name__ == "__main__":
    unittest.main()
