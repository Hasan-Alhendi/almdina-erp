from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js"
PAGE_JSON = PAGE.with_suffix(".json")
MODULE_ROOT = ROOT / "public" / "js" / "factory_production_settings"
API = MODULE_ROOT / "api.js"
STATE = MODULE_ROOT / "state.js"
VIEW_MODEL = MODULE_ROOT / "view_model.js"
RENDERER = MODULE_ROOT / "renderer.js"
INTERACTIONS = MODULE_ROOT / "interactions.js"
DIALOGS = MODULE_ROOT / "dialogs.js"
CONTROLLER = MODULE_ROOT / "controller.js"
CSS = ROOT / "public" / "css" / "factory_production_settings.css"


class FactoryProductionSettingsFrontendArchitectureTest(unittest.TestCase):
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

    def test_page_is_thin_composition_root(self) -> None:
        self.assertLessEqual(len(self.page.splitlines()), 100)
        self.assertIn("frappe.ui.make_app_page", self.page)
        metadata = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(metadata["roles"], [])
        for asset in (
            "api.js",
            "state.js",
            "view_model.js",
            "renderer.js",
            "interactions.js",
            "dialogs.js",
            "controller.js",
        ):
            self.assertIn(f"/assets/almdina_erp/js/factory_production_settings/{asset}", self.page)
        self.assertIn("/assets/almdina_erp/css/factory_production_settings.css", self.page)
        self.assertIn("frontend.ensureStylesheet", self.page)
        self.assertNotIn("production_settings_service", self.page)
        self.assertNotIn("frappe.call(", self.page)
        self.assertNotIn("style.textContent", self.page)

    def test_api_is_only_transport_owner(self) -> None:
        for endpoint in (
            "get_production_settings",
            "update_production_settings",
            "get_factory_settings_audit",
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

    def test_state_owns_current_snapshot_and_request_lifecycle(self) -> None:
        for marker in (
            "current: {}",
            "createLatestRequestGate",
            "createLifecycleScope",
            "settings:",
            "audit:",
            "function apply(",
            "function dispose(",
        ):
            self.assertIn(marker, self.state)
        for forbidden in ("frappe.", "document.", "$(", ".html(", "production_settings_service"):
            self.assertNotIn(forbidden, self.state)

    def test_view_model_is_pure_and_uses_server_section_editability(self) -> None:
        for marker in (
            "function sectionEditable(",
            "current.permissions.sections",
            "function sections(",
            "function legacy(",
            'section("cutting"',
            'section("costing"',
            'section("production"',
            'section("print_identity"',
        ):
            self.assertIn(marker, self.view_model)
        for forbidden in (
            "frappe.",
            "document.",
            "$(",
            ".html(",
            "production_settings_service",
            "System Manager",
            "Administrator",
        ):
            self.assertNotIn(forbidden, self.view_model)

    def test_renderer_owns_aps_markup_only(self) -> None:
        for marker in (
            "aps-shell",
            "aps-hero",
            "aps-section",
            "aps-permission",
            "aps-legacy",
            "aps-audit",
            "تعديل هذا القسم",
        ):
            self.assertIn(marker, self.renderer)
        for forbidden in (
            "frappe.call(",
            "production_settings_service",
            "AlmdinaFactoryProductionSettingsApi",
            "state.current",
        ):
            self.assertNotIn(forbidden, self.renderer)

    def test_interactions_own_delegated_edit_events(self) -> None:
        self.assertIn('EVENT_NAMESPACE = ".almdinaFactoryProductionSettings"', self.interactions)
        self.assertIn('".aps-edit"', self.interactions)
        self.assertIn("onEditSection", self.interactions)
        self.assertIn("lifecycle.track", self.interactions)
        for forbidden in (
            "frappe.call(",
            "production_settings_service",
            "AlmdinaFactoryProductionSettingsApi",
            "state.current",
        ):
            self.assertNotIn(forbidden, self.interactions)

    def test_dialogs_own_frappe_dialog_fields_and_local_feedback(self) -> None:
        self.assertIn("new frappe.ui.Dialog", self.dialogs)
        for fieldtype in ("Select", "Float", "Currency", "Percent", "Small Text", "Check"):
            self.assertIn(f'fieldtype: "{fieldtype}"', self.dialogs)
        self.assertIn("frappe.msgprint", self.dialogs)
        self.assertIn("frappe.show_alert", self.dialogs)
        self.assertNotIn("frappe.call(", self.dialogs)
        self.assertNotIn("production_settings_service", self.dialogs)

    def test_controller_only_orchestrates_api_state_and_presenters(self) -> None:
        self.assertLessEqual(len(self.controller.splitlines()), 220)
        for dependency in (
            "AlmdinaFactoryProductionSettingsApi",
            "AlmdinaFactoryProductionSettingsState",
            "AlmdinaFactoryProductionSettingsViewModel",
            "AlmdinaFactoryProductionSettingsRenderer",
            "AlmdinaFactoryProductionSettingsInteractions",
            "AlmdinaFactoryProductionSettingsDialogs",
        ):
            self.assertIn(dependency, self.controller)
        self.assertIn("requests.settings.begin", self.controller)
        self.assertIn("requests.audit.begin", self.controller)
        self.assertIn("viewModel.sectionEditable", self.controller)
        self.assertIn("bindActivationLifecycle", self.controller)
        self.assertNotIn("frappe.ui.make_app_page", self.controller)
        self.assertNotIn("frappe.call(", self.controller)
        self.assertNotIn("production_settings_service", self.controller)
        self.assertNotIn(".html(", self.controller)
        self.assertNotIn("aps-section", self.controller)

    def test_styles_are_external_and_responsive_without_visual_pinning(self) -> None:
        for marker in (
            ".aps-shell",
            ".aps-hero",
            ".aps-sections",
            ".aps-section",
            ".aps-legacy",
            "@media(max-width:",
        ):
            self.assertIn(marker, self.css)
        self.assertNotIn("<style", self.renderer)
        self.assertNotIn("<style", self.controller)


if __name__ == "__main__":
    unittest.main()
