from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
    changed_capabilities,
    field_permission_projection,
    normalize_capability_state,
    permission_impact,
    standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)


class TestPermissionMatrixApplication(unittest.TestCase):
    def test_catalog_contains_every_capability_once(self) -> None:
        groups = capability_catalog_payload()
        keys = [
            item["key"]
            for group in groups
            for item in group["capabilities"]
        ]
        self.assertEqual(set(keys), ALL_CAPABILITIES)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(group["label"] for group in groups))
        self.assertTrue(
            all(
                item["label"] and item["description"] and item["risk"]
                for group in groups
                for item in group["capabilities"]
            )
        )

    def test_order_actions_automatically_require_order_read(self) -> None:
        state = normalize_capability_state({Capability.APPROVE_DXF: True})
        self.assertTrue(state[Capability.APPROVE_DXF])
        self.assertTrue(state[Capability.VIEW_ORDERS])

        empty = normalize_capability_state({Capability.VIEW_ORDERS: False})
        self.assertFalse(empty[Capability.VIEW_ORDERS])

    def test_plan_actions_automatically_require_plan_view(self) -> None:
        for action in (
            Capability.RECALCULATE_PLAN,
            Capability.EDIT_OPTIMIZER_SETTINGS,
            Capability.PRINT_CUTTING_PLAN,
        ):
            with self.subTest(action=action):
                state = normalize_capability_state({action: True})
                self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])

    def test_drawing_actions_automatically_require_drawing_workspace(self) -> None:
        for action in (
            Capability.EDIT_SPECIAL_DRAWING,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.APPROVE_DXF,
        ):
            with self.subTest(action=action):
                state = normalize_capability_state({action: True})
                self.assertTrue(state[Capability.VIEW_DRAWING_WORKSPACE])

    def test_internal_cost_actions_require_cost_view_but_customer_invoice_does_not(self) -> None:
        for action in (
            Capability.EDIT_COST_SETTINGS,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.PRINT_INTERNAL_COST_REPORT,
        ):
            with self.subTest(action=action):
                state = normalize_capability_state({action: True})
                self.assertTrue(state[Capability.VIEW_COSTS])

        customer = normalize_capability_state(
            {Capability.PRINT_CUSTOMER_INVOICE: True}
        )
        self.assertFalse(customer[Capability.VIEW_COSTS])

    def test_read_grants_also_project_select_for_linked_records(self) -> None:
        order = standard_permission_projection(
            "Door Cutting Order",
            {Capability.VIEW_ORDERS: True},
        )
        edge = standard_permission_projection(
            "Edge Banding Type",
            {Capability.VIEW_EDGE_BANDING_TYPES: True},
        )

        self.assertTrue(order["read"])
        self.assertTrue(order["select"])
        self.assertTrue(edge["read"])
        self.assertTrue(edge["select"])

    def test_cost_capabilities_project_to_field_permission_level_one(self) -> None:
        read_only = field_permission_projection(
            "Door Cutting Order",
            {Capability.VIEW_COSTS: True},
        )
        editable = field_permission_projection(
            "Door Cutting Order",
            {Capability.EDIT_COST_SETTINGS: True},
        )

        self.assertEqual(read_only, {1: {"read": True, "write": False}})
        self.assertEqual(editable, {1: {"read": True, "write": True}})
        self.assertEqual(
            field_permission_projection(
                "Production Routing",
                {Capability.VIEW_COSTS: True},
            ),
            {},
        )

    def test_unknown_capability_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capabilities"):
            normalize_capability_state({"unknown_grant": True})

    def test_impact_uses_the_shared_navigation_policy(self) -> None:
        impact = permission_impact(
            {
                Capability.START_ASSIGNED_STAGE: True,
                Capability.HANDOFF_ASSIGNED_STAGE: True,
            }
        )
        navigation = impact["navigation"]
        self.assertEqual(navigation["home_page"], "shop-floor-inbox")
        self.assertEqual(navigation["profile"], "shop_floor")
        self.assertTrue(navigation["shared_shell"])
        self.assertTrue(navigation["sections"]["production"])

    def test_changes_include_labels_risk_and_direction(self) -> None:
        changes = changed_capabilities(
            {Capability.VIEW_COSTS: False},
            {Capability.VIEW_COSTS: True},
        )
        change = next(
            item for item in changes if item["key"] == Capability.VIEW_COSTS
        )
        self.assertFalse(change["before"])
        self.assertTrue(change["after"])
        self.assertEqual(change["risk"], "sensitive")
        self.assertTrue(change["label"])


if __name__ == "__main__":
    unittest.main()
