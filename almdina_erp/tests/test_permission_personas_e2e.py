from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_GO_LIVE,
    WORKSPACE_REPORTS,
    WORKSPACE_SETTINGS,
    WORKSPACE_SHOP_FLOOR,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    enabled_capabilities,
)
from almdina_erp.almdina_erp.application.security.permission_templates import (
    template_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestPermissionPersonasE2E(unittest.TestCase):
    def _navigation(self, template: str) -> tuple[dict[str, bool], dict]:
        state = template_state(template)
        navigation = build_navigation_context(enabled_capabilities(state))
        return state, navigation

    def test_order_entry_sees_only_order_work(self) -> None:
        state, navigation = self._navigation("order_entry")
        self.assertEqual(navigation["profile"], "order_entry")
        self.assertEqual(navigation["home_page"], "almdina-erp")
        self.assertTrue(navigation["sections"]["orders"])
        for section in (
            "costing",
            "planning",
            "drawing",
            "production",
            "quality",
            "workforce",
            "factory_settings",
            "master_data",
            "administration",
            "reports",
        ):
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
