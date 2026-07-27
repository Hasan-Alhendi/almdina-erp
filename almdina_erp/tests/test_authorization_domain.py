from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
    capabilities_for_roles,
    has_capability,
    is_order_entry_profile,
    is_shop_floor_only,
)


class TestAuthorizationDomain(unittest.TestCase):
    def test_system_manager_has_every_capability(self) -> None:
        self.assertEqual(capabilities_for_roles({"System Manager"}), ALL_CAPABILITIES)

    def test_order_entry_does_not_inherit_accounts_stock_or_production_management(self) -> None:
        roles = {"Order Entry"}
        self.assertTrue(has_capability(roles, Capability.CREATE_ORDER))
        self.assertTrue(has_capability(roles, Capability.EDIT_ORDER))
        self.assertFalse(has_capability(roles, Capability.APPROVE_ORDER))
        self.assertFalse(has_capability(roles, Capability.MANAGE_STOCK))
        self.assertFalse(has_capability(roles, Capability.EDIT_SPECIAL_PRICE))

    def test_specialized_roles_have_only_their_business_capabilities(self) -> None:
        self.assertTrue(
            has_capability({"Accounts Management"}, Capability.EDIT_SPECIAL_PRICE)
        )
        self.assertFalse(
            has_capability({"Accounts Management"}, Capability.START_ASSIGNED_STAGE)
        )
        self.assertTrue(has_capability({"Stock Manager"}, Capability.MANAGE_STOCK))
        self.assertFalse(has_capability({"Stock Manager"}, Capability.APPROVE_ORDER))

    def test_shop_floor_operator_capabilities_and_navigation_profile(self) -> None:
        roles = {"عامل رسم"}
        self.assertTrue(has_capability(roles, Capability.START_ASSIGNED_STAGE))
        self.assertTrue(has_capability(roles, Capability.HANDOFF_ASSIGNED_STAGE))
        self.assertTrue(is_shop_floor_only(roles))
        self.assertFalse(is_shop_floor_only({"عامل رسم", "Production Manager"}))

    def test_order_entry_navigation_profile_does_not_apply_to_system_manager(self) -> None:
        self.assertTrue(is_order_entry_profile({"Order Entry"}))
        self.assertFalse(is_order_entry_profile({"Order Entry", "System Manager"}))

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capability"):
            has_capability({"System Manager"}, "unknown")


if __name__ == "__main__":
    unittest.main()
