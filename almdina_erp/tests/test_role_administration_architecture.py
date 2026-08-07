from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "almdina_erp" / "domain" / "security" / "role_management.py"
APPLICATION = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "role_administration.py"
)
REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "role_repository.py"
)
ROUTING_REFERENCES = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "routing_role_references.py"
)
SERVICE = ROOT / "almdina_erp" / "services" / "role_management_service.py"
METADATA = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "almdina_role_metadata"
    / "almdina_role_metadata.json"
)
AUDIT = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "almdina_role_audit"
    / "almdina_role_audit.json"
)
AUDIT_CONTROLLER = AUDIT.with_suffix(".py")


def _function_source(source: str, function_name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    return ast.get_source_segment(source, node) or ""


class TestRoleAdministrationArchitecture(unittest.TestCase):
    def test_domain_and_application_are_framework_independent(self) -> None:
        for path in (DOMAIN, APPLICATION):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("import frappe", source)
            self.assertNotIn("from frappe", source)
            self.assertNotIn("Custom DocPerm", source)
            self.assertNotIn("frappe.db", source)

    def test_application_uses_a_repository_port_and_explicit_use_cases(self) -> None:
        source = APPLICATION.read_text(encoding="utf-8")
        self.assertIn("class RoleAdministrationRepository(Protocol)", source)
        self.assertIn("class RoleAdministration", source)
        for method in (
            "def console(",
            "def create(",
            "def update(",
            "def set_enabled(",
            "def delete(",
            "def audit(",
        ):
            self.assertIn(method, source)
        self.assertIn("new_role_definition", source)
        self.assertIn("decide_role_action", source)
        self.assertIn("permission_count", source)
        self.assertIn("production_routing_references", source)
        self.assertIn("workflow_references", source)

    def test_frappe_writes_are_isolated_in_role_repository(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn('"doctype": "Role"', repository)
        self.assertIn('frappe.rename_doc("Role"', repository)
        self.assertIn('frappe.delete_doc("Role", resolved', repository)
        self.assertIn('"Production Routing Stage"', repository)
        self.assertIn('"Workflow Transition"', repository)
        self.assertIn('"Production Stage"', repository)
        self.assertIn('"Custom DocPerm"', repository)
        self.assertNotIn('frappe.get_doc("Role"', service)
        self.assertNotIn("frappe.db.sql", service)
        self.assertIn("RoleAdministration(_repository)", service)

    def test_role_rename_updates_non_link_routing_snapshots(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        references = ROUTING_REFERENCES.read_text(encoding="utf-8")
        update_block = repository.split("def update_role", 1)[1].split(
            "def set_role_enabled", 1
        )[0]
        self.assertIn("rename_configured_role_references", update_block)
        self.assertIn('"Production Routing Stage"', update_block)
        self.assertIn('"Production Stage"', update_block)
        self.assertIn("def rename_configured_role_references", references)
        self.assertIn('values["eligible_roles_json"]', references)
        self.assertIn('values["eligible_roles_display"]', references)
        self.assertIn('values["operational_role"]', references)

    def test_role_endpoints_use_granular_server_capabilities(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        expected = {
            "get_role_console": "Capability.VIEW_ROLES",
            "get_role_details": "Capability.VIEW_ROLES",
            "create_factory_role": "Capability.CREATE_ROLES",
            "update_factory_role": "Capability.EDIT_ROLES",
            "set_factory_role_enabled": "Capability.EDIT_ROLES",
            "delete_factory_role": "Capability.DELETE_ROLES",
            "get_factory_role_audit": "Capability.VIEW_ROLES",
        }
        for endpoint, capability in expected.items():
            block = _function_source(source, endpoint)
            self.assertIn("_require_role_capability(", block, endpoint)
            self.assertIn(capability, block, endpoint)
        self.assertNotIn("Capability.MANAGE_PERMISSIONS", source)
        self.assertIn("confirm_delete", source)

    def test_new_roles_are_custom_desk_roles_with_no_permission_seed(self) -> None:
        repository = REPOSITORY.read_text(encoding="utf-8")
        create_block = repository.split("def create_role", 1)[1].split(
            "def update_role", 1
        )[0]
        self.assertIn('"desk_access": 1', create_block)
        self.assertIn('"is_custom": 1', create_block)
        self.assertNotIn("DocPerm", create_block)
        self.assertNotIn("permission_template", create_block)
        self.assertNotIn("profile", create_block)

    def test_private_metadata_and_audit_are_not_directly_exposed(self) -> None:
        metadata = json.loads(METADATA.read_text(encoding="utf-8"))
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        controller = AUDIT_CONTROLLER.read_text(encoding="utf-8")
        self.assertEqual(metadata["permissions"], [])
        self.assertEqual(audit["permissions"], [])
        self.assertEqual(metadata["allow_rename"], 0)
        self.assertEqual(audit["allow_rename"], 0)
        self.assertIn("Role audit records are immutable", controller)
        self.assertIn("role_uid", metadata["field_order"])
        self.assertIn("role_uid", audit["field_order"])

    def test_role_lifecycle_has_no_fixed_factory_role_catalog(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (DOMAIN, APPLICATION, REPOSITORY, SERVICE)
        )
        for role in (
            "Order Entry",
            "Production Manager",
            "عامل رسم",
            "عامل CNC",
            "عامل شريون",
            "عامل تقشيط",
        ):
            self.assertNotIn(role, combined)
        self.assertNotIn("PermissionTemplate", combined)
        self.assertNotIn("PERMISSION_TEMPLATES", combined)


if __name__ == "__main__":
    unittest.main()
