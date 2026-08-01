from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.permission_context import (
    PERMISSION_CONTEXT_VERSION,
    build_permission_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    ROLE_CAPABILITIES,
    Capability,
    capabilities_for_roles,
    capability_flags_for_roles,
    has_capability,
    is_order_entry_profile,
    is_shop_floor_only,
)


class TestAuthorizationDomain(unittest.TestCase):
    def test_system_manager_has_every_capability(self) -> None:
        self.assertEqual(capabilities_for_roles({"System Manager"}), ALL_CAPABILITIES)

    def test_role_policy_contains_only_registered_capabilities(self) -> None:
        for role, capabilities in ROLE_CAPABILITIES.items():
            with self.subTest(role=role):
                self.assertTrue(capabilities)
                self.assertLessEqual(capabilities, ALL_CAPABILITIES)

    def test_capability_flags_are_complete_deterministic_and_json_safe(self) -> None:
        flags = capability_flags_for_roles({"عامل رسم"})
        self.assertEqual(list(flags), sorted(ALL_CAPABILITIES))
        self.assertEqual(set(flags), ALL_CAPABILITIES)
        self.assertTrue(all(isinstance(value, bool) for value in flags.values()))

    def test_order_entry_does_not_inherit_accounts_or_production_management(self) -> None:
        roles = {"Order Entry"}
        self.assertTrue(has_capability(roles, Capability.CREATE_ORDER))
        self.assertTrue(has_capability(roles, Capability.EDIT_ORDER))
        self.assertTrue(has_capability(roles, Capability.CREATE_ORDER_REVISION))
        self.assertTrue(has_capability(roles, Capability.PRINT_MEASUREMENTS))
        self.assertFalse(has_capability(roles, Capability.APPROVE_ORDER))
        self.assertFalse(has_capability(roles, Capability.VIEW_COSTS))
        self.assertFalse(has_capability(roles, Capability.EDIT_SPECIAL_PRICE))
        self.assertFalse(has_capability(roles, Capability.UPLOAD_DXF))

    def test_production_manager_can_manage_operational_permissions(self) -> None:
        roles = {"Production Manager"}
        self.assertTrue(has_capability(roles, Capability.CREATE_ORDER_REVISION))
        self.assertTrue(has_capability(roles, Capability.APPROVE_ORDER))
        self.assertTrue(has_capability(roles, Capability.UPLOAD_DXF))
        self.assertTrue(has_capability(roles, Capability.APPROVE_DXF))
        self.assertTrue(has_capability(roles, Capability.REASSIGN_WORKER))
        self.assertFalse(has_capability(roles, Capability.MANAGE_PERMISSIONS))

    def test_designer_can_prepare_dxf_but_cannot_approve_or_view_costs(self) -> None:
        roles = {"عامل رسم"}
        self.assertTrue(has_capability(roles, Capability.VIEW_DRAWING_WORKSPACE))
        self.assertTrue(has_capability(roles, Capability.EDIT_SPECIAL_DRAWING))
        self.assertTrue(has_capability(roles, Capability.UPLOAD_DXF))
        self.assertTrue(has_capability(roles, Capability.REPLACE_DXF))
        self.assertFalse(has_capability(roles, Capability.APPROVE_DXF))
        self.assertFalse(has_capability(roles, Capability.VIEW_COSTS))
        self.assertFalse(has_capability(roles, Capability.DISPATCH_ORDER))

    def test_cnc_operator_can_consume_dxf_without_replacing_it(self) -> None:
        roles = {"عامل CNC"}
        self.assertTrue(has_capability(roles, Capability.VIEW_DRAWING_WORKSPACE))
        self.assertTrue(has_capability(roles, Capability.EXPORT_DXF))
        self.assertFalse(has_capability(roles, Capability.UPLOAD_DXF))
        self.assertFalse(has_capability(roles, Capability.REPLACE_DXF))
        self.assertFalse(has_capability(roles, Capability.APPROVE_DXF))

    def test_accounts_role_has_financial_permissions_only(self) -> None:
        roles = {"Accounts Management"}
        self.assertTrue(has_capability(roles, Capability.VIEW_COSTS))
        self.assertTrue(has_capability(roles, Capability.EDIT_SPECIAL_PRICE))
        self.assertTrue(has_capability(roles, Capability.APPROVE_SPECIAL_PRICE))
        self.assertTrue(has_capability(roles, Capability.PRINT_CUSTOMER_INVOICE))
        self.assertFalse(has_capability(roles, Capability.START_ASSIGNED_STAGE))
        self.assertFalse(has_capability(roles, Capability.VIEW_DRAWING_WORKSPACE))

    def test_shop_floor_operator_capabilities_and_navigation_profile(self) -> None:
        roles = {"عامل رسم"}
        self.assertTrue(has_capability(roles, Capability.START_ASSIGNED_STAGE))
        self.assertTrue(has_capability(roles, Capability.HANDOFF_ASSIGNED_STAGE))
        self.assertTrue(is_shop_floor_only(roles))
        self.assertFalse(is_shop_floor_only({"عامل رسم", "Production Manager"}))

    def test_order_entry_navigation_profile_does_not_apply_to_system_manager(self) -> None:
        self.assertTrue(is_order_entry_profile({"Order Entry"}))
        self.assertFalse(is_order_entry_profile({"Order Entry", "System Manager"}))

    def test_multiple_roles_receive_the_union_of_their_capabilities(self) -> None:
        roles = {"عامل رسم", "Accounts Management"}
        self.assertTrue(has_capability(roles, Capability.UPLOAD_DXF))
        self.assertTrue(has_capability(roles, Capability.VIEW_COSTS))
        self.assertFalse(has_capability(roles, Capability.APPROVE_DXF))

    def test_permission_context_is_stable_and_contains_no_role_names(self) -> None:
        context = build_permission_context({"عامل رسم"})
        self.assertEqual(context["version"], PERMISSION_CONTEXT_VERSION)
        self.assertEqual(context["profile"], "shop_floor")
        self.assertEqual(set(context), {"version", "profile", "capabilities"})
        self.assertTrue(context["capabilities"][Capability.UPLOAD_DXF])
        self.assertFalse(context["capabilities"][Capability.APPROVE_DXF])
        self.assertNotIn("roles", context)

    def test_permission_context_profiles_share_the_same_capability_contract(self) -> None:
        contexts = [
            build_permission_context({"Order Entry"}),
            build_permission_context({"عامل CNC"}),
            build_permission_context({"Production Manager"}),
        ]
        self.assertEqual(
            [context["profile"] for context in contexts],
            ["order_entry", "shop_floor", "full"],
        )
        for context in contexts:
            self.assertEqual(set(context["capabilities"]), ALL_CAPABILITIES)

    def test_unknown_capability_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capability"):
            has_capability({"System Manager"}, "unknown")


if __name__ == "__main__":
    unittest.main()
