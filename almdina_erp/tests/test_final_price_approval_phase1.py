"""Phase 1 contracts for independent final-price approval scaffolding."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.final_price_approval_migration import (
    capability_is_ungranted_by_default,
    legacy_orders_remain_unapproved,
    preserve_existing_capability_grants,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
    capability_catalog_payload,
    normalize_capability_state,
)
from almdina_erp.almdina_erp.application.security.price_approval_access import (
    can_mutate_price_approval_via_desk,
    can_read_price_approval_record,
)
from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
    SUPPORTING_DOCTYPES,
    supporting_standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
    PriceApprovalFieldForgeryError,
    PriceApprovalRecordMutationError,
    assert_order_price_approval_fields_unchanged,
    assert_price_approval_record_immutable,
    default_price_approval_status,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
ORDER_SCHEMA = (
    ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
)
APPROVAL_SCHEMA = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_price_approval"
    / "door_cutting_price_approval.json"
)
PATCHES = ROOT / "patches.txt"
HOOKS = ROOT / "hooks.py"
TRANSLATIONS = ROOT / "translations" / "ar.csv"


def _fields(schema_path: Path) -> dict[str, dict]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in schema["fields"]}


class TestFinalPriceApprovalPhase1(unittest.TestCase):
    def test_new_order_defaults_to_unapproved_price_status(self) -> None:
        fields = _fields(ORDER_SCHEMA)
        status = fields["price_approval_status"]
        self.assertEqual(default_price_approval_status(), PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertEqual(status["default"], PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertEqual(status["options"], "Unapproved\nApproved")
        self.assertEqual(status["label"], "Price approval status")
        self.assertEqual(status.get("read_only"), 1)
        self.assertEqual(status.get("no_copy"), 1)
        self.assertNotEqual(status.get("permlevel"), 1)

        link = fields["current_price_approval"]
        self.assertEqual(link["options"], "Door Cutting Price Approval")
        self.assertEqual(link.get("permlevel"), 1)
        self.assertEqual(link.get("read_only"), 1)
        self.assertEqual(link.get("no_copy"), 1)

    def test_operational_status_options_unchanged(self) -> None:
        fields = _fields(ORDER_SCHEMA)
        self.assertEqual(fields["status"]["options"], "Draft\nDelivered\nCancelled")
        self.assertEqual(
            fields["customer_quote_status"]["options"],
            "Automatic\nEstimated\nPartially Approved\nApproved",
        )

    def test_legacy_plan_or_special_quote_approval_does_not_approve_final_price(self) -> None:
        self.assertEqual(
            legacy_orders_remain_unapproved(
                plan_approved=True,
                customer_quote_status="Approved",
            ),
            PRICE_APPROVAL_STATUS_UNAPPROVED,
        )

    def test_capability_is_catalogued_and_shown_in_permission_matrix(self) -> None:
        self.assertIn(Capability.APPROVE_FINAL_PRICE, ALL_CAPABILITIES)
        definition = CAPABILITY_CATALOG[Capability.APPROVE_FINAL_PRICE]
        self.assertEqual(definition.key, "approve_final_price")
        self.assertEqual(definition.applies_to, "Door Cutting Order")
        self.assertEqual(definition.category, "costing")
        self.assertTrue(definition.custom)

        presentation = CAPABILITY_PRESENTATION[Capability.APPROVE_FINAL_PRICE]
        self.assertEqual(presentation["label"], "Approve final price")
        self.assertIn("final order price", presentation["description"])
        self.assertEqual(presentation["risk"], "critical")

        costing_group = next(
            group for group in capability_catalog_payload() if group["key"] == "costing"
        )
        keys = {item["key"] for item in costing_group["capabilities"]}
        self.assertIn(Capability.APPROVE_FINAL_PRICE, keys)

    def test_capability_is_not_granted_by_default_or_inferred_from_other_capabilities(self) -> None:
        self.assertTrue(capability_is_ungranted_by_default({}))
        for capability in (
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_DXF,
            Capability.EDIT_ORDER,
            Capability.VIEW_ALL_ORDERS,
            Capability.PRINT_CUSTOMER_INVOICE,
        ):
            with self.subTest(capability=capability):
                state = normalize_capability_state({capability: True})
                self.assertFalse(state[Capability.APPROVE_FINAL_PRICE])

    def test_granting_final_price_adds_only_required_visibility_dependencies(self) -> None:
        state = normalize_capability_state({Capability.APPROVE_FINAL_PRICE: True})
        self.assertTrue(state[Capability.APPROVE_FINAL_PRICE])
        self.assertTrue(state[Capability.VIEW_COSTS])
        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertFalse(state[Capability.EDIT_COST_SETTINGS])
        self.assertFalse(state[Capability.EDIT_ORDER])
        self.assertFalse(state[Capability.APPROVE_SPECIAL_PRICE])
        self.assertFalse(state[Capability.EDIT_SPECIAL_PRICE])
        self.assertFalse(state[Capability.VIEW_ALL_ORDERS])

    def test_price_approval_record_access_stays_inside_order_and_cost_scope(self) -> None:
        self.assertTrue(
            can_read_price_approval_record(
                has_view_costs=True,
                can_access_parent_order=True,
            )
        )
        self.assertFalse(
            can_read_price_approval_record(
                has_view_costs=False,
                can_access_parent_order=True,
            )
        )
        self.assertFalse(
            can_read_price_approval_record(
                has_view_costs=True,
                can_access_parent_order=False,
            )
        )
        self.assertFalse(can_mutate_price_approval_via_desk())

        projection = supporting_standard_permission_projection(
            "Door Cutting Price Approval",
            {Capability.VIEW_COSTS: True},
        )
        self.assertEqual(
            projection,
            {
                "read": True,
                "select": True,
                "create": False,
                "write": False,
                "delete": False,
            },
        )
        self.assertIn("Door Cutting Price Approval", SUPPORTING_DOCTYPES)

        approval_fields = _fields(APPROVAL_SCHEMA)
        self.assertEqual(approval_fields["validity_status"]["options"], "Active\nInvalidated")
        self.assertEqual(json.loads(APPROVAL_SCHEMA.read_text(encoding="utf-8"))["permissions"], [])

    def test_direct_save_cannot_forge_price_approval_fields(self) -> None:
        with self.assertRaises(PriceApprovalFieldForgeryError):
            assert_order_price_approval_fields_unchanged(
                previous_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
                previous_link=None,
                incoming_status=PRICE_APPROVAL_STATUS_APPROVED,
                incoming_link="DCPA-00001",
                allow_mutation=False,
                is_new=False,
            )

        with self.assertRaises(PriceApprovalFieldForgeryError):
            assert_order_price_approval_fields_unchanged(
                previous_status=None,
                previous_link=None,
                incoming_status=PRICE_APPROVAL_STATUS_APPROVED,
                incoming_link=None,
                allow_mutation=False,
                is_new=True,
            )

        assert_order_price_approval_fields_unchanged(
            previous_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            previous_link=None,
            incoming_status=PRICE_APPROVAL_STATUS_APPROVED,
            incoming_link="DCPA-00001",
            allow_mutation=True,
            is_new=False,
        )

        with self.assertRaises(PriceApprovalRecordMutationError):
            assert_price_approval_record_immutable(
                is_new=False,
                allow_status_transition=False,
                previous_validity=PRICE_APPROVAL_VALIDITY_ACTIVE,
                incoming_validity=PRICE_APPROVAL_VALIDITY_INVALIDATED,
            )

        assert_price_approval_record_immutable(
            is_new=False,
            allow_status_transition=True,
            previous_validity=PRICE_APPROVAL_VALIDITY_ACTIVE,
            incoming_validity=PRICE_APPROVAL_VALIDITY_INVALIDATED,
        )

    def test_copy_does_not_inherit_source_approval(self) -> None:
        fields = _fields(ORDER_SCHEMA)
        self.assertEqual(fields["price_approval_status"].get("no_copy"), 1)
        self.assertEqual(fields["current_price_approval"].get("no_copy"), 1)

    def test_migrate_helpers_are_idempotent_and_preserve_later_grants(self) -> None:
        patch_name = "almdina_erp.patches.v1_0.install_final_price_approval_phase1"
        self.assertIn(patch_name, PATCHES.read_text(encoding="utf-8"))
        self.assertTrue(capability_is_ungranted_by_default({Capability.VIEW_COSTS: True}))
        self.assertTrue(
            preserve_existing_capability_grants(
                {Capability.APPROVE_FINAL_PRICE: True},
                {Capability.APPROVE_FINAL_PRICE: True},
            )
        )
        self.assertTrue(
            preserve_existing_capability_grants(
                {Capability.APPROVE_FINAL_PRICE: False},
                {Capability.APPROVE_FINAL_PRICE: False},
            )
        )
        self.assertFalse(
            preserve_existing_capability_grants(
                {Capability.APPROVE_FINAL_PRICE: True},
                {Capability.APPROVE_FINAL_PRICE: False},
            )
        )

        hooks = HOOKS.read_text(encoding="utf-8")
        self.assertIn("Door Cutting Price Approval", hooks)
        self.assertIn("door_cutting_price_approval_has_permission", hooks)
        self.assertIn("door_cutting_price_approval_query", hooks)

        translations = TRANSLATIONS.read_text(encoding="utf-8")
        self.assertIn("Price approval status,حالة السعر", translations)
        self.assertIn("Approve final price,اعتماد السعر", translations)


if __name__ == "__main__":
    unittest.main()
