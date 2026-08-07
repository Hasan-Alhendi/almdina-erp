from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_GO_LIVE,
    WORKSPACE_MAIN_ROUTE,
    WORKSPACE_REPORTS,
    WORKSPACE_SETTINGS,
    WORKSPACE_SHOP_FLOOR,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    enabled_capabilities,
    validate_capability_dependencies,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def explicit_state(*capabilities: str) -> dict[str, bool]:
    """Build and validate a fully explicit administrator-selected role state."""

    return validate_capability_dependencies(
        {capability: True for capability in capabilities}
    )


PERSONA_STATES = {
    "order_entry": explicit_state(
        Capability.VIEW_ORDERS,
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.SUBMIT_ORDER,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.VIEW_CUSTOMERS,
        Capability.VIEW_EDGE_BANDING_TYPES,
    ),
    "planner_designer": explicit_state(
        Capability.VIEW_ORDERS,
        Capability.VIEW_CUTTING_PLAN,
        Capability.RECALCULATE_PLAN,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        Capability.PRINT_CUTTING_PLAN,
        Capability.VIEW_DRAWING_WORKSPACE,
        Capability.EDIT_SPECIAL_DRAWING,
        Capability.EXPORT_DXF,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
    ),
    "production_operator": explicit_state(
        Capability.VIEW_ORDERS,
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
        Capability.VIEW_CUTTING_PLAN,
        Capability.PRINT_CUTTING_PLAN,
        Capability.RECORD_INCIDENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.START_REPLACEMENT,
        Capability.COMPLETE_REPLACEMENT,
    ),
    "production_supervisor": explicit_state(
        Capability.VIEW_ORDERS,
        Capability.VIEW_CUTTING_PLAN,
        Capability.DISPATCH_ORDER,
        Capability.REVERT_DEPARTMENT,
        Capability.RETURN_ORDER_TO_DRAFT,
        Capability.MARK_DELIVERED,
        Capability.REASSIGN_WORKER,
        Capability.CREATE_REPLACEMENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.APPROVE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
        Capability.VIEW_OPERATIONAL_REPORTS,
    ),
    "pricing_and_documents": explicit_state(
        Capability.VIEW_ORDERS,
        Capability.VIEW_COSTS,
        Capability.EDIT_COST_SETTINGS,
        Capability.EDIT_SPECIAL_PRICE,
        Capability.APPROVE_SPECIAL_PRICE,
        Capability.VIEW_REPLACEMENTS,
        Capability.EDIT_REPLACEMENT_COST,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
        Capability.VIEW_OPERATIONAL_REPORTS,
        Capability.VIEW_FINANCIAL_REPORTS,
    ),
    "control_center": explicit_state(
        Capability.VIEW_ORDERS,
        Capability.APPROVE_ORDER,
        Capability.REJECT_ORDER,
        Capability.VIEW_CUTTING_PLAN,
        Capability.PRINT_CUTTING_PLAN,
        Capability.ARCHIVE_APPROVED_PLAN,
        Capability.CREATE_REPLACEMENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.APPROVE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
        Capability.VIEW_OPERATIONAL_REPORTS,
    ),
    "factory_administration": explicit_state(
        Capability.VIEW_USERS,
        Capability.CREATE_USERS,
        Capability.EDIT_USERS,
        Capability.ASSIGN_USER_ROLES,
        Capability.ENABLE_USERS,
        Capability.DISABLE_USERS,
        Capability.RESET_USER_PASSWORD,
        Capability.VIEW_FACTORY_SETTINGS,
        Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
        Capability.EDIT_FACTORY_COST_DEFAULTS,
        Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
        Capability.VIEW_PRODUCTION_ROUTINGS,
        Capability.CREATE_PRODUCTION_ROUTINGS,
        Capability.EDIT_PRODUCTION_ROUTINGS,
        Capability.DELETE_PRODUCTION_ROUTINGS,
        Capability.VIEW_EDGE_BANDING_TYPES,
        Capability.CREATE_EDGE_BANDING_TYPES,
        Capability.EDIT_EDGE_BANDING_TYPES,
        Capability.DELETE_EDGE_BANDING_TYPES,
        Capability.MANAGE_PERMISSIONS,
    ),
}


class TestPermissionPersonasE2E(unittest.TestCase):
    def _navigation(self, persona: str) -> tuple[dict[str, bool], dict]:
        state = PERSONA_STATES[persona]
        navigation = build_navigation_context(enabled_capabilities(state))
        return state, navigation

    def test_personas_are_valid_explicit_fixtures_not_runtime_templates(self) -> None:
        self.assertTrue(PERSONA_STATES)
        for state in PERSONA_STATES.values():
            self.assertEqual(validate_capability_dependencies(state), state)

    def test_order_entry_sees_only_order_work(self) -> None:
        state, navigation = self._navigation("order_entry")
        self.assertEqual(navigation["profile"], "order_entry")
        self.assertEqual(navigation["home_page"], WORKSPACE_MAIN_ROUTE)
        self.assertEqual(navigation["default_route"], f"/desk/{WORKSPACE_MAIN_ROUTE}")
        self.assertTrue(navigation["sections"]["orders"])
        for section in ("costing", "planning", "drawing", "production", "quality", "workforce", "factory_settings", "master_data", "administration", "reports"):
            self.assertFalse(navigation["sections"][section], section)
        self.assertTrue(state[Capability.PRINT_CUSTOMER_INVOICE])
        self.assertTrue(state[Capability.PRINT_MEASUREMENTS])
        self.assertFalse(state[Capability.APPROVE_ORDER])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.PRINT_INTERNAL_COST_REPORT])

    def test_planner_designer_has_plan_drawing_and_assigned_stage_only(self) -> None:
        state, navigation = self._navigation("planner_designer")
        self.assertTrue(navigation["sections"]["planning"])
        self.assertTrue(navigation["sections"]["drawing"])
        self.assertTrue(navigation["sections"]["production"])
        self.assertIn(WORKSPACE_SHOP_FLOOR, navigation["workspaces"])
        self.assertTrue(state[Capability.UPLOAD_DXF])
        self.assertTrue(state[Capability.REPLACE_DXF])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.REASSIGN_WORKER])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(navigation["sections"]["reports"])

    def test_operator_is_routed_to_shop_floor_and_cannot_supervise(self) -> None:
        state, navigation = self._navigation("production_operator")
        self.assertEqual(navigation["profile"], "shop_floor")
        self.assertEqual(navigation["home_page"], "shop-floor-inbox")
        self.assertEqual(navigation["workspaces"], [WORKSPACE_SHOP_FLOOR])
        self.assertTrue(state[Capability.START_ASSIGNED_STAGE])
        self.assertTrue(state[Capability.HANDOFF_ASSIGNED_STAGE])
        self.assertFalse(state[Capability.UPLOAD_DXF])
        self.assertFalse(state[Capability.REPLACE_DXF])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.REVERT_DEPARTMENT])
        self.assertFalse(state[Capability.REASSIGN_WORKER])

    def test_supervisor_can_coordinate_without_financial_or_admin_access(self) -> None:
        state, navigation = self._navigation("production_supervisor")
        self.assertTrue(navigation["sections"]["production"])
        self.assertTrue(navigation["sections"]["quality"])
        self.assertTrue(navigation["sections"]["reports"])
        self.assertTrue(state[Capability.DISPATCH_ORDER])
        self.assertTrue(state[Capability.REASSIGN_WORKER])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertFalse(state[Capability.MANAGE_PERMISSIONS])
        self.assertNotIn(WORKSPACE_SETTINGS, navigation["workspaces"])
        self.assertNotIn(WORKSPACE_GO_LIVE, navigation["workspaces"])

    def test_pricing_persona_has_financial_documents_without_production(self) -> None:
        state, navigation = self._navigation("pricing_and_documents")
        self.assertTrue(navigation["sections"]["costing"])
        self.assertTrue(navigation["sections"]["reports"])
        self.assertTrue(state[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertTrue(state[Capability.PRINT_INTERNAL_COST_REPORT])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.START_ASSIGNED_STAGE])
        self.assertFalse(state[Capability.MANAGE_PERMISSIONS])

    def test_control_center_has_quality_without_financial_data(self) -> None:
        state, navigation = self._navigation("control_center")
        self.assertTrue(navigation["sections"]["quality"])
        self.assertTrue(navigation["sections"]["reports"])
        self.assertTrue(state[Capability.APPROVE_ORDER])
        self.assertTrue(state[Capability.ARCHIVE_APPROVED_PLAN])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertFalse(state[Capability.EDIT_REPLACEMENT_COST])

    def test_factory_administrator_has_configuration_not_business_operations(self) -> None:
        state, navigation = self._navigation("factory_administration")
        self.assertTrue(navigation["sections"]["workforce"])
        self.assertTrue(navigation["sections"]["factory_settings"])
        self.assertTrue(navigation["sections"]["master_data"])
        self.assertTrue(navigation["sections"]["administration"])
        self.assertFalse(navigation["sections"]["orders"])
        self.assertFalse(navigation["sections"]["production"])
        self.assertFalse(navigation["sections"]["quality"])
        self.assertFalse(navigation["sections"]["costing"])
        self.assertFalse(navigation["sections"]["reports"])
        self.assertFalse(state[Capability.APPROVE_ORDER])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.VIEW_OPERATIONAL_REPORTS])
        self.assertFalse(state[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertIn(WORKSPACE_SETTINGS, navigation["workspaces"])
        self.assertIn(WORKSPACE_REPORTS, navigation["workspaces"])
        self.assertIn(WORKSPACE_GO_LIVE, navigation["workspaces"])


if __name__ == "__main__":
    unittest.main()
