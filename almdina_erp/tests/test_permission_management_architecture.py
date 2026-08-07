from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "almdina_erp" / "application" / "security" / "permission_matrix.py"
TRANSFER = ROOT / "almdina_erp" / "application" / "security" / "permission_transfer.py"
REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "permission_matrix_repository.py"
SERVICE = ROOT / "almdina_erp" / "services" / "permission_management_service.py"
SETTINGS_SERVICE = ROOT / "almdina_erp" / "services" / "production_settings_service.py"
WORKFORCE_SERVICE = ROOT / "almdina_erp" / "services" / "workforce_service.py"
PROVISION = ROOT / "almdina_erp" / "application" / "security" / "provision_user.py"
PAGE = ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js"
PAGE_JSON = PAGE.with_suffix(".json")
SETTINGS_PAGE_JSON = ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.json"
SETTINGS_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"
AUDIT_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "almdina_permission_audit" / "almdina_permission_audit.json"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"
SETTINGS_WORKSPACE = ROOT / "almdina_erp" / "workspace" / "almdina_settings" / "almdina_settings.json"


class TestPermissionManagementArchitecture(unittest.TestCase):
    def test_pure_matrix_policy_has_no_framework_dependency(self) -> None:
        source = POLICY.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("Custom DocPerm", source)

    def test_transfer_policy_is_framework_independent_and_has_no_templates(self) -> None:
        source = TRANSFER.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("PermissionTemplate", source)
        self.assertNotIn("template_state", source)
        self.assertIn("build_permission_export", source)
        self.assertIn("build_permission_bundle", source)

    def test_frappe_persistence_is_isolated_in_repository(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn('"Custom DocPerm"', repository)
        self.assertIn('"Almdina Permission Audit"', repository)
        self.assertNotIn('frappe.get_doc("Custom DocPerm"', service)
        self.assertNotIn("frappe.db.sql", service)
        self.assertIn("FrappePermissionMatrixRepository", service)

    def test_custom_permission_baseline_preserves_unedited_roles(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("ensure_custom_permission_baseline", repository)
        self.assertIn("setup_custom_perms", repository)
        self.assertIn("_override_from_standard", repository)
        self.assertIn('frappe.db.exists("Custom DocPerm", {"parent": doctype})', repository)

    def test_administration_services_use_capabilities_not_role_names(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SERVICE, SETTINGS_SERVICE, WORKFORCE_SERVICE, PROVISION)
        )
        self.assertIn("MANAGE_PERMISSIONS", combined)
        self.assertIn("decide_settings_update", combined)
        self.assertIn("WorkforceAction", combined)
        self.assertNotIn('require_any_role("Production Manager")', combined)
        self.assertNotIn('"System Manager" not in', combined)
        self.assertNotIn("Only System Manager", combined)

    def test_pages_and_settings_doctype_have_no_fixed_roles(self) -> None:
        permission_page = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        settings_page = json.loads(SETTINGS_PAGE_JSON.read_text(encoding="utf-8"))
        settings_doctype = json.loads(SETTINGS_DOCTYPE.read_text(encoding="utf-8"))
        self.assertEqual(permission_page["roles"], [])
        self.assertEqual(settings_page["roles"], [])
        self.assertEqual(settings_doctype["permissions"], [])

    def test_audit_is_append_only_and_not_directly_exposed(self) -> None:
        metadata = json.loads(AUDIT_DOCTYPE.read_text(encoding="utf-8"))
        controller = AUDIT_DOCTYPE.with_suffix(".py").read_text(encoding="utf-8")
        self.assertEqual(metadata["permissions"], [])
        self.assertEqual(metadata["allow_rename"], 0)
        self.assertIn("Permission audit records are immutable", controller)

    def test_permission_console_has_preview_audit_race_guards_and_no_templates(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("preview_role_permissions", source)
        self.assertIn("update_role_permissions", source)
        self.assertIn("requires_self_lockout_confirmation", source)
        self.assertIn("roleRequest", source)
        self.assertIn("previewRequest", source)
        self.assertIn("schedulePreview", source)
        self.assertIn("apc-savebar", source)
        self.assertIn("تصدير JSON", source)
        self.assertNotIn("preview_permission_template", source)
        self.assertNotIn("apc-template", source)
        self.assertNotIn("templates", service)
        self.assertNotIn("frappe.user_roles", source)
        for role in ("Production Manager", "System Manager", "Order Entry"):
            self.assertNotIn(role, source)

    def test_shared_shell_hides_only_capability_owned_shortcuts(self) -> None:
        source = SHARED_SHELL.read_text(encoding="utf-8")
        self.assertIn("CAPABILITY_ROUTE_RULES", source)
        self.assertIn('any: ["manage_permissions"]', source)
        self.assertIn('any: ["view_users", "manage_users"]', source)
        self.assertIn("view_factory_settings", source)
        self.assertIn("edit_factory_production_controls", source)
        self.assertIn("view_production_routings", source)
        self.assertIn("view_edge_banding_types", source)
        self.assertIn('any: ["approve_order", "reject_order"]', source)
        self.assertIn('any: ["view_operational_reports", "view_financial_reports"]', source)
        self.assertIn("ruleAllowed", source)
        self.assertIn("hideUnauthorizedShortcuts", source)
        self.assertNotIn("frappe.user_roles", source)

    def test_settings_workspace_has_direct_administration_entries(self) -> None:
        workspace = json.loads(SETTINGS_WORKSPACE.read_text(encoding="utf-8"))
        targets = {row["label"]: row["link_to"] for row in workspace["shortcuts"]}
        self.assertEqual(targets["إدارة الأدوار"], "Role")
        self.assertEqual(targets["إدارة المستخدمين"], "factory-workforce")
        self.assertEqual(targets["إدارة الصلاحيات"], "factory-permissions")
        self.assertEqual(targets["إدارة مسارات الإنتاج"], "factory-master-data")
        self.assertIn('routes: ["factory-permissions", "role"]', SHARED_SHELL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
