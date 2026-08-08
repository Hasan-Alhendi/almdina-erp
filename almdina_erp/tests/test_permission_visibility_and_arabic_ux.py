from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js"


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
