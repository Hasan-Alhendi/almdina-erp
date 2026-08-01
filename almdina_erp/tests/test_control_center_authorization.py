from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_CONTROL_CENTER,
    WORKSPACE_REPORTS,
    WORKSPACE_SHOP_FLOOR,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
    standard_permission_projection,
)
from almdina_erp.almdina_erp.application.security.report_access import (
    build_report_access,
)
from almdina_erp.almdina_erp.domain.replacements.replacement_authorization import (
    ReplacementAction,
    evaluate_replacement_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestControlCenterAuthorization(unittest.TestCase):
    def test_replacement_actions_require_replacement_read(self) -> None:
        state = normalize_capability_state(
            {Capability.APPROVE_REPLACEMENT: True}
        )
        self.assertTrue(state[Capability.APPROVE_REPLACEMENT])
        self.assertTrue(state[Capability.VIEW_REPLACEMENTS])

    def test_archive_requires_plan_view_and_print(self) -> None:
        state = normalize_capability_state(
            {Capability.ARCHIVE_APPROVED_PLAN: True}
        )
        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(state[Capability.PRINT_CUTTING_PLAN])

    def test_financial_reports_require_operations_and_costs(self) -> None:
        state = normalize_capability_state(
            {Capability.VIEW_FINANCIAL_REPORTS: True}
        )
        self.assertTrue(state[Capability.VIEW_OPERATIONAL_REPORTS])
        self.assertTrue(state[Capability.VIEW_COSTS])
        self.assertTrue(state[Capability.VIEW_ORDERS])

    def test_replacement_projection_never_grants_direct_write(self) -> None:
        projection = standard_permission_projection(
            "Replacement Piece",
            {
                Capability.APPROVE_REPLACEMENT: True,
                Capability.EDIT_REPLACEMENT_COST: True,
            },
        )
        self.assertEqual(
            projection,
            {"read": True, "create": False, "write": False},
        )

    def test_report_access_requires_explicit_financial_pair(self) -> None:
        operational = build_report_access(
            {Capability.VIEW_OPERATIONAL_REPORTS}
        )
        self.assertTrue(operational.operational)
        self.assertFalse(operational.financial)

        incomplete = build_report_access(
            {Capability.VIEW_FINANCIAL_REPORTS}
        )
        self.assertFalse(incomplete.operational)
        self.assertFalse(incomplete.financial)

        financial = build_report_access(
            {
                Capability.VIEW_FINANCIAL_REPORTS,
                Capability.VIEW_COSTS,
            }
        )
        self.assertTrue(financial.operational)
        self.assertTrue(financial.financial)

    def test_replacement_policy_checks_capability_status_and_plan(self) -> None:
        missing = evaluate_replacement_action(
            set(),
            status="Pending Approval",
            action=ReplacementAction.APPROVE,
        )
        self.assertFalse(missing.allowed)
        self.assertEqual(missing.code, "missing_capability")

        wrong_status = evaluate_replacement_action(
            {Capability.APPROVE_REPLACEMENT},
            status="Approved",
            action=ReplacementAction.APPROVE,
        )
        self.assertFalse(wrong_status.allowed)
        self.assertEqual(wrong_status.code, "invalid_status")

        missing_plan = evaluate_replacement_action(
            {Capability.START_REPLACEMENT},
            status="Approved",
            action=ReplacementAction.START,
            has_approved_plan=False,
        )
        self.assertFalse(missing_plan.allowed)
        self.assertEqual(missing_plan.code, "missing_approved_plan")

        allowed = evaluate_replacement_action(
            {Capability.COMPLETE_REPLACEMENT},
            status="In Progress",
            action=ReplacementAction.COMPLETE,
        )
        self.assertTrue(allowed.allowed)

    def test_operator_replacement_work_stays_in_shop_floor(self) -> None:
        navigation = build_navigation_context(
            {
                Capability.VIEW_REPLACEMENTS,
                Capability.START_REPLACEMENT,
                Capability.COMPLETE_REPLACEMENT,
            }
        )
        self.assertEqual(navigation["home_page"], "shop-floor-inbox")
        self.assertEqual(navigation["workspaces"], [WORKSPACE_SHOP_FLOOR])

    def test_management_and_reports_expand_the_correct_workspaces(self) -> None:
        control = build_navigation_context(
            {Capability.VIEW_ORDERS, Capability.APPROVE_REPLACEMENT}
        )
        self.assertIn(WORKSPACE_CONTROL_CENTER, control["workspaces"])
        self.assertNotIn(WORKSPACE_REPORTS, control["workspaces"])

        reports = build_navigation_context(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_OPERATIONAL_REPORTS,
            }
        )
        self.assertIn(WORKSPACE_REPORTS, reports["workspaces"])
        self.assertTrue(reports["sections"]["reports"])


if __name__ == "__main__":
    unittest.main()
