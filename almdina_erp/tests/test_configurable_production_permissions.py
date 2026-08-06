from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_POLICY = ROOT / "almdina_erp" / "domain" / "orders" / "production_authorization.py"
APPLICATION_COMMANDS = ROOT / "almdina_erp" / "application" / "shop_floor" / "commands.py"
COMMAND_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "shop_floor_command_repository.py"
AUTHORIZATION = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "shop_floor_authorization.py"
DISPATCH_SERVICE = ROOT / "almdina_erp" / "services" / "order_dispatch_service.py"
COMMAND_SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"
QUERY_SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_query_service.py"
WORKER_SERVICE = ROOT / "almdina_erp" / "services" / "production_worker_service.py"
ORDER_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"


class TestConfigurableProductionPermissions(unittest.TestCase):
    def test_domain_policy_is_framework_independent(self) -> None:
        source = DOMAIN_POLICY.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertIn("class ProductionActionFacts", source)
        self.assertIn("def decide_production_action", source)
        self.assertIn("def build_production_action_context", source)

    def test_application_commands_depend_on_capabilities_not_role_names(self) -> None:
        source = APPLICATION_COMMANDS.read_text(encoding="utf-8")
        for role in (
            "Order Entry",
            "Production Manager",
            "System Manager",
            "عامل شريون",
            "عامل رسم",
            "عامل CNC",
            "عامل تقشيط",
        ):
            self.assertNotIn(role, source)
        self.assertIn("capabilities_for_order", source)
        self.assertIn("Capability.REASSIGN_WORKER", source)
        self.assertIn("assert_worker_for_roles", source)
        self.assertIn("eligible_roles", source)

    def test_application_commands_use_only_configured_route_navigation(self) -> None:
        source = APPLICATION_COMMANDS.read_text(encoding="utf-8")
        self.assertIn("route.next_stage", source)
        self.assertIn("route.contains", source)
        self.assertNotIn("production_path_sequence(", source)
        self.assertNotIn("next_stage_type(", source)
        self.assertNotIn("def _next_stage", source)
        self.assertNotIn("def _validate_path", source)

    def test_infrastructure_resolves_document_permissions(self) -> None:
        source = COMMAND_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("document_has_capability", source)
        self.assertIn("PRODUCTION_ACTIONS", source)
        self.assertIn("assert_enabled_user_has_any_role", source)
        self.assertNotIn("DISPATCH_ROLES", source)
        self.assertNotIn("ADMIN_ROLES", source)
        self.assertNotIn("require_stage_assignee_or_admin", source)

    def test_stage_roles_define_eligibility_not_action_authorization(self) -> None:
        source = AUTHORIZATION.read_text(encoding="utf-8")
        self.assertIn("WORKER_EXECUTION_CAPABILITIES", source)
        self.assertIn("assert_enabled_user_has_any_role", source)
        self.assertIn("user_roles.intersection(eligible_roles)", source)
        self.assertIn("granted_capabilities", source)
        self.assertEqual(source.count("STAGE_ROLE_BY_TYPE"), 2)
        self.assertIn("STAGE_ROLE_BY_TYPE: dict[str, str] = {}", source)
        for role in ("Production Manager", "عامل رسم", "عامل CNC"):
            self.assertNotIn(role, source)
        self.assertNotIn("DISPATCH_ROLES", source)
        self.assertNotIn("ADMIN_ROLES", source)
        self.assertNotIn("STAGE_ADMIN_ROLES", source)
        self.assertNotIn("def require_roles", source)

    def test_legacy_dispatch_route_uses_the_same_capability(self) -> None:
        source = DISPATCH_SERVICE.read_text(encoding="utf-8")
        self.assertIn("Capability.DISPATCH_ORDER", source)
        self.assertIn("require_document_capability", source)
        self.assertNotIn("require_any_role", source)
        self.assertNotIn("Order Entry", source)
        self.assertNotIn("Production Manager", source)

    def test_reassignment_has_a_thin_server_boundary(self) -> None:
        command_source = COMMAND_SERVICE.read_text(encoding="utf-8")
        worker_source = WORKER_SERVICE.read_text(encoding="utf-8")
        application_source = APPLICATION_COMMANDS.read_text(encoding="utf-8")
        self.assertIn("def reassign_worker", command_source)
        self.assertIn("commands.reassign_worker", command_source)
        self.assertIn("commands.get_reassignment_workers", worker_source)
        self.assertIn("Capability.REASSIGN_WORKER", application_source)
        self.assertNotIn("get_users_for_stage", worker_source)
        self.assertIn("frappe.PermissionError", worker_source)

    def test_query_service_publishes_server_action_context(self) -> None:
        source = QUERY_SERVICE.read_text(encoding="utf-8")
        self.assertIn('"production_actions"', source)
        self.assertIn('"can_reassign_worker"', source)
        self.assertIn('"active_stage_assigned_to"', source)
        self.assertNotIn("DISPATCH_ROLES", source)
        self.assertNotIn("ADMIN_ROLES", source)

    def test_ui_never_uses_reassignment_as_a_stage_override(self) -> None:
        source = ORDER_UX.read_text(encoding="utf-8")
        self.assertNotIn("canOverrideAssignment", source)
        self.assertIn("function openReassignDialog", source)
        self.assertIn("production_worker_service.get_reassignment_workers", source)
        self.assertIn("shop_floor_commands.reassign_worker", source)
        self.assertIn("if (!assignedToMe) return", source)
        self.assertIn("frm.doc.name !== documentName", source)


if __name__ == "__main__":
    unittest.main()
