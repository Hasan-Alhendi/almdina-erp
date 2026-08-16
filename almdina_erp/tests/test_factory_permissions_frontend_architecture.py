from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js"
API = ROOT / "public" / "js" / "factory_permissions" / "api.js"
STATE = ROOT / "public" / "js" / "factory_permissions" / "state.js"
CONTROLLER = ROOT / "public" / "js" / "factory_permissions" / "controller.js"
CSS = ROOT / "public" / "css" / "factory_permissions.css"


class FactoryPermissionsFrontendArchitectureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.api = API.read_text(encoding="utf-8")
        cls.state = STATE.read_text(encoding="utf-8")
        cls.controller = CONTROLLER.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")

    def test_page_entry_is_a_thin_composition_root(self) -> None:
        self.assertLessEqual(len(self.page.splitlines()), 80)
        self.assertIn("frontend.ensureStylesheet", self.page)
        self.assertIn("/assets/almdina_erp/js/factory_permissions/api.js", self.page)
        self.assertIn("/assets/almdina_erp/js/factory_permissions/state.js", self.page)
        self.assertIn("/assets/almdina_erp/js/factory_permissions/controller.js", self.page)
        self.assertIn("/assets/almdina_erp/css/factory_permissions.css", self.page)
        self.assertNotIn("frappe.call(", self.page)
        self.assertNotIn("permission_management_service", self.page)
        self.assertNotIn("style.textContent", self.page)

    def test_api_adapter_owns_permission_endpoints_without_dom(self) -> None:
        expected_methods = (
            "get_permission_console",
            "get_role_permissions",
            "preview_role_permissions",
            "export_role_permissions",
            "preview_permission_import",
            "update_role_permissions",
        )
        for method in expected_methods:
            self.assertIn(method, self.api)
        self.assertIn("foundation().rpc", self.api)
        for forbidden in ("document.", "$(", ".html(", "frappe.call("):
            self.assertNotIn(forbidden, self.api)

    def test_state_owner_is_framework_and_dom_free(self) -> None:
        self.assertIn("createLatestRequestGate", self.state)
        self.assertIn("createLifecycleScope", self.state)
        self.assertIn("function isDirty()", self.state)
        self.assertIn("invalidatePending", self.state)
        for forbidden in ("frappe.", "document.", "$(", "System Manager", "Production Manager"):
            self.assertNotIn(forbidden, self.state)

    def test_controller_consumes_adapters_and_has_no_transport_or_inline_css(self) -> None:
        self.assertIn("AlmdinaFactoryPermissionsApi", self.controller)
        self.assertIn("AlmdinaFactoryPermissionsState", self.controller)
        self.assertIn("AlmdinaPageRevisit", self.controller)
        self.assertIn("requests.role.begin", self.controller)
        self.assertIn("requests.preview.begin", self.controller)
        self.assertIn("requests.transfer.begin", self.controller)
        self.assertIn("lifecycle.timeout", self.controller)
        self.assertIn("requires_self_lockout_confirmation", self.controller)
        self.assertIn("previewImport", self.controller)
        self.assertIn("updateRole", self.controller)
        self.assertNotIn("frappe.call(", self.controller)
        self.assertNotIn("permission_management_service", self.controller)
        self.assertNotIn("style.textContent", self.controller)
        self.assertNotIn("roleRequest", self.controller)
        self.assertNotIn("previewRequest", self.controller)
        self.assertNotIn("transferRequest", self.controller)

    def test_feature_styles_are_external_and_preserve_existing_surface_contract(self) -> None:
        for selector in (
            ".apc-shell",
            ".apc-role-picker",
            ".apc-capability",
            ".apc-savebar",
            "@media(max-width:650px)",
        ):
            self.assertIn(selector, self.css)
        self.assertNotIn("<style", self.controller)


if __name__ == "__main__":
    unittest.main()
