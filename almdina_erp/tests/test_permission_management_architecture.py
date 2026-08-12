from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "almdina_erp" / "application" / "security" / "permission_matrix.py"
SUPPORT_POLICY = ROOT / "almdina_erp" / "application" / "security" / "supporting_doctype_permissions.py"
SURFACE_POLICY = ROOT / "almdina_erp" / "application" / "security" / "surface_access.py"
REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "permission_matrix_repository.py"
PROJECTED_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "projected_permission_matrix_repository.py"
SUPPORT_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "supporting_doctype_permission_repository.py"
SYSTEM_ROLE_POLICY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "system_role_policy.py"
WORKFORCE_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "workforce_repository.py"
AUTHORIZATION_GATEWAY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "authorization_gateway.py"
AUTOMATIC_ROLE_CLEANUP = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "automatic_role_permission_cleanup.py"
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
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (POLICY, SUPPORT_POLICY)
        )
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("Custom DocPerm", source)

    def test_frappe_persistence_is_isolated_in_repository(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        projected = PROJECTED_REPOSITORY.read_text(encoding="utf-8")
        support = SUPPORT_REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")

        self.assertIn('"Custom DocPerm"', repository)
        self.assertIn('"Almdina Permission Audit"', repository)
        self.assertIn("FrappePermissionMatrixRepository", projected)
        self.assertIn("SupportingDoctypePermissionRepository", projected)
        self.assertIn('"Custom DocPerm"', support)
        self.assertIn("setup_custom_perms", support)

        self.assertNotIn('frappe.get_doc("Custom DocPerm"', service)
        self.assertNotIn("frappe.db.sql", service)
        self.assertIn("ProjectedPermissionMatrixRepository", service)

    def test_custom_permission_baseline_preserves_unedited_roles(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("ensure_custom_permission_baseline", repository)
        self.assertIn("setup_custom_perms", repository)
        self.assertIn("_override_from_standard", repository)
        self.assertIn('frappe.db.exists("Custom DocPerm", {"parent": doctype})', repository)

    def test_protected_system_roles_have_one_policy_source(self) -> None:
        policy = SYSTEM_ROLE_POLICY.read_text(encoding="utf-8")
        repository = REPOSITORY.read_text(encoding="utf-8")
        workforce = WORKFORCE_REPOSITORY.read_text(encoding="utf-8")
        gateway = AUTHORIZATION_GATEWAY.read_text(encoding="utf-8")
        cleanup = AUTOMATIC_ROLE_CLEANUP.read_text(encoding="utf-8")

        for role in ("All", "Guest", "Desk User", "System Manager"):
            self.assertIn(f'"{role}"', policy)
        self.assertIn("PROTECTED_ROLES = PROTECTED_SYSTEM_ROLES", repository)
        self.assertIn("PROTECTED_ASSIGNMENT_ROLES = PROTECTED_SYSTEM_ROLES", workforce)
        self.assertIn("PROTECTED_SYSTEM_ROLES", gateway)
        self.assertIn("PROTECTED_SYSTEM_ROLES", cleanup)
        self.assertNotIn('PROTECTED_ROLES = frozenset({"All", "Guest", "Desk User"})', repository)
        self.assertNotIn('PROTECTED_ASSIGNMENT_ROLES = frozenset(', workforce)

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

    def test_permission_console_has_preview_audit_and_race_guards(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("preview_role_permissions", source)
        self.assertIn("update_role_permissions", source)
        self.assertIn("requires_self_lockout_confirmation", source)
        self.assertIn("roleRequest", source)
        self.assertIn("previewRequest", source)
        self.assertIn("apc-savebar", source)
        self.assertIn("Promise.resolve(loadPreview()).then", source)
        self.assertIn("const executeSave = async", source)
        self.assertIn("finally {", source)
        self.assertIn("state.saving = false", source)
        self.assertIn("await refreshRuntimePermissions()", source)
        self.assertNotIn(").finally(() => {\n                state.saving = false", source)
        self.assertNotIn("frappe.user_roles", source)
        for role in ("Production Manager", "System Manager", "Order Entry"):
            self.assertNotIn(role, source)

    def test_shared_shell_uses_surface_policy_not_raw_capabilities(self) -> None:
        source = SHARED_SHELL.read_text(encoding="utf-8")
        surface_policy = SURFACE_POLICY.read_text(encoding="utf-8")

        self.assertIn("SURFACE_ROUTE_RULES", source)
        self.assertIn("surfaceAllowed", source)
        self.assertIn('surface: "permissions"', source)
        self.assertIn('surface: "role_admin"', source)
        self.assertIn('surface: "workforce"', source)
        self.assertIn('surface: "factory_settings"', source)
        self.assertIn('surface: "production_routings"', source)
        self.assertIn('surface: "edge_banding_types"', source)
        self.assertIn('surface: "report_factory_order_analysis"', source)
        self.assertIn("hideUnauthorizedShortcuts", source)
        self.assertNotIn("CAPABILITY_ROUTE_RULES", source)
        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("manage_users", source)
        self.assertNotIn("manage_factory_settings", source)

        self.assertIn("Capability.MANAGE_PERMISSIONS", surface_policy)
        self.assertIn("Capability.VIEW_USERS", surface_policy)
        self.assertIn("Capability.VIEW_PRODUCTION_ROUTINGS", surface_policy)
        self.assertIn("Capability.VIEW_EDGE_BANDING_TYPES", surface_policy)
        self.assertIn('sections.get("factory_settings")', surface_policy)

    def test_settings_workspace_has_direct_administration_entries(self) -> None:
        workspace = json.loads(SETTINGS_WORKSPACE.read_text(encoding="utf-8"))
        targets = {row["label"]: row["link_to"] for row in workspace["shortcuts"]}
        self.assertEqual(targets["إدارة الأدوار"], "Role")
        self.assertEqual(targets["إدارة المستخدمين"], "factory-workforce")
        self.assertEqual(targets["إدارة الصلاحيات"], "factory-permissions")
        self.assertEqual(targets["إدارة مسارات الإنتاج"], "factory-master-data")

        shell = SHARED_SHELL.read_text(encoding="utf-8")
        self.assertIn('{ surface: "permissions", routes: ["factory-permissions"] }', shell)
        self.assertIn('surface: "role_admin"', shell)
        self.assertIn('"role"', shell)
        self.assertIn('{ surface: "workforce", routes: ["factory-workforce"] }', shell)


if __name__ == "__main__":
    unittest.main()
