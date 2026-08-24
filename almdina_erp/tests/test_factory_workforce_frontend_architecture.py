from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_workforce" / "factory_workforce.js"
API = ROOT / "public" / "js" / "factory_workforce" / "api.js"
STATE = ROOT / "public" / "js" / "factory_workforce" / "state.js"
VIEW_MODEL = ROOT / "public" / "js" / "factory_workforce" / "view_model.js"
RENDERER = ROOT / "public" / "js" / "factory_workforce" / "renderer.js"
INTERACTIONS = ROOT / "public" / "js" / "factory_workforce" / "interactions.js"
DIALOGS = ROOT / "public" / "js" / "factory_workforce" / "dialogs.js"
CONTROLLER = ROOT / "public" / "js" / "factory_workforce" / "controller.js"
CSS = ROOT / "public" / "css" / "factory_workforce.css"


class FactoryWorkforceFrontendArchitectureTest(unittest.TestCase):
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

    def test_page_is_a_thin_composition_root(self) -> None:
        self.assertLessEqual(len(self.page.splitlines()), 100)
        self.assertIn("frappe.ui.make_app_page", self.page)
        for asset in (
            "api.js",
            "state.js",
            "view_model.js",
            "renderer.js",
            "interactions.js",
            "dialogs.js",
            "controller.js",
        ):
            self.assertIn(f"/assets/almdina_erp/js/factory_workforce/{asset}", self.page)
        self.assertIn("/assets/almdina_erp/css/factory_workforce.css", self.page)
        self.assertIn("frontend.ensureStylesheet", self.page)
        self.assertNotIn("frappe.call(", self.page)
        self.assertNotIn("workforce_service", self.page)
        self.assertNotIn("style.textContent", self.page)
        self.assertNotIn("class AlmdinaWorkforceConsole", self.page)

    def test_api_is_the_only_workforce_transport_owner(self) -> None:
        for endpoint in (
            "get_workforce_console",
            "create_workforce_user",
            "adopt_workforce_user",
            "update_workforce_user",
            "reset_workforce_password",
            "set_workforce_user_enabled",
            "get_workforce_user_audit",
        ):
            self.assertIn(endpoint, self.api)
            for other in (
                self.page,
                self.state,
                self.view_model,
                self.renderer,
                self.interactions,
                self.dialogs,
                self.controller,
            ):
                self.assertNotIn(endpoint, other)
        self.assertIn("foundation().rpc", self.api)
        for forbidden in ("document.", "$(", ".html(", "frappe.call("):
            self.assertNotIn(forbidden, self.api)

    def test_state_owns_mutable_data_and_request_lifecycle(self) -> None:
        for marker in (
            "users: []",
            "availableUsers: []",
            "permissions: {}",
            "summary: {}",
            "createLatestRequestGate",
            "createLifecycleScope",
            "requests",
            "applyConsole",
            "dispose",
        ):
            self.assertIn(marker, self.state)
        for forbidden in ("frappe.", "document.", "$(", ".html(", "workforce_service"):
            self.assertNotIn(forbidden, self.state)

    def test_view_model_is_pure_and_server_action_driven(self) -> None:
        for marker in (
            "function can(",
            "function actionAllowed(",
            "function roleOptions(",
            "function summaryCards(",
            "function userModel(",
            "function availableUserModel(",
            "user.actions",
        ):
            self.assertIn(marker, self.view_model)
        for forbidden in (
            "frappe.",
            "document.",
            "$(",
            ".html(",
            "workforce_service",
            "System Manager",
            "Administrator",
        ):
            self.assertNotIn(forbidden, self.view_model)

    def test_renderer_owns_existing_aw_surface_without_transport(self) -> None:
        for marker in (
            "aw-shell",
            "aw-toolbar",
            "aw-summary",
            "aw-card",
            "aw-audit",
            "مستخدمو المعمل",
            "مستخدمون غير مضافين إلى المعمل",
            "إضافة إلى المعمل",
        ):
            self.assertIn(marker, self.renderer)
        for forbidden in (
            "frappe.call(",
            "workforce_service",
            "AlmdinaFactoryWorkforceApi",
            "state.permissions",
        ):
            self.assertNotIn(forbidden, self.renderer)

    def test_interactions_own_delegated_events_and_search_timer(self) -> None:
        self.assertIn('EVENT_NAMESPACE = ".almdinaFactoryWorkforce"', self.interactions)
        self.assertIn("lifecycle.timeout", self.interactions)
        self.assertIn("350", self.interactions)
        for callback in (
            "onSearch",
            "onEnabledChanged",
            "onRefresh",
            "onEdit",
            "onPassword",
            "onToggle",
            "onAudit",
            "onAdopt",
        ):
            self.assertIn(callback, self.interactions)
        for forbidden in (
            "frappe.call(",
            "workforce_service",
            "AlmdinaFactoryWorkforceApi",
            "state.users",
            "state.permissions",
        ):
            self.assertNotIn(forbidden, self.interactions)

    def test_dialogs_own_frappe_dialog_presentation_not_transport(self) -> None:
        self.assertIn("new frappe.ui.Dialog", self.dialogs)
        self.assertIn('fieldtype: "MultiSelectList"', self.dialogs)
        self.assertIn('fieldtype: "Password"', self.dialogs)
        self.assertIn("frappe.confirm", self.dialogs)
        self.assertIn("frappe.show_alert", self.dialogs)
        self.assertIn("ownedSurfaces", self.dialogs)
        self.assertIn("drafts", self.dialogs)
        self.assertIn("surface.get_values(true)", self.dialogs)
        self.assertIn("function deactivate()", self.dialogs)
        for forbidden in (
            "frappe.call(",
            "workforce_service",
            "AlmdinaFactoryWorkforceApi",
            "state.permissions",
        ):
            self.assertNotIn(forbidden, self.dialogs)

    def test_controller_is_orchestration_only(self) -> None:
        self.assertLessEqual(len(self.controller.splitlines()), 310)
        for dependency in (
            "AlmdinaFactoryWorkforceApi",
            "AlmdinaFactoryWorkforceState",
            "AlmdinaFactoryWorkforceViewModel",
            "AlmdinaFactoryWorkforceRenderer",
            "AlmdinaFactoryWorkforceInteractions",
            "AlmdinaFactoryWorkforceDialogs",
        ):
            self.assertIn(dependency, self.controller)
        self.assertIn("requests.console.begin", self.controller)
        self.assertIn("requests.audit.begin", self.controller)
        self.assertIn("actionAllowed(user", self.controller)
        self.assertIn("bindActivationLifecycle", self.controller)
        self.assertIn("activation.generation()", self.controller)
        self.assertIn("runMutation", self.controller)
        self.assertNotIn("frappe.ui.make_app_page", self.controller)
        self.assertNotIn("frappe.call(", self.controller)
        self.assertNotIn("workforce_service", self.controller)
        self.assertNotIn(".html(", self.controller)
        self.assertNotIn("aw-card", self.controller)
        self.assertNotIn("style.textContent", self.controller)

    def test_styles_are_external_and_responsive_without_visual_pinning(self) -> None:
        for selector in (
            ".aw-shell",
            ".aw-toolbar",
            ".aw-summary",
            ".aw-card",
            ".aw-audit",
            "@media(max-width:",
        ):
            self.assertIn(selector, self.css)
        self.assertNotIn("<style", self.renderer)
        self.assertNotIn("<style", self.controller)


if __name__ == "__main__":
    unittest.main()
