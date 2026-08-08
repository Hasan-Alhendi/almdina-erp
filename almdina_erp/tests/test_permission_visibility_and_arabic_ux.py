from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js"
WORKSPACE = APP / "workspace" / "almdina_erp" / "almdina_erp.json"


class TestPermissionVisibilityAndArabicUX(unittest.TestCase):
    def test_permission_context_exposes_surfaces(self) -> None:
        server = (APP / "application" / "security" / "permission_context.py").read_text(encoding="utf-8")
        client = (PUBLIC / "permission_context.js").read_text(encoding="utf-8")
        self.assertIn('"surfaces": surfaces', server)
        self.assertIn("surface(surfaceName)", client)
        self.assertIn("PERMISSION_CONTEXT_VERSION = 6", server)

    def test_shared_shell_hides_dynamic_shortcuts_and_guards_direct_routes(self) -> None:
        source = (PUBLIC / "shared_shell.js").read_text(encoding="utf-8")
        self.assertIn("MutationObserver", source)
        self.assertIn("hideUnauthorizedShortcuts", source)
        self.assertIn("guardCurrentRoute", source)
        self.assertIn("surfaceAllowed", source)
        self.assertIn("لا تملك صلاحية الوصول إلى هذا القسم", source)
        for route in (
            "customer",
            "production-incident",
            "factory-workforce",
            "factory-permissions",
            "role",
            "factory-order-analysis",
            "production-stage-performance",
        ):
            self.assertIn(route, source)
        self.assertNotIn("frappe.user_roles", source)

    def test_workspace_labels_are_mapped_to_exact_permission_surfaces(self) -> None:
        source = (PUBLIC / "permission_action_visibility_guard.js").read_text(encoding="utf-8")
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
            "القطع التعويضية": "replacements",
            "أخطاء الإنتاج": "production_incidents",
            "ملخص عمليات المعمل": "report_factory_operations_summary",
            "تحليل طلبات القص": "report_factory_order_analysis",
            "تحليل استخدام الألواح": "report_board_usage_analysis",
            "تحليل قياسات الدرف": "report_piece_size_usage_analysis",
            "أداء مراحل الإنتاج": "report_production_stage_performance",
            "أخطاء الإنتاج والقطع التعويضية": "report_production_incidents_and_replacements",
        }
        configured_labels = {row["label"] for row in workspace.get("shortcuts", [])}
        self.assertEqual(configured_labels, set(expected))
        for label, surface in expected.items():
            self.assertIn(f'"{label}": "{surface}"', source)

        self.assertIn("WORKSPACE_LABELS_LONGEST_FIRST", source)
        self.assertIn("right.length - left.length", source)
        self.assertIn('element.getAttribute("data-widget-name")', source)
        self.assertIn("element.textContent", source)
        self.assertIn("guardWorkspaceItems", source)

    def test_empty_workspace_sections_are_hidden_by_surface_policy(self) -> None:
        source = (PUBLIC / "permission_action_visibility_guard.js").read_text(encoding="utf-8")
        for label in (
            "الإعدادات الأساسية",
            "إدارة النظام ومسارات العمل",
            "التشغيل اليومي",
            "التقارير التشغيلية والتكلفة",
        ):
            self.assertIn(f'"{label}"', source)
        self.assertIn("WORKSPACE_SECTION_SURFACES", source)
        self.assertIn("guardWorkspaceSections", source)
        self.assertIn("almdinaPermissionSectionHidden", source)
        self.assertIn(".some(surfaceAllowed)", source)

    def test_workforce_create_action_flash_is_guarded(self) -> None:
        source = (PUBLIC / "permission_action_visibility_guard.js").read_text(encoding="utf-8")
        self.assertIn('currentRoute() !== "factory-workforce"', source)
        self.assertIn('can("create_users")', source)
        self.assertIn("MutationObserver", source)
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn("permission_action_visibility_guard.js", hooks)

    def test_active_permission_services_do_not_use_english_denial_fallbacks(self) -> None:
        paths = (
            APP / "infrastructure" / "frappe" / "authorization_gateway.py",
            APP / "services" / "permission_management_service.py",
            APP / "services" / "workforce_service.py",
            APP / "services" / "master_data_service.py",
            APP / "services" / "report_permission_service.py",
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

    def test_production_incident_permission_is_explicit_and_hooked(self) -> None:
        authorization = (APP / "domain" / "security" / "authorization.py").read_text(encoding="utf-8")
        matrix = (APP / "application" / "security" / "permission_matrix.py").read_text(encoding="utf-8")
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        permissions = (ROOT / "permissions.py").read_text(encoding="utf-8")
        self.assertIn('VIEW_PRODUCTION_INCIDENTS = "view_production_incidents"', authorization)
        self.assertIn("عرض أخطاء الإنتاج", matrix)
        self.assertIn('"Production Incident": "almdina_erp.permissions.production_incident_query"', hooks)
        self.assertIn('"Production Incident": "almdina_erp.permissions.production_incident_has_permission"', hooks)
        self.assertIn("Capability.VIEW_PRODUCTION_INCIDENTS", permissions)


if __name__ == "__main__":
    unittest.main()
