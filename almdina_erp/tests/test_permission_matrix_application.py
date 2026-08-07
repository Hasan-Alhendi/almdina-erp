from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
    changed_capabilities,
    field_permission_projection,
    missing_capability_dependencies,
    normalize_capability_state,
    permission_impact,
    required_capabilities,
    standard_permission_projection,
    validate_capability_dependencies,
)
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES, Capability


class TestPermissionMatrixApplication(unittest.TestCase):
    def test_catalog_contains_every_capability_once_and_declares_dependencies(self) -> None:
        groups = capability_catalog_payload()
        keys = [item["key"] for group in groups for item in group["capabilities"]]
        self.assertEqual(set(keys), ALL_CAPABILITIES)
        self.assertEqual(len(keys), len(set(keys)))
        dxf = next(item for group in groups for item in group["capabilities"] if item["key"] == Capability.UPLOAD_DXF)
        self.assertIn(Capability.VIEW_ORDERS, dxf["requires"])
        self.assertIn(Capability.VIEW_DRAWING_WORKSPACE, dxf["requires"])
        self.assertTrue(dxf["requires_labels"])

    def test_normalization_never_adds_hidden_permissions(self) -> None:
        state = normalize_capability_state({Capability.APPROVE_DXF: True})
        self.assertTrue(state[Capability.APPROVE_DXF])
        self.assertFalse(state[Capability.VIEW_ORDERS])
        self.assertFalse(state[Capability.VIEW_DRAWING_WORKSPACE])

    def test_missing_dependencies_are_reported_and_validation_fails(self) -> None:
        state = normalize_capability_state({Capability.UPLOAD_DXF: True})
        missing = missing_capability_dependencies(state)
        row = next(item for item in missing if item["capability"] == Capability.UPLOAD_DXF)
        self.assertIn(Capability.VIEW_ORDERS, row["missing"])
        self.assertIn(Capability.VIEW_DRAWING_WORKSPACE, row["missing"])
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            validate_capability_dependencies(state)

    def test_complete_explicit_state_is_accepted_without_mutation(self) -> None:
        selected = {
            Capability.VIEW_ORDERS: True,
            Capability.VIEW_DRAWING_WORKSPACE: True,
            Capability.UPLOAD_DXF: True,
        }
        validated = validate_capability_dependencies(selected)
        self.assertTrue(validated[Capability.UPLOAD_DXF])
        self.assertTrue(validated[Capability.VIEW_ORDERS])
        self.assertTrue(validated[Capability.VIEW_DRAWING_WORKSPACE])
        self.assertFalse(validated[Capability.APPROVE_DXF])

    def test_order_input_requires_customer_and_edge_reads_explicitly(self) -> None:
        required = required_capabilities(Capability.CREATE_ORDER)
        self.assertIn(Capability.VIEW_ORDERS, required)
        self.assertIn(Capability.VIEW_CUSTOMERS, required)
        self.assertIn(Capability.VIEW_EDGE_BANDING_TYPES, required)

    def test_financial_reporting_has_transitive_explicit_dependencies(self) -> None:
        required = required_capabilities(Capability.VIEW_FINANCIAL_REPORTS)
        self.assertIn(Capability.VIEW_OPERATIONAL_REPORTS, required)
        self.assertIn(Capability.VIEW_COSTS, required)
        self.assertIn(Capability.VIEW_ORDERS, required)

    def test_read_grants_project_select_for_linked_records(self) -> None:
        order = standard_permission_projection("Door Cutting Order", {Capability.VIEW_ORDERS: True})
        edge = standard_permission_projection("Edge Banding Type", {Capability.VIEW_EDGE_BANDING_TYPES: True})
        customer = standard_permission_projection("Customer", {Capability.VIEW_CUSTOMERS: True})
        self.assertTrue(order["read"] and order["select"])
        self.assertTrue(edge["read"] and edge["select"])
        self.assertTrue(customer["read"] and customer["select"])

    def test_cost_field_projection_uses_only_explicit_grants(self) -> None:
        read_only = field_permission_projection("Door Cutting Order", {Capability.VIEW_COSTS: True})
        incomplete_edit = field_permission_projection("Door Cutting Order", {Capability.EDIT_COST_SETTINGS: True})
        self.assertEqual(read_only, {1: {"read": True, "write": False}})
        self.assertEqual(incomplete_edit, {1: {"read": False, "write": True}})
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            validate_capability_dependencies({Capability.EDIT_COST_SETTINGS: True})

    def test_unknown_capability_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown capabilities"):
            normalize_capability_state({"unknown_grant": True})

    def test_impact_requires_a_valid_explicit_matrix(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            permission_impact({Capability.START_ASSIGNED_STAGE: True})
        impact = permission_impact(
            {
                Capability.VIEW_ORDERS: True,
                Capability.START_ASSIGNED_STAGE: True,
                Capability.HANDOFF_ASSIGNED_STAGE: True,
            }
        )
        navigation = impact["navigation"]
        self.assertEqual(navigation["home_page"], "shop-floor-inbox")
        self.assertEqual(navigation["profile"], "shop_floor")
        self.assertTrue(navigation["sections"]["production"])

    def test_changes_include_labels_risk_and_direction(self) -> None:
        changes = changed_capabilities({Capability.VIEW_COSTS: False}, {Capability.VIEW_COSTS: True})
        change = next(item for item in changes if item["key"] == Capability.VIEW_COSTS)
        self.assertFalse(change["before"])
        self.assertTrue(change["after"])
        self.assertEqual(change["risk"], "sensitive")
        self.assertTrue(change["label"])


if __name__ == "__main__":
    unittest.main()
