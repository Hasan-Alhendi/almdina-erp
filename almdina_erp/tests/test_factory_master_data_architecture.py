from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "almdina_erp" / "domain" / "security" / "factory_settings.py"
SURFACE_POLICY = ROOT / "almdina_erp" / "application" / "security" / "surface_access.py"
SETTINGS_SERVICE = ROOT / "almdina_erp" / "services" / "production_settings_service.py"
MASTER_SERVICE = ROOT / "almdina_erp" / "services" / "master_data_service.py"
AUDIT_ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "master_data_audit.py"
REFERENCE_ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "master_data_references.py"
ROUTING_JSON = ROOT / "almdina_erp" / "doctype" / "production_routing" / "production_routing.json"
ROUTING_CONTROLLER = ROUTING_JSON.with_suffix(".py")
EDGE_JSON = ROOT / "almdina_erp" / "doctype" / "edge_banding_type" / "edge_banding_type.json"
EDGE_CONTROLLER = EDGE_JSON.with_suffix(".py")
SETTINGS_CONTROLLER = ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.py"
AUDIT_JSON = ROOT / "almdina_erp" / "doctype" / "almdina_master_data_audit" / "almdina_master_data_audit.json"
SETTINGS_PAGE = ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js"
SETTINGS_FRONTEND_STATE = ROOT / "public" / "js" / "factory_production_settings" / "state.js"
SETTINGS_FRONTEND_RENDERER = ROOT / "public" / "js" / "factory_production_settings" / "renderer.js"
SETTINGS_FRONTEND_CONTROLLER = ROOT / "public" / "js" / "factory_production_settings" / "controller.js"
SETTINGS_CSS = ROOT / "public" / "css" / "factory_production_settings.css"
MASTER_PAGE = ROOT / "almdina_erp" / "page" / "factory_master_data" / "factory_master_data.js"
MASTER_PAGE_JSON = MASTER_PAGE.with_suffix(".json")
ROUTING_WORKFLOW_CSS = ROOT / "public" / "css" / "factory_routing_workflow.css"
WORKSPACE = ROOT / "almdina_erp" / "workspace" / "almdina_settings" / "almdina_settings.json"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"


class TestFactoryMasterDataArchitecture(unittest.TestCase):
    def test_factory_settings_policy_is_framework_independent(self) -> None:
        source = POLICY.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertIn("SECTION_FIELDS", source)
        self.assertIn("decide_settings_update", source)

    def test_master_doctypes_have_no_fixed_role_grants(self) -> None:
        for path in (ROUTING_JSON, EDGE_JSON):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["permissions"], [])
            self.assertEqual(metadata["allow_rename"], 0)
            self.assertEqual(metadata["track_changes"], 1)

    def test_sensitive_changes_are_audited_and_deletion_checks_references(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROUTING_CONTROLLER, EDGE_CONTROLLER)
        )
        self.assertIn("audit_saved_document", combined)
        self.assertIn("audit_deleted_document", combined)
        self.assertIn("find_link_references", combined)
        self.assertIn("before_trash", combined)
        self.assertIn("DocField", REFERENCE_ADAPTER.read_text(encoding="utf-8"))
        self.assertIn("Almdina Master Data Audit", AUDIT_ADAPTER.read_text(encoding="utf-8"))

    def test_audit_doctype_is_private_and_immutable(self) -> None:
        metadata = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        controller = AUDIT_JSON.with_suffix(".py").read_text(encoding="utf-8")
        self.assertEqual(metadata["permissions"], [])
        self.assertEqual(metadata["allow_rename"], 0)
        self.assertIn("immutable", controller.lower())

    def test_settings_service_is_field_aware_and_role_free(self) -> None:
        source = SETTINGS_SERVICE.read_text(encoding="utf-8")
        self.assertIn("decide_settings_update", source)
        self.assertIn("record_master_data_audit", source)
        self.assertIn("for update", source.lower())
        self.assertNotIn("Production Manager", source)
        self.assertNotIn("System Manager", source)
        self.assertNotIn("frappe.user_roles", source)

    def test_direct_settings_form_write_is_rejected(self) -> None:
        source = SETTINGS_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("Use the Almdina Factory Settings page", source)
        self.assertIn("ignore_permissions", source)

    def test_master_service_uses_allowlist_and_capabilities(self) -> None:
        source = MASTER_SERVICE.read_text(encoding="utf-8")
        self.assertIn("_MASTER_DEFINITIONS", source)
        self.assertIn("require_doctype_capability", source)
        self.assertIn("delete_master_data_record", source)
        self.assertIn("Capability.DELETE_PRODUCTION_ROUTINGS", source)
        self.assertIn("Capability.DELETE_EDGE_BANDING_TYPES", source)
        self.assertNotIn("frappe.user_roles", source)
        for role in ("Production Manager", "System Manager", "Stock Manager", "Order Entry"):
            self.assertNotIn(role, source)

    def test_pages_are_arabic_responsive_and_do_not_read_roles(self) -> None:
        master_metadata = json.loads(MASTER_PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(master_metadata["roles"], [])

        settings_page = SETTINGS_PAGE.read_text(encoding="utf-8")
        settings_state = SETTINGS_FRONTEND_STATE.read_text(encoding="utf-8")
        settings_renderer = SETTINGS_FRONTEND_RENDERER.read_text(encoding="utf-8")
        settings_controller = SETTINGS_FRONTEND_CONTROLLER.read_text(encoding="utf-8")
        settings_css = SETTINGS_CSS.read_text(encoding="utf-8")
        settings_surface = "\n".join(
            (settings_page, settings_state, settings_renderer, settings_controller)
        )

        self.assertIn("factory_production_settings/controller.js", settings_page)
        self.assertIn("createLatestRequestGate", settings_state)
        self.assertIn("requests.settings.begin", settings_controller)
        self.assertIn("الإعدادات الافتراضية للمعمل", settings_renderer)
        self.assertIn("@media", settings_css)
        self.assertNotIn("requestId", settings_surface)
        self.assertNotIn("frappe.user_roles", settings_surface)

        master = MASTER_PAGE.read_text(encoding="utf-8")
        self.assertIn("requestId", master)
        self.assertNotIn("frappe.user_roles", master)
        css = ROUTING_WORKFLOW_CSS.read_text(encoding="utf-8")
        self.assertIn("get_production_routing_console", master)
        self.assertIn("save_production_routing", master)
        self.assertIn("سجل التغييرات", master)
        self.assertIn("سيُرفض الحذف", master)
        self.assertIn("@media", css)

    def test_settings_workspace_uses_consoles_not_raw_single_doctype(self) -> None:
        metadata = json.loads(WORKSPACE.read_text(encoding="utf-8"))
        targets = {row["link_to"] for row in metadata["links"]}
        self.assertIn("factory-production-settings", targets)
        self.assertIn("factory-master-data", targets)
        self.assertNotIn("Almdina ERP Settings", targets)

    def test_shared_shell_uses_granular_configuration_surfaces(self) -> None:
        shell = SHARED_SHELL.read_text(encoding="utf-8")
        surface_policy = SURFACE_POLICY.read_text(encoding="utf-8")

        self.assertIn('surface: "factory_master_data"', shell)
        self.assertIn('surface: "production_routings"', shell)
        self.assertIn('surface: "edge_banding_types"', shell)
        self.assertIn('surface: "factory_settings"', shell)
        self.assertIn("factory-master-data", shell)
        self.assertIn("production-routing", shell)
        self.assertIn("edge-banding-type", shell)
        self.assertIn("factory-production-settings", shell)

        self.assertIn("Capability.VIEW_PRODUCTION_ROUTINGS", surface_policy)
        self.assertIn("Capability.VIEW_EDGE_BANDING_TYPES", surface_policy)
        self.assertIn('sections.get("factory_settings")', surface_policy)
        self.assertIn("can_open_master_data", surface_policy)


if __name__ == "__main__":
    unittest.main()
