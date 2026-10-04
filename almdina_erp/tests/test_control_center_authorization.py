from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_CONTROL_CENTER,
    WORKSPACE_MAIN,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestControlCenterAuthorization(unittest.TestCase):
    def test_archive_requires_plan_view_and_print(self) -> None:
        state = normalize_capability_state(
            {Capability.ARCHIVE_APPROVED_PLAN: True}
        )
        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(state[Capability.PRINT_CUTTING_PLAN])

    def test_cost_view_stays_without_retired_report_capabilities(self) -> None:
        state = normalize_capability_state({Capability.VIEW_COSTS: True})
        self.assertTrue(state[Capability.VIEW_COSTS])
        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertNotIn("view_operational_reports", state)
        self.assertNotIn("view_financial_reports", state)

    def test_operator_stage_work_uses_shared_order_interface(self) -> None:
        navigation = build_navigation_context(
            {
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            }
        )
        self.assertNotIn("home_page", navigation)
        self.assertNotIn("default_route", navigation)
        self.assertEqual(navigation["workspaces"], [WORKSPACE_MAIN])

    def test_management_opens_control_center_without_a_reports_section(self) -> None:
        control = build_navigation_context(
            {Capability.VIEW_ORDERS, Capability.APPROVE_ORDER}
        )
        self.assertIn(WORKSPACE_CONTROL_CENTER, control["workspaces"])
        self.assertNotIn("reports", control["sections"])

        costing = build_navigation_context(
            {Capability.VIEW_ORDERS, Capability.VIEW_COSTS}
        )
        self.assertTrue(costing["sections"]["costing"])
        self.assertNotIn("reports", costing["sections"])


if __name__ == "__main__":
    unittest.main()
