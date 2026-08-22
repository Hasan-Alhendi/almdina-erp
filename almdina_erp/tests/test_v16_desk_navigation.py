from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_MAIN,
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestV16DeskNavigation(unittest.TestCase):
    def _assert_frappe_owns_home(self, navigation: dict) -> None:
        self.assertNotIn("home_page", navigation)
        self.assertNotIn("default_route", navigation)

    def test_builtin_administrator_keeps_native_frappe_home(self) -> None:
        navigation = build_navigation_context(
            {Capability.MANAGE_PERMISSIONS},
            system_administrator=True,
        )

        self.assertEqual(navigation["profile"], "full")
        self._assert_frappe_owns_home(navigation)
        self.assertFalse(navigation["app_only"])
        self.assertIn("Almdina ERP", navigation["workspaces"])

    def test_ordinary_administrative_profile_keeps_native_frappe_home(self) -> None:
        navigation = build_navigation_context({Capability.MANAGE_PERMISSIONS})

        self.assertEqual(navigation["profile"], "full")
        self._assert_frappe_owns_home(navigation)
        self.assertTrue(navigation["app_only"])
        self.assertIn("Almdina ERP", navigation["workspaces"])

    def test_order_entry_profile_keeps_native_frappe_home(self) -> None:
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
        self._assert_frappe_owns_home(navigation)
        self.assertTrue(navigation["app_only"])
        self.assertIn("Almdina ERP", navigation["workspaces"])

    def test_operator_only_profile_keeps_native_frappe_home(self) -> None:
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
        self._assert_frappe_owns_home(navigation)
        self.assertEqual(navigation["workspaces"], [WORKSPACE_MAIN])
        self.assertTrue(navigation["app_only"])

    def test_inactive_context_does_not_force_a_route(self) -> None:
        navigation = build_navigation_context(set())

        self._assert_frappe_owns_home(navigation)
        self.assertEqual(navigation["workspaces"], [])
        self.assertFalse(navigation["app_only"])


if __name__ == "__main__":
    unittest.main()
