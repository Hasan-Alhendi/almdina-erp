"""Step 2: unlock cost edits, auto-invalidate, save reconcile, algorithm exception."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    decide_final_price_approval_actions,
    invalidate_order_final_price_approval,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    build_final_price_basis_payload,
    build_order_pricing_input_payload,
    fingerprint_final_price_basis,
    fingerprint_order_pricing_inputs,
    pricing_basis_commercially_equivalent,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
    can_edit_cost_settings_for_order,
    cost_settings_locked_by_price_approval,
    reconcile_order_price_approval_fields,
)


ROOT = Path(__file__).resolve().parents[1]
COST_SERVICE = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
PLAN_COST_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_cost_command_service.py"
DOCUMENT_ACCESS = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "document_access.py"
)
APPROVAL_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_final_price_approval_ux.js"
)
EDIT_SESSION = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_edit_session_ux.js"
)
DOC_CONTEXT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_document_context.js"
)
APPLICATION = ROOT / "almdina_erp" / "application" / "orders" / "final_price_approval.py"
TRANSLATIONS = ROOT / "translations" / "ar.csv"


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


def _basis(**overrides: Any) -> dict[str, Any]:
    payload = build_final_price_basis_payload(
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
        required_boards=4,
        pieces=[_piece()],
        offcut_applicable=False,
        offcut_assignments=[],
        invoice_preview_total_usd=25.5,
        customer_quote_total_usd=25.5,
    )
    payload.update(overrides)
    return payload


class TestFinalPriceApprovalStep2UnlockInvalidate(unittest.TestCase):
    def test_approved_no_longer_locks_cost_settings(self) -> None:
        self.assertFalse(cost_settings_locked_by_price_approval(PRICE_APPROVAL_STATUS_APPROVED))
        self.assertTrue(
            can_edit_cost_settings_for_order(
                has_edit_cost_settings=True,
                price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
            )
        )
        self.assertFalse(
            can_edit_cost_settings_for_order(
                has_edit_cost_settings=False,
                price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
            )
        )
        decision = decide_final_price_approval_actions(
            has_approve_final_price=True,
            has_view_costs=True,
            has_edit_cost_settings=True,
            price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
            current_price_approval="DCPA-1",
            price_basis_token_value="1:abc",
        )
        self.assertTrue(decision.can_edit_cost_settings)

        cost_source = COST_SERVICE.read_text(encoding="utf-8")
        plan_cost = PLAN_COST_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("assert_cost_settings_unlocked_for_order", cost_source)
        self.assertNotIn("assert_cost_settings_unlocked_for_order", plan_cost)
        self.assertIn("maybe_invalidate_final_price_approval", plan_cost)
        self.assertIn("cost_settings_changed", plan_cost)

    def test_stale_form_fields_are_reconciled_not_rejected(self) -> None:
        status, link = reconcile_order_price_approval_fields(
            previous_status=PRICE_APPROVAL_STATUS_APPROVED,
            previous_link="DCPA-00001",
            incoming_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            incoming_link=None,
            allow_mutation=False,
            is_new=False,
        )
        self.assertEqual(status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(link, "DCPA-00001")

        forged_status, forged_link = reconcile_order_price_approval_fields(
            previous_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            previous_link=None,
            incoming_status=PRICE_APPROVAL_STATUS_APPROVED,
            incoming_link="DCPA-FORGED",
            allow_mutation=False,
            is_new=False,
        )
        self.assertEqual(forged_status, PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertIsNone(forged_link)

        access = DOCUMENT_ACCESS.read_text(encoding="utf-8")
        self.assertIn("reconcile_order_price_approval_fields", access)
        self.assertNotIn("assert_order_price_approval_fields_unchanged", access)

    def test_algorithm_same_board_count_keeps_approval(self) -> None:
        original = _basis(cutting_plan="PLAN-1", required_boards=4)
        digest = fingerprint_final_price_basis(original)
        same_boards_new_plan = _basis(cutting_plan="PLAN-2", required_boards=4)
        self.assertTrue(
            pricing_basis_commercially_equivalent(
                stored_fingerprint=digest,
                stored_cutting_plan="PLAN-1",
                current_basis=same_boards_new_plan,
            )
        )
        fewer_boards = _basis(cutting_plan="PLAN-2", required_boards=3)
        self.assertFalse(
            pricing_basis_commercially_equivalent(
                stored_fingerprint=digest,
                stored_cutting_plan="PLAN-1",
                current_basis=fewer_boards,
            )
        )
        rate_changed = build_final_price_basis_payload(
            cutting_plan="PLAN-2",
            currency="USD",
            plan_costs={
                "board_rate_usd": 12,
                "cutting_cost_per_board_usd": 1,
                "offcut_price_usd": 0,
                "mdf_cost_usd": 24,
                "cutting_cost_usd": 2,
                "edge_cost_usd": 3,
                "total_cost_usd": 29,
            },
            required_boards=4,
            pieces=[_piece()],
            offcut_applicable=False,
            offcut_assignments=[],
            invoice_preview_total_usd=29.5,
            customer_quote_total_usd=29.5,
        )
        self.assertFalse(
            pricing_basis_commercially_equivalent(
                stored_fingerprint=digest,
                stored_cutting_plan="PLAN-1",
                current_basis=rate_changed,
            )
        )
        app = APPLICATION.read_text(encoding="utf-8")
        self.assertIn("pricing_basis_commercially_equivalent", app)

    def test_ux_removes_lock_note_and_wires_toast(self) -> None:
        ux = APPROVAL_UX.read_text(encoding="utf-8")
        self.assertNotIn(
            "Cost settings are locked because the final price is approved.",
            ux,
        )
        self.assertIn("The price approval for this order has been cancelled", ux)
        self.assertIn("cancel_final_price_approval", ux)
        self.assertIn("consumeInvalidationSignal", ux)
        self.assertIn("syncFormPriceApprovalFields", ux)

        edit = EDIT_SESSION.read_text(encoding="utf-8")
        self.assertNotIn(
            "Cost settings are locked because the final price is approved.",
            edit,
        )
        self.assertIn("consumeInvalidationSignal", edit)

        context = DOC_CONTEXT.read_text(encoding="utf-8")
        self.assertIn("capturePriorPriceApprovalStatus", context)
        self.assertIn("afterOrderSave", context)

        translations = TRANSLATIONS.read_text(encoding="utf-8")
        self.assertIn(
            "The price approval for this order has been cancelled,لقد تم إلغاء اعتماد سعر هذا الطلب",
            translations,
        )
        self.assertNotIn(
            "Cost settings are locked because the final price is approved.",
            translations,
        )

    def test_order_cutting_machine_changes_order_input_fingerprint(self) -> None:
        pieces = [_piece()]
        cnc = build_order_pricing_input_payload(
            pieces=pieces,
            order_cutting_machine="CNC",
        )
        saw = build_order_pricing_input_payload(
            pieces=pieces,
            order_cutting_machine="مشرحة",
        )
        self.assertNotEqual(
            fingerprint_order_pricing_inputs(cnc),
            fingerprint_order_pricing_inputs(saw),
        )
        gateway = (
            ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "final_price_approval_gateway.py"
        ).read_text(encoding="utf-8")
        self.assertIn("order_cutting_machine", gateway)


class TestFinalPriceApprovalStep2InvalidationGateway(unittest.TestCase):
    def test_only_if_basis_changed_ignores_plan_identity_alone(self) -> None:
        from almdina_erp.tests.test_final_price_approval_phase3 import (
            FakeApproval,
            FakeGateway,
            FakeOrder,
            FakePlan,
            _basis,
            _piece,
        )

        basis = _basis(cutting_plan="PLAN-1")
        # Align with 4-board commercial scenarios used above when needed.
        basis = dict(basis)
        digest = fingerprint_final_price_basis(basis)
        approval = FakeApproval(
            name="DCPA-00001",
            door_cutting_order="DCO-1",
            cutting_plan="PLAN-1",
            approved_amount=25.5,
            currency="USD",
            approved_by="approver@example.com",
            approved_on="2026-10-14 12:00:00",
            pricing_basis_fingerprint=digest,
            fingerprint_formula_version="1",
            approval_note="ملاحظة",
        )
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-2", door_cutting_order="DCO-1"),
            basis=dict(basis, cutting_plan="PLAN-2"),
            active=approval,
            approvals=[approval],
        )
        kept = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="cost_plan_basis_changed",
            only_if_basis_changed=True,
        )
        self.assertFalse(kept.invalidated)
        self.assertEqual(approval.validity_status, PRICE_APPROVAL_VALIDITY_ACTIVE)
        self.assertEqual(approval.approval_note, "ملاحظة")

        gateway.basis = dict(basis, cutting_plan="PLAN-2")
        gateway.basis["plan"] = dict(gateway.basis["plan"], required_boards=3)
        # Rebuild fingerprint path through commercially different boards.
        gateway.basis = build_final_price_basis_payload(
            cutting_plan="PLAN-2",
            currency="USD",
            plan_costs={
                "board_rate_usd": 10,
                "cutting_cost_per_board_usd": 1,
                "offcut_price_usd": 0,
                "mdf_cost_usd": 15,
                "cutting_cost_usd": 1.5,
                "edge_cost_usd": 3,
                "total_cost_usd": 19.5,
            },
            required_boards=3,
            pieces=[_piece()],
            offcut_applicable=False,
            offcut_assignments=[],
            invoice_preview_total_usd=20.0,
            customer_quote_total_usd=20.0,
        )
        cleared = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="cost_plan_basis_changed",
            only_if_basis_changed=True,
        )
        self.assertTrue(cleared.invalidated)
        self.assertEqual(approval.validity_status, PRICE_APPROVAL_VALIDITY_INVALIDATED)
        self.assertEqual(approval.approval_note, "ملاحظة")
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_UNAPPROVED)


if __name__ == "__main__":
    unittest.main()
