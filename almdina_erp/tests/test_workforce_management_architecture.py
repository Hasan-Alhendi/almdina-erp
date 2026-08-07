from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
DOMAIN = APP / "domain" / "security" / "workforce.py"
APPLICATION = APP / "application" / "security" / "workforce_management.py"
REPOSITORY = APP / "infrastructure" / "frappe" / "workforce_repository.py"
REGISTRY = APP / "infrastructure" / "frappe" / "managed_role_registry.py"
SERVICE = APP / "services" / "workforce_service.py"
PROVISION = APP / "application" / "security" / "provision_user.py"
PROVISION_SERVICE = APP / "services" / "workforce_provisioning_service.py"
PAGE = APP / "page" / "factory_workforce" / "factory_workforce.js"
PAGE_JSON = PAGE.with_suffix(".json")
AUDIT_JSON = APP / "doctype" / "almdina_user_audit" / "almdina_user_audit.json"
WORKSPACE = APP / "workspace" / "almdina_settings" / "almdina_settings.json"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"


class TestWorkforceManagementArchitecture(unittest.TestCase):
    def test_domain_and_application_have_no_framework_dependency(self) -> None:
        source = DOMAIN.read_text(encoding="utf-8") + APPLICATION.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("frappe.db", source)

    def test_runtime_uses_roles_only_and_has_no_operational_profile_model(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                DOMAIN,
                APPLICATION,
                REPOSITORY,
                SERVICE,
                PROVISION,
                PROVISION_SERVICE,
                PAGE,
            )
        )
        for token in (
            "OperationalProfile",
            "PROFILES",
            "profile_for_key",
            "infer_profile",
            "assign_profile",
            "ASSIGN_PROFILE",
            "assign_workforce_profile",
            'fieldname:"profile"',
            '"profile":',
        ):
            self.assertNotIn(token, source)
        self.assertIn("ASSIGN_USER_ROLES", DOMAIN.read_text(encoding="utf-8"))
        self.assertIn('fieldname:"roles"', PAGE.read_text(encoding="utf-8"))
        self.assertIn("roles=roles", PROVISION.read_text(encoding="utf-8"))

    def test_frappe_user_writes_and_password_updates_are_isolated(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("FrappeWorkforceRepository", service)
        self.assertIn("update_password", repository)
        self.assertIn("`tabUser`", repository)
        self.assertIn('"Almdina User Audit"', repository)
        self.assertNotIn("update_password", service)
        self.assertNotIn("frappe.db.sql", service)

    def test_active_service_has_no_business_role_gates(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("WorkforceAction", source)
        self.assertIn("granted_capabilities", source)
        self.assertNotIn("frappe.get_roles", source)
        for role in ("System Manager", "Production Manager", "Accounts Management", "عامل رسم"):
            self.assertNotIn(role, source)

    def test_provisioning_is_roles_only_and_delegates_to_secured_workforce_service(self) -> None:
        facade = PROVISION.read_text(encoding="utf-8")
        service = PROVISION_SERVICE.read_text(encoding="utf-8")
        self.assertIn("workforce_provisioning_service", facade)
        self.assertIn("create_workforce_user", service)
        self.assertIn("update_workforce_user", service)
        self.assertIn('"roles": selected_roles', service)
        self.assertNotIn("profile", facade.lower())
        self.assertNotIn("profile", service.lower())
        self.assertNotIn("import frappe", facade)
        self.assertNotIn("update_password", facade)

    def test_workforce_page_uses_dynamic_multi_role_selection(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        metadata = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(metadata["roles"], [])
        for endpoint in (
            "get_workforce_console",
            "create_workforce_user",
            "update_workforce_user",
            "reset_workforce_password",
            "get_workforce_user_audit",
        ):
            self.assertIn(endpoint, source)
        self.assertIn("requestId", source)
        self.assertIn("@media(max-width:600px)", source)
        self.assertIn('fieldtype:"Password"', source)
        self.assertIn('fieldtype:"MultiSelectList"', source)
        self.assertIn('fieldname:"roles"', source)
        self.assertIn("workforce_roles", source)
        self.assertNotIn("assign_profile", source)
        self.assertNotIn("manage_users", source)
        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("frappe.get_roles", source)
        self.assertNotIn('set_route("Form", "User"', source)

    def test_role_replacement_preserves_unmanaged_technical_roles(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        registry = REGISTRY.read_text(encoding="utf-8")
        self.assertIn("managed_role_names", repository)
        self.assertIn("managed_role_metadata", repository)
        self.assertIn('ROLE_METADATA_DOCTYPE = "Almdina Role Metadata"', registry)
        self.assertIn("if row.role not in managed", repository)
        self.assertIn("required = list(dict.fromkeys", repository)
        self.assertNotIn('user.set("roles", roles)', repository)

    def test_audit_is_append_only_private_and_password_free(self) -> None:
        metadata = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        controller = AUDIT_JSON.with_suffix(".py").read_text(encoding="utf-8")
        repository = REPOSITORY.read_text(encoding="utf-8")
        application = APPLICATION.read_text(encoding="utf-8")
        self.assertEqual(metadata["permissions"], [])
        self.assertEqual(metadata["allow_rename"], 0)
        self.assertIn("User audit records are immutable", controller)
        self.assertIn("audit_snapshot", repository)
        self.assertIn('"roles": roles', application)
        self.assertNotIn('"temporary_password":', repository)
        self.assertNotIn('"new_password":', repository)
        self.assertNotIn("Profile Changed", metadata["fields"][1]["options"])

    def test_workspace_and_shared_shell_use_granular_workforce_capability(self) -> None:
        workspace = WORKSPACE.read_text(encoding="utf-8")
        shell = SHARED_SHELL.read_text(encoding="utf-8")
        self.assertIn("factory-workforce", workspace)
        self.assertIn("factory-workforce", shell)
        self.assertIn('any: ["view_users"]', shell)
        self.assertNotIn("manage_users", shell)
        self.assertNotIn("manage_factory_settings", shell)
        self.assertNotIn("frappe.user_roles", shell)


if __name__ == "__main__":
    unittest.main()
