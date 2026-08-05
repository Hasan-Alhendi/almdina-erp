from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    DESKTOP_PAGE_ROUTE,
    WORKSPACE_MAIN_ROUTE,
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestV16DeskNavigation(unittest.TestCase):
    def test_builtin_administrator_opens_frappe_desktop(self) -> None:
        navigation = build_navigation_context(
            {Capability.MANAGE_PERMISSIONS},
            system_administrator=True,
        )

        self.assertEqual(navigation["profile"], "full")
        self.assertEqual(navigation["home_page"], DESKTOP_PAGE_ROUTE)
        self.assertEqual(navigation["default_route"], "/desk/desktop")
        self.assertFalse(navigation["app_only"])
        self.assertIn("Almdina ERP", navigation["workspaces"])

    def test_ordinary_administrative_profile_opens_main_factory_workspace(self) -> None:
        navigation = build_navigation_context({Capability.MANAGE_PERMISSIONS})

        self.assertEqual(navigation["profile"], "full")
        self.assertEqual(navigation["home_page"], WORKSPACE_MAIN_ROUTE)
        self.assertEqual(navigation["default_route"], "/desk/almdina-erp")
        self.assertTrue(navigation["app_only"])
        self.assertIn("Almdina ERP", navigation["workspaces"])

    def test_order_entry_profile_opens_main_factory_workspace(self) -> None:
        navigation = build_navigation_context(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.EDIT_ORDER,
                Capability.SUBMIT_ORDER,
                Capability.PRINT_MEASUREMENTS,
            }
        )

        self.assertEqual(navigation["profile"], "order_entry")
        self.assertEqual(navigation["home_page"], WORKSPACE_MAIN_ROUTE)
        self.assertEqual(navigation["default_route"], "/desk/almdina-erp")
        self.assertTrue(navigation["app_only"])
        self.assertIn("Almdina ERP", navigation["workspaces"])

    def test_operator_only_profile_still_opens_shop_floor(self) -> None:
        navigation = build_navigation_context(
            {
                Capability.VIEW_ORDERS,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
                Capability.VIEW_CUTTING_PLAN,
                Capability.PRINT_CUTTING_PLAN,
                Capability.VIEW_DRAWING_WORKSPACE,
                Capability.UPLOAD_DXF,
            }
        )

        self.assertEqual(navigation["profile"], "shop_floor")
        self.assertEqual(navigation["home_page"], "shop-floor-inbox")
        self.assertEqual(navigation["default_route"], "/app/shop-floor-inbox")
        self.assertTrue(navigation["app_only"])

    def test_inactive_context_does_not_force_a_route(self) -> None:
        navigation = build_navigation_context(set())

        self.assertEqual(navigation["home_page"], "")
        self.assertEqual(navigation["default_route"], "")
        self.assertEqual(navigation["workspaces"], [])
        self.assertFalse(navigation["app_only"])


if __name__ == "__main__":
    unittest.main()
