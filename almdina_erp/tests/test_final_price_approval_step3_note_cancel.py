"""Step 3: optional approval_note on approve + manual cancel command."""

from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    approve_order_final_price,
    cancel_order_final_price_approval,
    decide_final_price_approval_actions,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    fingerprint_final_price_basis,
    price_basis_token,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    MANUAL_PRICE_APPROVAL_CANCELLED,
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
    ApprovalNoteError,
    FinalPriceCancellationError,
    can_edit_cost_settings_for_order,
    cost_settings_locked_by_price_approval,
    normalize_approval_note,
)

from almdina_erp.tests.test_final_price_approval_phase2 import (
    FakeApproval,
    FakeGateway,
    FakeOrder,
    FakePlan,
    _basis,
)
from almdina_erp.tests.test_final_price_approval_step2_unlock_invalidate import (
    TestFinalPriceApprovalStep2UnlockInvalidate,
)


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "final_price_approval_service.py"
CONTRACTS = ROOT / "tests" / "security_endpoint_contracts.py"
COST_SERVICE = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
TRANSLATIONS = ROOT / "translations" / "ar.csv"
APPLICATION = ROOT / "almdina_erp" / "application" / "orders" / "final_price_approval.py"


def _approved_gateway(*, note: str | None = "ملاحظة أصلية") -> FakeGateway:
    basis = _basis()
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
        approval_note=note,
    )
    order = FakeOrder(
        name="DCO-1",
        price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
        current_price_approval="DCPA-00001",
    )
    return FakeGateway(
        order=order,
        plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
        basis=basis,
        active=approval,
        approvals=[approval],
    )


class TestFinalPriceApprovalStep3NoteCancel(unittest.TestCase):
    def test_approve_without_and_with_arabic_multiline_note(self) -> None:
        basis = _basis()
        token = price_basis_token(fingerprint_final_price_basis(basis))
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
            basis=basis,
        )
        bare = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
        )
        self.assertIsNone(bare.approval_note)
        self.assertIsNone(gateway.approvals[0].approval_note)

        gateway2 = FakeGateway(
            order=FakeOrder(name="DCO-2"),
            plan=FakePlan(name="PLAN-2", door_cutting_order="DCO-2"),
            basis=basis,
        )
        note = "ملاحظة عربية\nسطر ثاني"
        with_note = approve_order_final_price(
            gateway2,
            order_name="DCO-2",
            expected_price_basis_token=token,
            approval_note=note,
        )
        self.assertEqual(with_note.approval_note, note)
        self.assertEqual(gateway2.approvals[0].approval_note, note)

    def test_rejects_non_text_and_overlong_note(self) -> None:
        basis = _basis()
        token = price_basis_token(fingerprint_final_price_basis(basis))
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
            basis=basis,
        )
        with self.assertRaises(ApprovalNoteError):
            approve_order_final_price(
                gateway,
                order_name="DCO-1",
                expected_price_basis_token=token,
                approval_note=123,  # type: ignore[arg-type]
            )
        with self.assertRaises(ApprovalNoteError):
            approve_order_final_price(
                gateway,
                order_name="DCO-1",
                expected_price_basis_token=token,
                approval_note="x" * 501,
            )
        self.assertEqual(gateway.approvals, [])

    def test_note_outside_fingerprint_and_repeat_keeps_original(self) -> None:
        basis = _basis()
        digest = fingerprint_final_price_basis(basis)
        token = price_basis_token(digest)
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
            basis=basis,
        )
        first = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
            approval_note="الأولى",
        )
        self.assertEqual(first.pricing_basis_fingerprint, digest)
        second = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
            approval_note="ملاحظة مختلفة",
        )
        self.assertTrue(second.reused_existing)
        self.assertEqual(second.approval_note, "الأولى")
        self.assertEqual(gateway.approvals[0].approval_note, "الأولى")
        self.assertEqual(len(gateway.approvals), 1)

    def test_manual_cancel_with_cancel_capability_only(self) -> None:
        gateway = _approved_gateway()
        result = cancel_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            expected_current_price_approval="DCPA-00001",
        )
        self.assertTrue(result.cancelled_now)
        self.assertEqual(result.reason, MANUAL_PRICE_APPROVAL_CANCELLED)
        self.assertEqual(result.price_approval_status, PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertIsNone(result.current_price_approval)
        self.assertEqual(result.cancelled_approval, "DCPA-00001")
        approval = gateway.approvals[0]
        self.assertEqual(approval.validity_status, PRICE_APPROVAL_VALIDITY_INVALIDATED)
        self.assertEqual(approval.approval_note, "ملاحظة أصلية")
        self.assertEqual(approval.invalidated_by, "approver@example.com")
        self.assertEqual(approval.invalidation_reason, MANUAL_PRICE_APPROVAL_CANCELLED)
        self.assertEqual(gateway.locks[:2], ["order:DCO-1", "approval:DCPA-00001"])

        decision = decide_final_price_approval_actions(
            has_approve_final_price=False,
            has_view_costs=True,
            has_edit_cost_settings=False,
            has_cancel_final_price_approval=True,
            price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
            current_price_approval="DCPA-00001",
            price_basis_token_value="1:abc",
            order_status="In Production",
            revision_state="Current",
            docstatus=0,
        )
        self.assertTrue(decision.can_cancel_final_price_approval)
        self.assertFalse(decision.can_approve_final_price)

        approve_only = decide_final_price_approval_actions(
            has_approve_final_price=True,
            has_view_costs=True,
            has_edit_cost_settings=True,
            has_cancel_final_price_approval=False,
            price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
            current_price_approval="DCPA-00001",
            price_basis_token_value="1:abc",
        )
        self.assertFalse(approve_only.can_cancel_final_price_approval)
        self.assertEqual(approve_only.cancel_reason_code, "missing_capability")

    def test_cancel_across_production_stages_without_operational_mutation(self) -> None:
        for status in ("Draft", "Drawing", "CNC", "Sanding", "Ready for Delivery"):
            gateway = _approved_gateway()
            gateway.order.status = status
            gateway.order.current_production_stage = "CNC"
            gateway.order.current_assignee = "worker@example.com"
            gateway.order.approved_plan = "PLAN-APPROVED"
            cancel_order_final_price_approval(
                gateway,
                order_name="DCO-1",
                expected_current_price_approval="DCPA-00001",
            )
            self.assertEqual(gateway.order.status, status)
            self.assertEqual(gateway.order.current_production_stage, "CNC")
            self.assertEqual(gateway.order.current_assignee, "worker@example.com")
            self.assertEqual(gateway.order.approved_plan, "PLAN-APPROVED")

    def test_cancel_allowed_when_plan_is_stale(self) -> None:
        gateway = _approved_gateway()
        gateway.plan_current = False
        result = cancel_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            expected_current_price_approval="DCPA-00001",
        )
        self.assertTrue(result.cancelled_now)

    def test_cancel_idempotent_replay_preserves_invalidation_history(self) -> None:
        gateway = _approved_gateway()
        first = cancel_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            expected_current_price_approval="DCPA-00001",
        )
        self.assertTrue(first.cancelled_now)
        approval = gateway.approvals[0]
        when = approval.invalidated_on
        who = approval.invalidated_by
        second = cancel_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            expected_current_price_approval="DCPA-00001",
        )
        self.assertFalse(second.cancelled_now)
        self.assertEqual(approval.invalidated_on, when)
        self.assertEqual(approval.invalidated_by, who)
        self.assertEqual(approval.approval_note, "ملاحظة أصلية")

    def test_rejects_foreign_or_newer_active_approval(self) -> None:
        gateway = _approved_gateway()
        foreign = FakeApproval(
            name="DCPA-OTHER",
            door_cutting_order="DCO-OTHER",
            cutting_plan="PLAN-X",
            approved_amount=1,
            currency="USD",
            approved_by="x",
            approved_on="2026-10-14 12:00:00",
            pricing_basis_fingerprint="abc",
            fingerprint_formula_version="1",
        )
        gateway.approvals.append(foreign)
        with self.assertRaises(FinalPriceCancellationError) as foreign_err:
            cancel_order_final_price_approval(
                gateway,
                order_name="DCO-1",
                expected_current_price_approval="DCPA-OTHER",
            )
        self.assertEqual(foreign_err.exception.code, "foreign_approval")

        newer = FakeApproval(
            name="DCPA-00002",
            door_cutting_order="DCO-1",
            cutting_plan="PLAN-1",
            approved_amount=25.5,
            currency="USD",
            approved_by="approver@example.com",
            approved_on="2026-10-15 12:00:00",
            pricing_basis_fingerprint=gateway.active.pricing_basis_fingerprint,
            fingerprint_formula_version="1",
        )
        gateway.approvals.append(newer)
        gateway.active = newer
        gateway.order.current_price_approval = "DCPA-00002"
        with self.assertRaises(FinalPriceCancellationError) as stale_err:
            cancel_order_final_price_approval(
                gateway,
                order_name="DCO-1",
                expected_current_price_approval="DCPA-00001",
            )
        self.assertEqual(stale_err.exception.code, "approval_changed")
        self.assertEqual(newer.validity_status, PRICE_APPROVAL_VALIDITY_ACTIVE)

    def test_failed_invalidate_leaves_approval_active(self) -> None:
        gateway = _approved_gateway()
        gateway.fail_insert = False

        def boom(approval, *, reason, actor=None):
            raise RuntimeError("write failed")

        gateway.invalidate_approval = boom  # type: ignore[method-assign]
        with self.assertRaises(RuntimeError):
            cancel_order_final_price_approval(
                gateway,
                order_name="DCO-1",
                expected_current_price_approval="DCPA-00001",
            )
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(gateway.order.current_price_approval, "DCPA-00001")

    def test_reapprove_after_cancel_creates_independent_note(self) -> None:
        gateway = _approved_gateway(note="قديمة")
        cancel_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            expected_current_price_approval="DCPA-00001",
        )
        token = price_basis_token(fingerprint_final_price_basis(gateway.basis))
        fresh = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
            approval_note="جديدة بعد الإلغاء",
        )
        self.assertFalse(fresh.reused_existing)
        self.assertEqual(fresh.approval_note, "جديدة بعد الإلغاء")
        self.assertEqual(gateway.approvals[0].approval_note, "قديمة")
        self.assertEqual(gateway.approvals[1].approval_note, "جديدة بعد الإلغاء")

    def test_step2_unlock_and_algorithm_contracts_still_hold(self) -> None:
        # Cross-check: step-2 policy must remain intact after step-3 wiring.
        self.assertFalse(cost_settings_locked_by_price_approval(PRICE_APPROVAL_STATUS_APPROVED))
        self.assertTrue(
            can_edit_cost_settings_for_order(
                has_edit_cost_settings=True,
                price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
            )
        )
        TestFinalPriceApprovalStep2UnlockInvalidate().test_algorithm_same_board_count_keeps_approval()
        TestFinalPriceApprovalStep2UnlockInvalidate().test_stale_form_fields_are_reconciled_not_rejected()

    def test_service_and_contracts_wire_note_and_cancel(self) -> None:
        service = SERVICE.read_text(encoding="utf-8")
        self.assertIn("approval_note", service)
        self.assertIn("cancel_order_final_price_approval as run_cancel_order_final_price_approval", service)
        self.assertIn("run_cancel_order_final_price_approval(", service)
        self.assertIn("Capability.CANCEL_FINAL_PRICE_APPROVAL", service)
        self.assertIn('"final_price_approval_invalidated": False', service)
        self.assertIn("MANUAL_PRICE_APPROVAL_CANCELLED", APPLICATION.read_text(encoding="utf-8"))
        contracts = CONTRACTS.read_text(encoding="utf-8")
        self.assertIn("cancel_order_final_price_approval", contracts)
        cost = COST_SERVICE.read_text(encoding="utf-8")
        self.assertIn("can_cancel_final_price_approval", cost)
        self.assertIn("approval_note", cost)
        translations = TRANSLATIONS.read_text(encoding="utf-8")
        for key in (
            "Final-price cancellation capability is required.",
            "The price approval changed since this page was loaded. Refresh and review before cancelling.",
            "There is no active final-price approval to cancel.",
            "Approval note must be text.",
            "Approval note cannot exceed 500 characters.",
        ):
            self.assertTrue(
                f"{key}," in translations or f'"{key}",' in translations,
                msg=f"missing Arabic for {key}",
            )

    def test_normalize_still_central(self) -> None:
        self.assertEqual(normalize_approval_note("  hi  "), "hi")
        self.assertIsNone(normalize_approval_note("   "))


if __name__ == "__main__":
    unittest.main()
