from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_POLICY = ROOT / "almdina_erp" / "domain" / "orders" / "production_authorization.py"
APPLICATION_COMMANDS = ROOT / "almdina_erp" / "application" / "shop_floor" / "commands.py"
COMMAND_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "shop_floor_command_repository.py"
AUTHORIZATION = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "shop_floor_authorization.py"
ORDER_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "order_tracking_repository.py"
STAGE_REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "production_stage_repository.py"
ROUTING_CONTROLLER = ROOT / "almdina_erp" / "doctype" / "production_routing" / "production_routing.py"
MASTER_DATA = ROOT / "almdina_erp" / "services" / "master_data_service.py"
FACTORY_SCOPE = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "factory_user_scope.py"
DISPATCH_SERVICE = ROOT / "almdina_erp" / "services" / "order_dispatch_service.py"
COMMAND_SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"
QUERY_SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_query_service.py"
WORKER_SERVICE = ROOT / "almdina_erp" / "services" / "production_worker_service.py"
ORDER_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"


class TestConfigurableProductionPermissions(unittest.TestCase):
    def test_domain_policy_is_framework_independent_and_stage_name_agnostic(self) -> None:
        source = DOMAIN_POLICY.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn('stage_type == "Drawing"', source)
        self.assertNotIn("dxf_not_approved", source)
        self.assertIn("class ProductionActionFacts", source)
        self.assertIn("def decide_production_action", source)
        self.assertIn("def build_production_action_context", source)

    def test_application_commands_depend_on_capabilities_and_route_data_not_role_names(self) -> None:
        source = APPLICATION_COMMANDS.read_text(encoding="utf-8")
        for forbidden in (
            "Order Entry",
            "Production Manager",
            "System Manager",
            "عامل شريون",
            "عامل رسم",
            "عامل CNC",
            "عامل تقشيط",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("capabilities_for_order", source)
        self.assertIn("Capability.REASSIGN_WORKER", source)
        self.assertIn("route_stage.is_planning_stage", source)
        self.assertIn("route.requires_approved_plan_before_dispatch", source)

    def test_mutating_use_cases_request_locks_through_the_application_port(self) -> None:
        source = APPLICATION_COMMANDS.read_text(encoding="utf-8")
        self.assertIn("def lock_order", source)
        self.assertIn("def lock_stage", source)
        self.assertIn("repository.lock_order(order_name)", source)
        self.assertIn("repository.lock_stage(stage_name)", source)
        self.assertNotIn("frappe.db.sql", source)
        self.assertNotIn("for update", source.lower())

        order_source = ORDER_REPOSITORY.read_text(encoding="utf-8")
        stage_source = STAGE_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("for update", order_source.lower())
        self.assertIn("for update", stage_source.lower())

    def test_infrastructure_resolves_document_permissions_without_role_gates(self) -> None:
        source = COMMAND_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("document_has_capability", source)
        self.assertIn("PRODUCTION_ACTIONS", source)
        self.assertIn("order_tracking_repository.lock_order", source)
        self.assertIn("production_stage_repository.lock_stage", source)
        self.assertNotIn("DISPATCH_ROLES", source)
        self.assertNotIn("ADMIN_ROLES", source)
        self.assertNotIn("require_stage_assignee_or_admin", source)

    def test_operational_workers_are_factory_scoped_and_role_qualified(self) -> None:
        source = AUTHORIZATION.read_text(encoding="utf-8")
        scope = FACTORY_SCOPE.read_text(encoding="utf-8")
        self.assertIn("assert_enabled_user_has_role", source)
        self.assertIn("get_users_for_role", source)
        self.assertIn("is_almdina_user", source)
        self.assertIn("ALMDINA_APP", source)
        self.assertIn("coalesce(u.default_app, '') = %s", source)
        self.assertIn('ALMDINA_APP = "almdina_erp"', scope)
        for forbidden in (
            "STAGE_ROLE_BY_TYPE",
            "عامل شريون",
            "عامل رسم",
            "عامل CNC",
            "عامل تقشيط",
            "DISPATCH_ROLES",
            "ADMIN_ROLES",
            "STAGE_ADMIN_ROLES",
            "def require_roles",
        ):
            self.assertNotIn(forbidden, source)

    def test_protected_platform_roles_cannot_become_operational_roles(self) -> None:
        controller = ROUTING_CONTROLLER.read_text(encoding="utf-8")
        master = MASTER_DATA.read_text(encoding="utf-8")
        self.assertIn("is_protected_system_role", controller)
        self.assertIn("لا يمكن استخدام الدور المحمي", controller)
        self.assertIn("PROTECTED_SYSTEM_ROLES", master)
        self.assertIn('"not in", sorted(PROTECTED_SYSTEM_ROLES)', master)

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
        service = QUERY_SERVICE.read_text(encoding="utf-8")
        application = APPLICATION_COMMANDS.parent.joinpath("queries.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("get_order_operational_role_flags", service)
        self.assertIn('"production_actions"', application)
        self.assertIn('"can_reassign_worker"', application)
        self.assertIn('"active_stage_assigned_to"', application)
        self.assertIn('"can_start_stage"', application)
        self.assertIn('"can_handoff_stage"', application)
        self.assertNotIn("DISPATCH_ROLES", service + application)
        self.assertNotIn("ADMIN_ROLES", service + application)

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
