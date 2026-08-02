from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    legacy_role_state,
    legacy_roles,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)


class TestLegacyPermissionBootstrap(unittest.TestCase):
    def test_order_entry_restores_creation_without_internal_cost_access(self) -> None:
        state = legacy_role_state("Order Entry")

        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertTrue(state[Capability.CREATE_ORDER])
        self.assertTrue(state[Capability.EDIT_ORDER])
        self.assertTrue(state[Capability.SUBMIT_ORDER])
        self.assertTrue(state[Capability.PRINT_MEASUREMENTS])
        self.assertTrue(state[Capability.PRINT_CUSTOMER_INVOICE])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.VIEW_CUTTING_PLAN])

    def test_production_manager_restores_order_plan_and_supervision(self) -> None:
        state = legacy_role_state("Production Manager")

        self.assertTrue(state[Capability.CREATE_ORDER])
        self.assertTrue(state[Capability.EDIT_ORDER])
        self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(state[Capability.RECALCULATE_PLAN])
        self.assertTrue(state[Capability.DISPATCH_ORDER])
        self.assertTrue(state[Capability.REASSIGN_WORKER])
        self.assertTrue(state[Capability.APPROVE_ORDER])
        self.assertTrue(state[Capability.REJECT_ORDER])
        self.assertFalse(state[Capability.VIEW_COSTS])

    def test_accounts_role_restores_cost_and_financial_documents(self) -> None:
        state = legacy_role_state("Accounts Management")

        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertTrue(state[Capability.VIEW_COSTS])
        self.assertTrue(state[Capability.EDIT_COST_SETTINGS])
        self.assertTrue(state[Capability.APPROVE_SPECIAL_PRICE])
        self.assertTrue(state[Capability.PRINT_CUSTOMER_INVOICE])
        self.assertTrue(state[Capability.PRINT_INTERNAL_COST_REPORT])
        self.assertFalse(state[Capability.CREATE_ORDER])

    def test_drawing_role_restores_plan_and_dxf_without_costs(self) -> None:
        state = legacy_role_state("عامل رسم")

        self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(state[Capability.RECALCULATE_PLAN])
        self.assertTrue(state[Capability.VIEW_DRAWING_WORKSPACE])
        self.assertTrue(state[Capability.EXPORT_DXF])
        self.assertTrue(state[Capability.UPLOAD_DXF])
        self.assertFalse(state[Capability.VIEW_COSTS])

    def test_system_manager_receives_complete_application_access(self) -> None:
        state = legacy_role_state("System Manager")

        self.assertEqual(
            {capability for capability, enabled in state.items() if enabled},
            set(ALL_CAPABILITIES),
        )

    def test_bootstrap_scope_is_explicit_and_unknown_roles_fail_closed(self) -> None:
        self.assertIn("Order Entry", legacy_roles())
        self.assertIn("Accounts Management", legacy_roles())
        self.assertIn("System Manager", legacy_roles())
        with self.assertRaisesRegex(ValueError, "Unknown legacy Almdina role"):
            legacy_role_state("Unrelated Role")


if __name__ == "__main__":
    unittest.main()
