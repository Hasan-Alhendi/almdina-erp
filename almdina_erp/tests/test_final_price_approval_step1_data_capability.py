"""Step 1: approval note, invalidated_by protection, cancel capability."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.security.final_price_approval_migration import (
    cancel_capability_is_ungranted_by_default,
    preserve_cancel_capability_grants,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
    capability_catalog_payload,
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    build_final_price_basis_payload,
    build_order_pricing_input_payload,
    fingerprint_final_price_basis,
    fingerprint_order_pricing_inputs,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    APPROVAL_NOTE_MAX_LENGTH,
    PROTECTED_APPROVAL_HISTORY_FIELDS,
    ApprovalNoteError,
    PriceApprovalRecordMutationError,
    assert_invalidated_by_mutation_allowed,
    assert_invalidation_preserves_approval_details,
    normalize_approval_note,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_SCHEMA = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_price_approval"
    / "door_cutting_price_approval.json"
)
CONTROLLER = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_price_approval"
    / "door_cutting_price_approval.py"
)
BASIS_MODULE = ROOT / "almdina_erp" / "domain" / "orders" / "final_price_basis.py"
TRANSLATIONS = ROOT / "translations" / "ar.csv"


def _fields(schema_path: Path) -> dict[str, dict]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in schema["fields"]}


def _piece(**overrides: Any) -> dict[str, Any]:
    row = {
        "piece_no": 1,
        "piece_type": "Regular",
        "qty": 1,
        "factory_execution_qty": 1,
        "width_cm": 40,
        "length_cm": 80,
        "allow_rotation": 1,
        "edge_type": "PVC",
        "edge_meters": 1.2,
        "edge_rate_usd": 0.5,
        "edge_cost_usd": 0.6,
        "edge_long_right": 1,
        "edge_long_left": 1,
        "edge_width_top": 1,
        "edge_width_bottom": 1,
        "edge_break": 0,
        "edge_break_only": 0,
        "special_shape_price_status": "Not Applicable",
        "clipped_corner_edge_price_status": "Unpriced",
        "extra_double": 0,
        "extra_full_door_double": 0,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "special_shape_geometry_token": "",
    }
    row.update(overrides)
    return row


class TestFinalPriceApprovalStep1DataCapability(unittest.TestCase):
    def test_approval_note_schema_is_optional_read_only_small_text(self) -> None:
        fields = _fields(APPROVAL_SCHEMA)
        note = fields["approval_note"]
        self.assertEqual(note["fieldtype"], "Small Text")
        self.assertEqual(note["label"], "Approval note")
        self.assertEqual(note.get("read_only"), 1)
        self.assertNotEqual(note.get("reqd"), 1)
        self.assertNotIn("default", note)
        self.assertNotEqual(note.get("in_list_view"), 1)

        invalidated_by = fields["invalidated_by"]
        self.assertEqual(invalidated_by["fieldtype"], "Link")
        self.assertEqual(invalidated_by["options"], "User")
        self.assertEqual(invalidated_by["label"], "Invalidated by")
        self.assertEqual(invalidated_by.get("read_only"), 1)
        self.assertNotEqual(invalidated_by.get("reqd"), 1)

        schema = json.loads(APPROVAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertIn("approval_note", schema["field_order"])
        self.assertIn("invalidated_by", schema["field_order"])
        self.assertEqual(schema["permissions"], [])

    def test_normalize_approval_note_accepts_absent_blank_arabic_and_multiline(self) -> None:
        self.assertIsNone(normalize_approval_note(None))
        self.assertIsNone(normalize_approval_note(""))
        self.assertIsNone(normalize_approval_note("   \n  "))
        self.assertEqual(normalize_approval_note("  ملاحظة اعتماد  "), "ملاحظة اعتماد")
        self.assertEqual(
            normalize_approval_note("سطر أول\nسطر ثاني\n"),
            "سطر أول\nسطر ثاني",
        )
        self.assertEqual(APPROVAL_NOTE_MAX_LENGTH, 500)
        self.assertEqual(
            normalize_approval_note("x" * APPROVAL_NOTE_MAX_LENGTH),
            "x" * APPROVAL_NOTE_MAX_LENGTH,
        )

    def test_normalize_approval_note_rejects_non_text_and_overlong(self) -> None:
        with self.assertRaisesRegex(ApprovalNoteError, "must be text"):
            normalize_approval_note(123)
        with self.assertRaisesRegex(ApprovalNoteError, "must be text"):
            normalize_approval_note(["note"])
        with self.assertRaisesRegex(ApprovalNoteError, "500"):
            normalize_approval_note("x" * (APPROVAL_NOTE_MAX_LENGTH + 1))

    def test_invalidation_cannot_rewrite_approval_note_or_other_history(self) -> None:
        previous = {
            "door_cutting_order": "DCO-1",
            "cutting_plan": "PLAN-1",
            "approved_amount": 10.0,
            "currency": "USD",
            "approved_by": "approver@example.com",
            "approved_on": "2026-10-14 12:00:00",
            "pricing_basis_fingerprint": "abc",
            "fingerprint_formula_version": "1",
            "approval_note": "ملاحظة أصلية",
        }
        same = dict(previous)
        assert_invalidation_preserves_approval_details(previous=previous, incoming=same)

        changed_note = dict(previous, approval_note="ملاحظة معدّلة")
        with self.assertRaises(PriceApprovalRecordMutationError):
            assert_invalidation_preserves_approval_details(
                previous=previous,
                incoming=changed_note,
            )
        self.assertIn("approval_note", PROTECTED_APPROVAL_HISTORY_FIELDS)

        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("assert_invalidation_preserves_approval_details", controller)
        self.assertIn("normalize_approval_note", controller)
        self.assertIn("assert_invalidated_by_mutation_allowed", controller)

    def test_approval_note_is_outside_pricing_fingerprint_inputs(self) -> None:
        pieces = [_piece()]
        basis = build_final_price_basis_payload(
            cutting_plan="PLAN-1",
            currency="USD",
            plan_costs={
                "board_rate_usd": 10,
                "cutting_cost_per_board_usd": 1,
                "offcut_price_usd": 0,
                "mdf_cost_usd": 20,
                "cutting_cost_usd": 2,
                "edge_cost_usd": 3,
                "total_cost_usd": 25,
            },
            required_boards=2,
            pieces=pieces,
            offcut_applicable=False,
            offcut_assignments=[],
            invoice_preview_total_usd=25.5,
            customer_quote_total_usd=25.5,
        )
        encoded = json.dumps(basis, ensure_ascii=False)
        self.assertNotIn("approval_note", encoded)
        # Fingerprint is derived from the commercial payload only.
        before = fingerprint_final_price_basis(basis)
        # The builder never emits the note; callers must not inject it into basis.
        rebuilt = build_final_price_basis_payload(
            cutting_plan="PLAN-1",
            currency="USD",
            plan_costs={
                "board_rate_usd": 10,
                "cutting_cost_per_board_usd": 1,
                "offcut_price_usd": 0,
                "mdf_cost_usd": 20,
                "cutting_cost_usd": 2,
                "edge_cost_usd": 3,
                "total_cost_usd": 25,
            },
            required_boards=2,
            pieces=pieces,
            offcut_applicable=False,
            offcut_assignments=[],
            invoice_preview_total_usd=25.5,
            customer_quote_total_usd=25.5,
        )
        self.assertEqual(fingerprint_final_price_basis(rebuilt), before)
        self.assertNotIn("approval_note", rebuilt)

        order_inputs = build_order_pricing_input_payload(pieces=pieces)
        self.assertNotIn("approval_note", json.dumps(order_inputs, ensure_ascii=False))
        fingerprint_order_pricing_inputs(order_inputs)

        basis_source = BASIS_MODULE.read_text(encoding="utf-8")
        self.assertIn("approval_note", basis_source)

    def test_invalidated_by_requires_authorized_invalidation_transition(self) -> None:
        assert_invalidated_by_mutation_allowed(
            allow_authorized_invalidation=False,
            previous_invalidated_by=None,
            incoming_invalidated_by=None,
        )
        assert_invalidated_by_mutation_allowed(
            allow_authorized_invalidation=True,
            previous_invalidated_by=None,
            incoming_invalidated_by="operator@example.com",
        )
        with self.assertRaises(PriceApprovalRecordMutationError):
            assert_invalidated_by_mutation_allowed(
                allow_authorized_invalidation=False,
                previous_invalidated_by=None,
                incoming_invalidated_by="operator@example.com",
            )
        with self.assertRaises(PriceApprovalRecordMutationError):
            assert_invalidated_by_mutation_allowed(
                allow_authorized_invalidation=False,
                previous_invalidated_by="a@example.com",
                incoming_invalidated_by="b@example.com",
            )

    def test_cancel_capability_is_catalogued_and_shown_in_matrix(self) -> None:
        self.assertIn(Capability.CANCEL_FINAL_PRICE_APPROVAL, ALL_CAPABILITIES)
        definition = CAPABILITY_CATALOG[Capability.CANCEL_FINAL_PRICE_APPROVAL]
        self.assertEqual(definition.key, "cancel_final_price_approval")
        self.assertEqual(definition.applies_to, "Door Cutting Order")
        self.assertEqual(definition.category, "costing")
        self.assertTrue(definition.custom)

        presentation = CAPABILITY_PRESENTATION[Capability.CANCEL_FINAL_PRICE_APPROVAL]
        self.assertEqual(presentation["label"], "Cancel final price approval")
        self.assertIn("keeping the approval record", presentation["description"])
        self.assertEqual(presentation["risk"], "critical")

        costing_group = next(
            group for group in capability_catalog_payload() if group["key"] == "costing"
        )
        keys = {item["key"] for item in costing_group["capabilities"]}
        self.assertIn(Capability.CANCEL_FINAL_PRICE_APPROVAL, keys)

    def test_cancel_capability_not_granted_by_default_or_from_approve(self) -> None:
        self.assertTrue(cancel_capability_is_ungranted_by_default({}))
        self.assertTrue(
            cancel_capability_is_ungranted_by_default(
                {Capability.APPROVE_FINAL_PRICE: True}
            )
        )
        for capability in (
            Capability.APPROVE_FINAL_PRICE,
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.EDIT_ORDER,
            Capability.VIEW_ALL_ORDERS,
            Capability.PRINT_CUSTOMER_INVOICE,
        ):
            with self.subTest(capability=capability):
                state = normalize_capability_state({capability: True})
                self.assertFalse(state[Capability.CANCEL_FINAL_PRICE_APPROVAL])

    def test_granting_cancel_adds_only_visibility_dependencies(self) -> None:
        state = normalize_capability_state({Capability.CANCEL_FINAL_PRICE_APPROVAL: True})
        self.assertTrue(state[Capability.CANCEL_FINAL_PRICE_APPROVAL])
        self.assertTrue(state[Capability.VIEW_COSTS])
        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertFalse(state[Capability.APPROVE_FINAL_PRICE])
        self.assertFalse(state[Capability.EDIT_COST_SETTINGS])
        self.assertFalse(state[Capability.EDIT_ORDER])
        self.assertFalse(state[Capability.APPROVE_SPECIAL_PRICE])
        self.assertFalse(state[Capability.EDIT_SPECIAL_PRICE])
        self.assertFalse(state[Capability.VIEW_ALL_ORDERS])

    def test_migrate_helpers_preserve_later_cancel_grants(self) -> None:
        self.assertTrue(
            preserve_cancel_capability_grants(
                {Capability.CANCEL_FINAL_PRICE_APPROVAL: True},
                {Capability.CANCEL_FINAL_PRICE_APPROVAL: True},
            )
        )
        self.assertTrue(
            preserve_cancel_capability_grants(
                {Capability.CANCEL_FINAL_PRICE_APPROVAL: False},
                {Capability.CANCEL_FINAL_PRICE_APPROVAL: False},
            )
        )
        self.assertFalse(
            preserve_cancel_capability_grants(
                {Capability.CANCEL_FINAL_PRICE_APPROVAL: True},
                {Capability.CANCEL_FINAL_PRICE_APPROVAL: False},
            )
        )

    def test_translations_cover_note_actor_and_cancel_capability(self) -> None:
        translations = TRANSLATIONS.read_text(encoding="utf-8")
        self.assertIn("Approval note,ملاحظة الاعتماد", translations)
        self.assertIn("Invalidated by,أُلغي اعتماده بواسطة", translations)
        self.assertIn("Cancel final price approval,إلغاء اعتماد السعر", translations)
        self.assertIn(
            "Cancel the order's final price approval while keeping the approval record and its details.",
            translations,
        )


if __name__ == "__main__":
    unittest.main()
