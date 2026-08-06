from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
DOMAIN = APP / "domain" / "security" / "workforce.py"
APPLICATION = APP / "application" / "security" / "workforce_management.py"
REPOSITORY = APP / "infrastructure" / "frappe" / "workforce_repository.py"
SERVICE = APP / "services" / "workforce_service.py"
PROVISION = APP / "application" / "security" / "provision_user.py"
PAGE = APP / "page" / "factory_workforce" / "factory_workforce.js"
PAGE_JSON = PAGE.with_suffix(".json")
AUDIT_JSON = (
    APP
    / "doctype"
    / "almdina_user_audit"
    / "almdina_user_audit.json"
)
WORKSPACE = APP / "workspace" / "almdina_settings" / "almdina_settings.json"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"


class TestWorkforceManagementArchitecture(unittest.TestCase):
    def test_domain_and_application_have_no_framework_dependency(self) -> None:
        source = DOMAIN.read_text(encoding="utf-8") + APPLICATION.read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("frappe.db", source)

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
        self.assertNotIn("System Manager", source)
        self.assertNotIn("Production Manager", source)
        self.assertNotIn("Accounts Management", source)
        self.assertNotIn("عامل رسم", source)

    def test_legacy_provisioner_is_only_a_clean_facade(self) -> None:
        source = PROVISION.read_text(encoding="utf-8")
        self.assertIn("workforce_provisioning_service", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("update_password", source)
        self.assertNotIn("frappe.get_doc", source)

    def test_workforce_page_uses_dynamic_multi_role_selection(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        metadata = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
        self.assertEqual(metadata["roles"], [])
        self.assertIn("get_workforce_console", source)
        self.assertIn("create_workforce_user", source)
        self.assertIn("update_workforce_user", source)
        self.assertIn("reset_workforce_password", source)
        self.assertIn("get_workforce_user_audit", source)
        self.assertIn("requestId", source)
        self.assertIn("@media(max-width:600px)", source)
        self.assertIn('fieldtype:"Password"', source)
        self.assertIn('fieldtype:"MultiSelectList"', source)
        self.assertIn('fieldname:"roles"', source)
        self.assertIn("workforce_roles", source)
        self.assertNotIn('fieldname:"profile"', source)
        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("frappe.get_roles", source)
        self.assertNotIn('set_route("Form", "User"', source)

    def test_role_replacement_preserves_unmanaged_technical_roles(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("managed_role_names", repository)
        self.assertIn("Almdina Role Metadata", repository)
        self.assertIn("if row.role not in managed_roles", repository)
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

    def test_workspace_and_shared_shell_use_workforce_capability(self) -> None:
        workspace = WORKSPACE.read_text(encoding="utf-8")
        shell = SHARED_SHELL.read_text(encoding="utf-8")
        self.assertIn("factory-workforce", workspace)
        self.assertIn("factory-workforce", shell)
        self.assertIn('any: ["view_users", "manage_users"]', shell)
        self.assertNotIn("frappe.user_roles", shell)


if __name__ == "__main__":
    unittest.main()
