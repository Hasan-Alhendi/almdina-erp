from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.surface_access import Surface
from almdina_erp.almdina_erp.application.security.workspace_visibility import (
    WORKSPACE_ENTRY_SURFACES,
    filter_workspace_content,
    workspace_item_allowed,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js"
MANIFEST = ROOT / "frontend_assets.py"
WORKSPACE = APP / "workspace" / "almdina_erp" / "almdina_erp.json"


class TestPermissionVisibilityAndArabicUX(unittest.TestCase):
    def test_permission_context_exposes_surfaces(self) -> None:
        server = (APP / "application" / "security" / "permission_context.py").read_text(encoding="utf-8")
        client = (PUBLIC / "permission_context.js").read_text(encoding="utf-8")
        self.assertIn('"surfaces": surfaces', server)
        self.assertIn("surface(surfaceName)", client)
        self.assertIn("PERMISSION_CONTEXT_VERSION = 7", server)

    def test_shared_shell_hides_dynamic_shortcuts_and_guards_direct_routes(self) -> None:
        source = (PUBLIC / "shared_shell.js").read_text(encoding="utf-8")
        self.assertIn("MutationObserver", source)
        self.assertIn("hideUnauthorizedShortcuts", source)
        self.assertIn("guardCurrentRoute", source)
        self.assertIn("surfaceAllowed", source)
        self.assertIn("لا تملك صلاحية الوصول إلى هذا القسم", source)
        for route in (
            "customer",
            "factory-workforce",
            "factory-permissions",
            "role",
        ):
            self.assertIn(route, source)
        self.assertNotIn("frappe.user_roles", source)

    def test_workspace_labels_are_mapped_to_exact_permission_surfaces(self) -> None:
        workspace = json.loads(WORKSPACE.read_text(encoding="utf-8"))
        expected = {
            "أنواع القشاط وأسعاره": "edge_banding_types",
            "الزبائن": "customer_admin",
            "إعدادات المعمل": "factory_settings",
            "إدارة الأدوار": "role_admin",
            "إدارة الصلاحيات": "permissions",
            "إدارة المستخدمين": "workforce",
            "إدارة مسارات الإنتاج": "factory_master_data",
            "طلبات قص الدرف": "orders",
            "مراحل الإنتاج": "production_stages",
        }
        configured_labels = {row["label"] for row in workspace.get("shortcuts", [])}
        self.assertEqual(configured_labels, set(expected))
        for label, surface in expected.items():
            self.assertEqual(WORKSPACE_ENTRY_SURFACES[label], surface)

    def test_server_projects_order_only_workspace_before_render(self) -> None:
        workspace = json.loads(WORKSPACE.read_text(encoding="utf-8"))
        surfaces = {surface: False for surface in set(WORKSPACE_ENTRY_SURFACES.values())}
        surfaces[Surface.ORDERS] = True

        filtered = json.loads(filter_workspace_content(workspace["content"], surfaces))
        shortcut_names = {
            block.get("data", {}).get("shortcut_name")
            for block in filtered
            if block.get("type") == "shortcut"
        }
        headers = {
            block.get("data", {}).get("text", "")
            for block in filtered
            if block.get("type") == "header"
        }

        self.assertEqual({"طلبات قص الدرف"}, shortcut_names)
        self.assertTrue(any("التشغيل اليومي" in value for value in headers))
        for hidden_section in (
            "الإعدادات الأساسية",
            "إدارة النظام ومسارات العمل",
        ):
            self.assertFalse(any(hidden_section in value for value in headers))
        self.assertFalse(any("التقارير التشغيلية والتكلفة" in value for value in headers))

    def test_v16_sidebar_links_are_authorized_by_business_surface(self) -> None:
        surfaces = {
            Surface.ORDERS: True,
            Surface.FACTORY_SETTINGS: False,
        }
        order_link = {
            "type": "Link",
            "parent_page": "Almdina ERP",
            "link_to": "Door Cutting Order",
            "label": "طلبات قص الدرف",
        }
        denied_settings = {
            "type": "Link",
            "parent_page": "Almdina ERP",
            "link_to": "factory-production-settings",
            "label": "إعدادات المعمل",
        }
        self.assertIs(workspace_item_allowed(order_link, surfaces), True)
        self.assertIs(workspace_item_allowed(denied_settings, surfaces), False)

    def test_workspace_server_guards_cover_boot_and_desktop_endpoint(self) -> None:
        boot = (ROOT / "boot.py").read_text(encoding="utf-8")
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        endpoint = (ROOT / "workspace_api.py").read_text(encoding="utf-8")

        self.assertIn('"sidebar_pages"', boot)
        self.assertIn("workspace_item_allowed", boot)
        self.assertIn("project_workspace_page", boot)
        self.assertIn("Link/URL rows are business destinations", boot)
        self.assertLess(
            boot.index('if page_type in {"link", "url"}:'),
            boot.index("return _workspace_name(page) in allowed"),
        )

        self.assertIn('"frappe.desk.desktop.get_desktop_page"', hooks)
        self.assertIn('"almdina_erp.workspace_api.get_desktop_page"', hooks)
        self.assertIn("frappe_get_desktop_page(page)", endpoint)
        self.assertIn("filter_desktop_page_payload", endpoint)
        self.assertLess(
            endpoint.index("frappe_get_desktop_page(page)"),
            endpoint.index("filter_desktop_page_payload(payload"),
        )

    def test_workforce_create_action_is_page_owned_and_guard_is_retired(self) -> None:
        controller = (PUBLIC / "factory_workforce" / "controller.js").read_text(encoding="utf-8")
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('page.set_primary_action(__("إنشاء مستخدم جديد"), openCreateDialog, "add");', controller)
        self.assertIn('if (!can("create_users")) return;', controller)
        self.assertIn("syncPrimaryAction();", controller)
        self.assertFalse((PUBLIC / "permission_action_visibility_guard.js").exists())
        self.assertNotIn("permission_action_visibility_guard.js", manifest)

    def test_active_permission_services_do_not_use_english_denial_fallbacks(self) -> None:
        paths = (
            APP / "infrastructure" / "frappe" / "authorization_gateway.py",
            APP / "services" / "permission_management_service.py",
            APP / "services" / "workforce_service.py",
            APP / "services" / "master_data_service.py",
            APP / "domain" / "security" / "workforce.py",
        )
        forbidden = (
            "You do not have permission",
            "Only a permission administrator",
            "Unsupported factory master data type",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for phrase in forbidden:
                self.assertNotIn(phrase, source, f"{phrase!r} remains in {path}")
            self.assertTrue(any("\u0600" <= char <= "\u06ff" for char in source), path)

if __name__ == "__main__":
    unittest.main()
