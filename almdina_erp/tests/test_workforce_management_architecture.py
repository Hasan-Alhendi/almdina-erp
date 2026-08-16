from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
DOMAIN = APP / "domain" / "security" / "workforce.py"
APPLICATION = APP / "application" / "security" / "workforce_management.py"
APPLICATION_PACKAGE = APP / "application" / "security" / "__init__.py"
SURFACE_POLICY = APP / "application" / "security" / "surface_access.py"
REPOSITORY = APP / "infrastructure" / "frappe" / "workforce_repository.py"
SERVICE = APP / "services" / "workforce_service.py"
PROVISION = APP / "services" / "workforce_provisioning_service.py"
PAGE = APP / "page" / "factory_workforce" / "factory_workforce.js"
PAGE_JSON = PAGE.with_suffix(".json")
WORKFORCE_API = ROOT / "public" / "js" / "factory_workforce" / "api.js"
WORKFORCE_STATE = ROOT / "public" / "js" / "factory_workforce" / "state.js"
WORKFORCE_VIEW_MODEL = ROOT / "public" / "js" / "factory_workforce" / "view_model.js"
WORKFORCE_RENDERER = ROOT / "public" / "js" / "factory_workforce" / "renderer.js"
WORKFORCE_INTERACTIONS = ROOT / "public" / "js" / "factory_workforce" / "interactions.js"
WORKFORCE_DIALOGS = ROOT / "public" / "js" / "factory_workforce" / "dialogs.js"
WORKFORCE_CONTROLLER = ROOT / "public" / "js" / "factory_workforce" / "controller.js"
WORKFORCE_CSS = ROOT / "public" / "css" / "factory_workforce.css"
WORKFORCE_FRONTEND_MODULES = (
    WORKFORCE_API,
    WORKFORCE_STATE,
    WORKFORCE_VIEW_MODEL,
    WORKFORCE_RENDERER,
    WORKFORCE_INTERACTIONS,
    WORKFORCE_DIALOGS,
    WORKFORCE_CONTROLLER,
)
AUDIT_JSON = APP / "doctype" / "almdina_user_audit" / "almdina_user_audit.json"
WORKSPACE = APP / "workspace" / "almdina_settings" / "almdina_settings.json"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"


def _workforce_browser_surface() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PAGE, *WORKFORCE_FRONTEND_MODULES)
    )


class TestWorkforceManagementArchitecture(unittest.TestCase):
    def test_domain_and_application_have_no_framework_dependency(self) -> None:
        source = DOMAIN.read_text(encoding="utf-8") + APPLICATION.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("frappe.db", source)
        self.assertNotIn("OperationalProfile", source)
        self.assertNotIn("PROFILES", source)

    def test_frappe_user_writes_and_password_updates_are_isolated(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("FrappeWorkforceRepository", service)
        self.assertIn("update_password", repository)
        self.assertIn("`tabUser`", repository)
        self.assertIn('"Almdina User Audit"', repository)
        self.assertNotIn("update_password", service)
        self.assertNotIn("frappe.db.sql", service)

    def test_active_service_has_no_business_role_gates_or_profiles(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("WorkforceAction", source)
        self.assertIn("granted_capabilities", source)
        self.assertIn("assign_user_roles", (APP / "domain" / "security" / "authorization.py").read_text(encoding="utf-8"))
        self.assertNotIn("frappe.get_roles", source)
        self.assertNotIn("OperationalProfile", source)
        self.assertNotIn("profile_for_key", source)
        self.assertNotIn("manage_users", source)

    def test_provisioner_accepts_roles_not_profiles(self) -> None:
        source = PROVISION.read_text(encoding="utf-8")
        application_package = APPLICATION_PACKAGE.read_text(encoding="utf-8")
        self.assertIn("roles: Sequence[str]", source)
        self.assertIn("FrappeWorkforceRepository", source)
        self.assertIn("create_workforce_user", source)
        self.assertNotIn("profile:", source)
        self.assertNotIn("PROFILES", source)
        self.assertNotIn('"PROFILES"', application_package)
        self.assertNotIn('"provision_user"', application_package)
        self.assertFalse((APP / "application" / "security" / "provision_user.py").exists())

    def test_workforce_page_is_role_driven_responsive_and_race_safe(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        api = WORKFORCE_API.read_text(encoding="utf-8")
        state = WORKFORCE_STATE.read_text(encoding="utf-8")
        view_model = WORKFORCE_VIEW_MODEL.read_text(encoding="utf-8")
        renderer = WORKFORCE_RENDERER.read_text(encoding="utf-8")
        dialogs = WORKFORCE_DIALOGS.read_text(encoding="utf-8")
        controller = WORKFORCE_CONTROLLER.read_text(encoding="utf-8")
        css = WORKFORCE_CSS.read_text(encoding="utf-8")
        surface = _workforce_browser_surface()
        metadata = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(metadata["roles"], [])

        for endpoint in (
            "get_workforce_console",
            "create_workforce_user",
            "adopt_workforce_user",
            "update_workforce_user",
            "reset_workforce_password",
            "get_workforce_user_audit",
        ):
            self.assertIn(endpoint, api)
        self.assertIn('fieldtype: "MultiSelectList"', dialogs)
        self.assertIn("assign_user_roles", view_model)
        self.assertIn("availableUsers", state)
        self.assertIn("مستخدمون غير مضافين إلى المعمل", renderer)
        self.assertIn("إضافة إلى المعمل", renderer)
        self.assertIn("لا تمنحه أي دور أو صلاحية تشغيلية تلقائيًا", renderer)
        self.assertIn("createLatestRequestGate", state)
        self.assertIn("requests.console.begin", controller)
        self.assertIn("@media(max-width:600px)", css)
        self.assertIn('fieldtype: "Password"', dialogs)
        self.assertIn("factory_workforce/controller.js", page)
        self.assertNotIn("requestId", surface)
        self.assertNotIn("profileOptions", surface)
        self.assertNotIn("profile_label", surface)
        self.assertNotIn("manage_users", surface)
        self.assertNotIn("frappe.user_roles", surface)
        self.assertNotIn("frappe.get_roles", surface)

    def test_audit_is_append_only_private_and_password_free(self) -> None:
        metadata = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        controller = AUDIT_JSON.with_suffix(".py").read_text(encoding="utf-8")
        repository = REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertEqual(metadata["permissions"], [])
        self.assertEqual(metadata["allow_rename"], 0)
        self.assertIn("User audit records are immutable", controller)
        self.assertIn("audit_snapshot", repository)
        self.assertNotIn('"temporary_password":', repository)
        self.assertNotIn('"new_password":', repository)

        action_field = next(
            field for field in metadata["fields"] if field["fieldname"] == "action"
        )
        allowed_actions = {
            option.strip()
            for option in str(action_field["options"]).split("\n")
            if option.strip()
        }
        self.assertIn("Added to Workforce", allowed_actions)
        self.assertIn('action="Added to Workforce"', service)
        for token in (
            'action="Created"',
            'action="Identity Updated"',
            'action="Roles Changed"',
            'action="Password Reset"',
        ):
            action_name = token.split('"')[1]
            self.assertIn(action_name, allowed_actions)

    def test_workspace_and_shared_shell_expose_workforce_by_surface_policy(self) -> None:
        workspace = WORKSPACE.read_text(encoding="utf-8")
        shell = SHARED_SHELL.read_text(encoding="utf-8")
        surface_policy = SURFACE_POLICY.read_text(encoding="utf-8")

        self.assertIn("factory-workforce", workspace)
        self.assertIn('{ surface: "workforce", routes: ["factory-workforce"] }', shell)
        self.assertIn("Capability.VIEW_USERS", surface_policy)
        self.assertNotIn('"view_users"', shell)
        self.assertNotIn("frappe.user_roles", shell)

    def test_repository_uses_explicit_scope_and_safe_adoption(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("list_assignable_roles", repository)
        self.assertIn("validate_roles", repository)
        self.assertIn("list_available_users", repository)
        self.assertIn("adopt_user", repository)
        self.assertIn("coalesce(u.default_app, '') = 'almdina_erp'", repository)
        self.assertIn("coalesce(u.default_app, '') != 'almdina_erp'", repository)
        self.assertIn('if role != "System Manager"', repository)
        self.assertNotIn("RETAINED_SYSTEM_ROLES", repository)
        self.assertIn("Capability.CREATE_USERS in granted", service)
        self.assertIn("دون منحه أي دور مصنع تلقائيًا", service)
        self.assertNotIn("MANAGED_OPERATIONAL_ROLES", repository)
        self.assertNotIn("infer_profile", repository)


if __name__ == "__main__":
    unittest.main()
