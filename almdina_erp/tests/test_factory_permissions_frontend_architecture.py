from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js"
API = ROOT / "public" / "js" / "factory_permissions" / "api.js"
STATE = ROOT / "public" / "js" / "factory_permissions" / "state.js"
VIEW_MODEL = ROOT / "public" / "js" / "factory_permissions" / "view_model.js"
RENDERER = ROOT / "public" / "js" / "factory_permissions" / "renderer.js"
INTERACTIONS = ROOT / "public" / "js" / "factory_permissions" / "interactions.js"
DIALOGS = ROOT / "public" / "js" / "factory_permissions" / "dialogs.js"
CONTROLLER = ROOT / "public" / "js" / "factory_permissions" / "controller.js"
CSS = ROOT / "public" / "css" / "factory_permissions.css"


class FactoryPermissionsFrontendArchitectureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.api = API.read_text(encoding="utf-8")
        cls.state = STATE.read_text(encoding="utf-8")
        cls.view_model = VIEW_MODEL.read_text(encoding="utf-8")
        cls.renderer = RENDERER.read_text(encoding="utf-8")
        cls.interactions = INTERACTIONS.read_text(encoding="utf-8")
        cls.dialogs = DIALOGS.read_text(encoding="utf-8")
        cls.controller = CONTROLLER.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")

    def test_page_entry_is_a_thin_composition_root(self) -> None:
        self.assertLessEqual(len(self.page.splitlines()), 100)
        self.assertIn("frappe.ui.make_app_page", self.page)
        self.assertIn("frontend.ensureStylesheet", self.page)
        for asset in (
            "api.js",
            "state.js",
            "view_model.js",
            "renderer.js",
            "interactions.js",
            "dialogs.js",
            "controller.js",
        ):
            self.assertIn(f"/assets/almdina_erp/js/factory_permissions/{asset}", self.page)
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
            "search_permission_roles",
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

    def test_view_model_owns_pure_derived_presentation_data(self) -> None:
        for symbol in (
            "completeCatalog",
            "capabilityKeys",
            "groupCapabilityKeys",
            "roleMenu",
            "permissionGroups",
            "bulkControls",
            "stats",
            "impact",
            "audit",
        ):
            self.assertIn(symbol, self.view_model)
        for forbidden in (
            "frappe.",
            "document.",
            "$(",
            ".html(",
            "AlmdinaFactoryPermissionsApi",
            "permission_management_service",
        ):
            self.assertNotIn(forbidden, self.view_model)

    def test_renderer_owns_factory_permissions_dom_without_transport(self) -> None:
        for marker in (
            "apc-shell",
            "apc-role-mount",
            "mountRoleControl",
            "roleSearchQuery",
            "apc-capability",
            "apc-impact-panel",
            "apc-audit-panel",
            "apc-savebar",
            "URL.createObjectURL",
        ):
            self.assertIn(marker, self.renderer)
        for forbidden in (
            "AlmdinaFactoryPermissionsApi",
            "permission_management_service",
            "frappe.call(",
            "requests.role",
            "requests.preview",
            "requests.transfer",
            "apc-role-picker",
            'role="combobox"',
            "apc-role-menu",
        ):
            self.assertNotIn(forbidden, self.renderer)

    def test_interactions_own_delegated_events_without_business_state_or_api(self) -> None:
        self.assertIn('EVENT_NAMESPACE = ".almdinaFactoryPermissions"', self.interactions)
        self.assertIn("onCapabilityChanged", self.interactions)
        self.assertIn("onGroupToggle", self.interactions)
        self.assertIn("onGlobalToggle", self.interactions)
        self.assertIn("onImport", self.interactions)
        self.assertNotIn("apc-import-file", self.interactions)
        self.assertNotIn("apc-role-picker", self.interactions)
        self.assertNotIn("ArrowDown", self.interactions)
        self.assertIn("lifecycle.track", self.interactions)
        for forbidden in (
            "AlmdinaFactoryPermissionsApi",
            "AlmdinaFactoryPermissionsState",
            "permission_management_service",
            "frappe.call(",
            "state.working",
            "state.selectedRole",
        ):
            self.assertNotIn(forbidden, self.interactions)

    def test_dialogs_own_import_attach_dialog(self) -> None:
        self.assertIn("new frappe.ui.Dialog", self.dialogs)
        self.assertIn('fieldtype: "Attach"', self.dialogs)
        self.assertIn("permissions_file", self.dialogs)
        self.assertIn("processImportFile", self.dialogs)
        self.assertIn("fetchAttachPayload", self.dialogs)
        self.assertNotIn("frappe.call(", self.dialogs)
        self.assertNotIn("permission_management_service", self.dialogs)

    def test_controller_is_a_thin_orchestrator_over_extracted_modules(self) -> None:
        self.assertLessEqual(len(self.controller.splitlines()), 540)
        for dependency in (
            "AlmdinaFactoryPermissionsApi",
            "AlmdinaFactoryPermissionsState",
            "AlmdinaFactoryPermissionsViewModel",
            "AlmdinaFactoryPermissionsRenderer",
            "AlmdinaFactoryPermissionsInteractions",
            "AlmdinaFactoryPermissionsDialogs",
            "AlmdinaPageRevisit",
        ):
            self.assertIn(dependency, self.controller)
        self.assertIn("requests.role.begin", self.controller)
        self.assertIn("requests.console.begin", self.controller)
        self.assertIn("requests.preview.begin", self.controller)
        self.assertIn("requests.transfer.begin", self.controller)
        self.assertIn("lifecycle.timeout", self.controller)
        self.assertIn("requires_self_lockout_confirmation", self.controller)
        self.assertIn("previewImport", self.controller)
        self.assertIn("updateRole", self.controller)
        self.assertIn("bindActivationLifecycle", self.controller)
        self.assertIn("activation.generation()", self.controller)
        self.assertIn("ownedTransients", self.controller)
        self.assertIn("dialogs.openImportDialog", self.controller)
        self.assertIn("mountRoleControl", self.controller)
        self.assertIn("disposeRoleControl", self.controller)
        self.assertIn("renderer.disposeRoleControl();", self.controller)
        self.assertIn("featureShellReady = false;", self.controller)
        self.assertIn("api.roleSearchQuery", self.controller)
        self.assertIn("reconcileAfterSave", self.controller)
        self.assertNotIn("frappe.ui.make_app_page", self.controller)
        self.assertNotIn("frappe.call(", self.controller)
        self.assertNotIn("permission_management_service", self.controller)
        self.assertNotIn("style.textContent", self.controller)
        self.assertNotIn("roleRequest", self.controller)
        self.assertNotIn("previewRequest", self.controller)
        self.assertNotIn("transferRequest", self.controller)
        self.assertNotIn(".html(", self.controller)
        self.assertNotIn('role="combobox"', self.controller)

    def test_renderer_uses_central_design_system_for_buttons(self) -> None:
        self.assertIn('class="almdina-ui apc-shell"', self.renderer)
        self.assertIn("AlmdinaUi.button", self.renderer)
        self.assertNotIn('class="btn btn-primary apc-save"', self.renderer)
        self.assertNotIn('type="file"', self.renderer)
        self.assertNotIn("apc-import-file", self.renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.page)

    def test_feature_styles_are_external_and_preserve_existing_surface_contract(self) -> None:
        for selector in (
            ".apc-shell",
            ".apc-role-mount",
            ".apc-capability",
            ".apc-savebar",
            "@media(max-width:650px)",
        ):
            self.assertIn(selector, self.css)
        self.assertNotIn(".apc-role-picker", self.css)
        self.assertNotIn("<style", self.controller)
        self.assertNotIn("<style", self.renderer)


if __name__ == "__main__":
    unittest.main()
