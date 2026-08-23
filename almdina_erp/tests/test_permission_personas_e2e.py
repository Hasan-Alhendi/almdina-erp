from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.business_capability_state import (
    enabled_business_capabilities,
    normalize_business_capability_state,
)
from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_GO_LIVE,
    WORKSPACE_MAIN,
    WORKSPACE_REPORTS,
    WORKSPACE_SETTINGS,
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestPermissionPersonasE2E(unittest.TestCase):
    def _context(self, *capabilities: str) -> tuple[dict[str, bool], dict]:
        state = normalize_business_capability_state(
            {capability: True for capability in capabilities}
        )
        navigation = build_navigation_context(enabled_business_capabilities(state))
        return state, navigation

    def _assert_frappe_owns_home(self, navigation: dict) -> None:
        self.assertNotIn("home_page", navigation)
        self.assertNotIn("default_route", navigation)

    def test_order_entry_grants_expose_only_order_work(self) -> None:
        state, navigation = self._context(
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
        )
        self.assertEqual(navigation["profile"], "order_entry")
        self._assert_frappe_owns_home(navigation)
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
        self.assertFalse(state[Capability.VIEW_CUSTOMERS])
        self.assertFalse(state[Capability.VIEW_EDGE_BANDING_TYPES])
        self.assertTrue(state[Capability.PRINT_CUSTOMER_INVOICE])
        self.assertTrue(state[Capability.PRINT_MEASUREMENTS])
        self.assertFalse(state[Capability.APPROVE_ORDER])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.PRINT_INTERNAL_COST_REPORT])

    def test_planning_and_drawing_grants_do_not_imply_supervision_or_costs(self) -> None:
        state, navigation = self._context(
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
        )
        self.assertTrue(navigation["sections"]["planning"])
        self.assertTrue(navigation["sections"]["drawing"])
        self.assertTrue(navigation["sections"]["production"])
        self._assert_frappe_owns_home(navigation)
        self.assertEqual(navigation["workspaces"], [WORKSPACE_MAIN])
        self.assertTrue(state[Capability.UPLOAD_DXF])
        self.assertTrue(state[Capability.REPLACE_DXF])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.REASSIGN_WORKER])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(navigation["sections"]["reports"])

    def test_operator_grants_use_shared_order_list_without_supervision(self) -> None:
        state, navigation = self._context(
            Capability.VIEW_ORDERS,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
            Capability.VIEW_CUTTING_PLAN,
            Capability.PRINT_CUTTING_PLAN,
            Capability.RECORD_INCIDENT,
            Capability.VIEW_REPLACEMENTS,
            Capability.START_REPLACEMENT,
            Capability.COMPLETE_REPLACEMENT,
        )
        self.assertEqual(navigation["profile"], "shop_floor")
        self._assert_frappe_owns_home(navigation)
        self.assertEqual(navigation["workspaces"], [WORKSPACE_MAIN])
        self.assertTrue(state[Capability.START_ASSIGNED_STAGE])
        self.assertTrue(state[Capability.HANDOFF_ASSIGNED_STAGE])
        self.assertFalse(state[Capability.UPLOAD_DXF])
        self.assertFalse(state[Capability.REPLACE_DXF])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.REVERT_DEPARTMENT])
        self.assertFalse(state[Capability.REASSIGN_WORKER])

    def test_supervision_grants_do_not_imply_financial_or_admin_access(self) -> None:
        state, navigation = self._context(
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
        )
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

    def test_financial_grants_do_not_imply_production(self) -> None:
        state, navigation = self._context(
            Capability.VIEW_ORDERS,
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.EDIT_REPLACEMENT_COST,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
            Capability.PRINT_INTERNAL_COST_REPORT,
            Capability.VIEW_FINANCIAL_REPORTS,
        )
        self.assertTrue(navigation["sections"]["costing"])
        self.assertTrue(navigation["sections"]["reports"])
        self.assertTrue(state[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertTrue(state[Capability.PRINT_INTERNAL_COST_REPORT])
        self.assertFalse(state[Capability.DISPATCH_ORDER])
        self.assertFalse(state[Capability.START_ASSIGNED_STAGE])
        self.assertFalse(state[Capability.MANAGE_PERMISSIONS])

    def test_quality_grants_do_not_imply_financial_data(self) -> None:
        state, navigation = self._context(
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
        )
        self.assertTrue(navigation["sections"]["quality"])
        self.assertTrue(navigation["sections"]["reports"])
        self.assertTrue(state[Capability.APPROVE_ORDER])
        self.assertTrue(state[Capability.ARCHIVE_APPROVED_PLAN])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertFalse(state[Capability.EDIT_REPLACEMENT_COST])

    def test_administration_grants_are_configuration_only(self) -> None:
        state, navigation = self._context(
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
        )
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
