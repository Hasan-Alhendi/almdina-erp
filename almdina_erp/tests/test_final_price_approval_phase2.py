"""Phase 2 contracts for commercial final-price approval."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    FinalPriceApprovalTokenError,
    approve_order_final_price,
    decide_final_price_approval_actions,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    COST_SETTINGS_FIELDS,
    build_final_price_basis_payload,
    fingerprint_final_price_basis,
    parse_price_basis_token,
    price_basis_token,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    FinalPriceApprovalEligibilityError,
    assert_order_price_approval_fields_unchanged,
    can_edit_cost_settings_for_order,
    cost_settings_locked_by_price_approval,
    evaluate_final_price_approval_eligibility,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
COST_SERVICE = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
PLAN_COST_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_cost_command_service.py"
APPROVAL_SERVICE = ROOT / "almdina_erp" / "services" / "final_price_approval_service.py"
ENDPOINT_CONTRACTS = ROOT / "tests" / "security_endpoint_contracts.py"


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
        required_boards=2,
        pieces=[
            {
                "piece_no": 1,
                "piece_type": "Regular",
                "qty": 1,
                "factory_execution_qty": 1,
                "edge_type": "PVC",
                "edge_meters": 1.2,
                "edge_rate_usd": 0.5,
                "edge_cost_usd": 0.6,
                "special_shape_price_status": "Not Applicable",
                "clipped_corner_edge_price_status": "Unpriced",
            }
        ],
        offcut_applicable=False,
        offcut_assignments=[],
        invoice_preview_total_usd=25.5,
        customer_quote_total_usd=25.5,
    )
    payload.update(overrides)
    return payload


@dataclass
class FakeApproval:
    name: str
    door_cutting_order: str
    cutting_plan: str
    approved_amount: float
    currency: str
    approved_by: str
    approved_on: str
    pricing_basis_fingerprint: str
    fingerprint_formula_version: str
    validity_status: str = PRICE_APPROVAL_VALIDITY_ACTIVE
    approval_note: str | None = None
    invalidation_reason: str | None = None
    invalidated_on: str | None = None
    invalidated_by: str | None = None


@dataclass
class FakeOrder:
    name: str
    status: str = "Draft"
    revision_state: str = "Current"
    docstatus: int = 0
    price_approval_status: str = PRICE_APPROVAL_STATUS_UNAPPROVED
    current_price_approval: str | None = None
    current_production_stage: str | None = None
    current_department: str | None = None
    current_assignee: str | None = None
    approved_plan: str | None = None
    department_status: str | None = None
    production_path: str | None = None


@dataclass
class FakePlan:
    name: str
    door_cutting_order: str
    required_boards: int = 2
    cost_snapshot_version: int = 1
    board_rate_usd: float = 10
    cutting_cost_per_board_usd: float = 1
    offcut_price_usd: float = 0


@dataclass
class FakeGateway:
    order: FakeOrder
    plan: FakePlan
    basis: dict[str, Any]
    pending: tuple[str, ...] = ()
    plan_current: bool = True
    board_present: bool = True
    cutting_present: bool = True
    active: FakeApproval | None = None
    fail_insert: bool = False
    approvals: list[FakeApproval] = field(default_factory=list)
    order_updates: list[tuple[str, str]] = field(default_factory=list)
    locks: list[str] = field(default_factory=list)

    def lock_order(self, order_name: str) -> FakeOrder:
        self.locks.append(f"order:{order_name}")
        return self.order

    def lock_cost_plan(self, plan_name: str) -> FakePlan:
        self.locks.append(f"plan:{plan_name}")
        return self.plan

    def resolve_cost_plan(self, order: FakeOrder) -> FakePlan | None:
        return self.plan

    def plan_belongs_to_order(self, plan: FakePlan, order_name: str) -> bool:
        return plan.door_cutting_order == order_name

    def plan_is_current(self, order: FakeOrder, plan: FakePlan) -> bool:
        return self.plan_current

    def build_basis_payload(self, order: FakeOrder, plan: FakePlan) -> dict[str, Any]:
        return dict(self.basis)

    def pending_price_labels(self, order: FakeOrder, plan: FakePlan) -> tuple[str, ...]:
        return self.pending

    def cost_input_presence(self, plan: FakePlan) -> tuple[bool, bool]:
        return self.board_present, self.cutting_present

    def find_active_approval(self, order_name: str) -> FakeApproval | None:
        return self.active

    def load_approval(self, approval_name: str) -> FakeApproval | None:
        for row in self.approvals:
            if row.name == approval_name:
                return row
        if self.active and self.active.name == approval_name:
            return self.active
        return None

    def lock_approval(self, approval_name: str) -> FakeApproval | None:
        self.locks.append(f"approval:{approval_name}")
        return self.load_approval(approval_name)

    def insert_approval(self, **kwargs: Any) -> FakeApproval:
        if self.fail_insert:
            raise RuntimeError("storage failed")
        approval = FakeApproval(
            name=f"DCPA-{len(self.approvals) + 1:05d}",
            door_cutting_order=kwargs["order_name"],
            cutting_plan=kwargs["cutting_plan"],
            approved_amount=kwargs["approved_amount"],
            currency=kwargs["currency"],
            approved_by="approver@example.com",
            approved_on="2026-10-14 12:00:00",
            pricing_basis_fingerprint=kwargs["fingerprint"],
            fingerprint_formula_version=kwargs["formula_version"],
            approval_note=kwargs.get("approval_note"),
        )
        self.approvals.append(approval)
        self.active = approval
        return approval

    def update_order_price_approval(
        self,
        order_name: str,
        *,
        status: str,
        approval_name: str | None,
    ) -> None:
        self.order.price_approval_status = status
        self.order.current_price_approval = approval_name
        self.order_updates.append((status, approval_name))

    def invalidate_approval(
        self,
        approval: FakeApproval,
        *,
        reason: str,
        actor: str | None = None,
    ) -> None:
        from almdina_erp.almdina_erp.domain.orders.price_approval import (
            PRICE_APPROVAL_VALIDITY_INVALIDATED,
        )

        if approval.validity_status != PRICE_APPROVAL_VALIDITY_ACTIVE:
            return
        approval.validity_status = PRICE_APPROVAL_VALIDITY_INVALIDATED
        approval.invalidation_reason = reason
        approval.invalidated_on = "2026-10-14 13:00:00"
        approval.invalidated_by = actor
        if self.active is approval:
            self.active = None

    def current_user(self) -> str:
        return "approver@example.com"

    def now_iso(self) -> str:
        return "2026-10-14 12:00:00"


class TestFinalPriceApprovalPhase2(unittest.TestCase):
    def test_successful_approval_records_invoice_total_and_basis(self) -> None:
        basis = _basis()
        digest = fingerprint_final_price_basis(basis)
        token = price_basis_token(digest)
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
            basis=basis,
        )
        result = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
        )
        self.assertFalse(result.reused_existing)
        self.assertEqual(result.approved_amount_usd, 25.5)
        self.assertEqual(result.cutting_plan, "PLAN-1")
        self.assertEqual(result.approved_by, "approver@example.com")
        self.assertEqual(result.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(gateway.order.current_price_approval, result.current_price_approval)
        self.assertEqual(gateway.locks, ["order:DCO-1", "plan:PLAN-1"])
        self.assertEqual(basis["approved_amount_usd"], basis["invoice_preview_total_usd"])

    def test_price_status_independent_of_operational_and_special_quote_states(self) -> None:
        evaluate_final_price_approval_eligibility(
            order_name="DCO-1",
            order_status="At CNC",
            revision_state="Current",
            docstatus=0,
            cutting_plan="PLAN-1",
            plan_belongs_to_order=True,
            plan_is_current=True,
            pending_price_labels=(),
            board_rate_present=True,
            cutting_rate_present=True,
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            offcut_price_usd=0,
            approved_amount_usd=0,
        )
        self.assertFalse(cost_settings_locked_by_price_approval("Unapproved"))
        self.assertFalse(cost_settings_locked_by_price_approval("Approved"))

    def test_eligibility_allows_multiple_production_stages_including_post_drawing(self) -> None:
        """Final-price approval is not Draft-only and ignores production department."""

        production_statuses = (
            "Draft",
            "Drawing",
            "At CNC",
            "CNC",
            "Sanding",
            "Ready for Delivery",
            "On Hold",
            "Partially Completed",
        )
        for status in production_statuses:
            with self.subTest(order_status=status):
                evaluate_final_price_approval_eligibility(
                    order_name="DCO-1",
                    order_status=status,
                    revision_state="Current",
                    docstatus=0,
                    cutting_plan="PLAN-1",
                    plan_belongs_to_order=True,
                    plan_is_current=True,
                    pending_price_labels=(),
                    board_rate_present=True,
                    cutting_rate_present=True,
                    board_rate_usd=10,
                    cutting_cost_per_board_usd=1,
                    offcut_price_usd=0,
                    approved_amount_usd=25.5,
                )
                decision = decide_final_price_approval_actions(
                    has_approve_final_price=True,
                    has_view_costs=True,
                    has_edit_cost_settings=False,
                    price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
                    current_price_approval=None,
                    price_basis_token_value="1:abc",
                    eligibility_error=None,
                )
                self.assertTrue(decision.can_approve_final_price)

        with self.assertRaises(FinalPriceApprovalEligibilityError) as cancelled:
            evaluate_final_price_approval_eligibility(
                order_name="DCO-1",
                order_status="Cancelled",
                revision_state="Current",
                docstatus=0,
                cutting_plan="PLAN-1",
                plan_belongs_to_order=True,
                plan_is_current=True,
                pending_price_labels=(),
                board_rate_present=True,
                cutting_rate_present=True,
                board_rate_usd=10,
                cutting_cost_per_board_usd=1,
                offcut_price_usd=0,
                approved_amount_usd=25.5,
            )
        self.assertEqual(cancelled.exception.code, "order_cancelled")

    def test_approve_during_post_drawing_stage_preserves_operational_state(self) -> None:
        basis = _basis()
        token = price_basis_token(fingerprint_final_price_basis(basis))
        order = FakeOrder(
            name="DCO-PROD-1",
            status="At CNC",
            current_production_stage="PS-CNC-1",
            current_department="CNC",
            current_assignee="cnc.worker@example.com",
            approved_plan="PLAN-1",
            department_status="قيد العمل",
            production_path="Drawing",
        )
        gateway = FakeGateway(
            order=order,
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-PROD-1"),
            basis=basis,
        )
        before = {
            "status": order.status,
            "current_production_stage": order.current_production_stage,
            "current_department": order.current_department,
            "current_assignee": order.current_assignee,
            "approved_plan": order.approved_plan,
            "department_status": order.department_status,
            "production_path": order.production_path,
        }

        result = approve_order_final_price(
            gateway,
            order_name="DCO-PROD-1",
            expected_price_basis_token=token,
        )

        self.assertEqual(result.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(order.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(order.current_price_approval, result.current_price_approval)
        self.assertEqual(order.status, before["status"])
        self.assertEqual(order.current_production_stage, before["current_production_stage"])
        self.assertEqual(order.current_department, before["current_department"])
        self.assertEqual(order.current_assignee, before["current_assignee"])
        self.assertEqual(order.approved_plan, before["approved_plan"])
        self.assertEqual(order.department_status, before["department_status"])
        self.assertEqual(order.production_path, before["production_path"])
        # Only price-approval fields are written through the gateway.
        self.assertEqual(
            gateway.order_updates,
            [(PRICE_APPROVAL_STATUS_APPROVED, result.current_price_approval)],
        )

    def test_approve_endpoint_does_not_use_draft_edit_or_special_price_policies(self) -> None:
        source = APPROVAL_SERVICE.read_text(encoding="utf-8")
        for forbidden in (
            "assert_order_editable",
            "user_can_edit_order",
            "EDIT_ORDER",
            "EDITABLE_ORDER_STATUSES",
            "APPROVE_SPECIAL_PRICE",
            "EDIT_SPECIAL_PRICE",
            "require_stage_assignment_access",
            "require_stage_operational_access",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("production stage", source)
        self.assertIn("post-Drawing", source)
        self.assertIn("Mutates price-approval fields", source)
        self.assertIn("draft-only", source)

    def test_missing_capability_decision_and_service_auth_wiring(self) -> None:
        decision = decide_final_price_approval_actions(
            has_approve_final_price=False,
            has_view_costs=True,
            has_edit_cost_settings=True,
            price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            current_price_approval=None,
            price_basis_token_value="1:abc",
        )
        self.assertFalse(decision.can_approve_final_price)
        self.assertEqual(decision.reason_code, "missing_capability")
        source = APPROVAL_SERVICE.read_text(encoding="utf-8")
        self.assertIn("Capability.APPROVE_FINAL_PRICE", source)
        self.assertIn("Capability.VIEW_COSTS", source)
        self.assertIn("Capability.CANCEL_FINAL_PRICE_APPROVAL", source)
        self.assertNotIn("EDIT_ORDER", source)
        self.assertNotIn("APPROVE_SPECIAL_PRICE", source)
        # EDIT_COST_SETTINGS may appear only in post-cancel action decisions,
        # never as a required gate for approve/cancel RPCs.
        self.assertNotIn(
            "require_document_capability(\n        order,\n        Capability.EDIT_COST_SETTINGS",
            source,
        )
        approve_endpoint = source.split("def approve_order_final_price", 1)[1].split(
            "def cancel_order_final_price_approval", 1
        )[0]
        self.assertNotIn("EDIT_COST_SETTINGS", approve_endpoint)

    def test_approve_without_edit_capabilities_is_allowed_by_decision(self) -> None:
        decision = decide_final_price_approval_actions(
            has_approve_final_price=True,
            has_view_costs=True,
            has_edit_cost_settings=False,
            price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            current_price_approval=None,
            price_basis_token_value="1:abc",
        )
        self.assertTrue(decision.can_approve_final_price)
        self.assertFalse(decision.can_edit_cost_settings)

    def test_rejects_incomplete_stale_or_foreign_plan(self) -> None:
        with self.assertRaises(FinalPriceApprovalEligibilityError) as pending:
            evaluate_final_price_approval_eligibility(
                order_name="DCO-1",
                order_status="Draft",
                revision_state="Current",
                docstatus=0,
                cutting_plan="PLAN-1",
                plan_belongs_to_order=True,
                plan_is_current=True,
                pending_price_labels=("درفة خاصة رقم 1",),
                board_rate_present=True,
                cutting_rate_present=True,
                board_rate_usd=1,
                cutting_cost_per_board_usd=1,
                offcut_price_usd=0,
                approved_amount_usd=10,
            )
        self.assertEqual(pending.exception.code, "pending_prices")

        with self.assertRaises(FinalPriceApprovalEligibilityError) as stale:
            evaluate_final_price_approval_eligibility(
                order_name="DCO-1",
                order_status="Draft",
                revision_state="Current",
                docstatus=0,
                cutting_plan="PLAN-1",
                plan_belongs_to_order=True,
                plan_is_current=False,
                pending_price_labels=(),
                board_rate_present=True,
                cutting_rate_present=True,
                board_rate_usd=1,
                cutting_cost_per_board_usd=1,
                offcut_price_usd=0,
                approved_amount_usd=10,
            )
        self.assertEqual(stale.exception.code, "stale_plan")

        with self.assertRaises(FinalPriceApprovalEligibilityError) as foreign:
            evaluate_final_price_approval_eligibility(
                order_name="DCO-1",
                order_status="Draft",
                revision_state="Current",
                docstatus=0,
                cutting_plan="PLAN-OTHER",
                plan_belongs_to_order=False,
                plan_is_current=True,
                pending_price_labels=(),
                board_rate_present=True,
                cutting_rate_present=True,
                board_rate_usd=1,
                cutting_cost_per_board_usd=1,
                offcut_price_usd=0,
                approved_amount_usd=10,
            )
        self.assertEqual(foreign.exception.code, "foreign_plan")

    def test_rejects_missing_or_stale_basis_token_even_without_dco_modified(self) -> None:
        basis = _basis()
        digest = fingerprint_final_price_basis(basis)
        token = price_basis_token(digest)
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
            basis=basis,
        )
        with self.assertRaises(FinalPriceApprovalTokenError):
            approve_order_final_price(
                gateway,
                order_name="DCO-1",
                expected_price_basis_token=None,
            )

        changed = _basis()
        changed["plan"]["board_rate_usd"] = 11
        gateway.basis = changed
        with self.assertRaises(FinalPriceApprovalTokenError):
            approve_order_final_price(
                gateway,
                order_name="DCO-1",
                expected_price_basis_token=token,
            )
        version, digest_part = parse_price_basis_token(token)
        self.assertEqual(version, "1")
        self.assertTrue(digest_part)

    def test_repeat_approval_is_idempotent_for_same_basis(self) -> None:
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
        )
        second = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
        )
        self.assertEqual(len(gateway.approvals), 1)
        self.assertTrue(second.reused_existing)
        self.assertEqual(first.current_price_approval, second.current_price_approval)

    def test_storage_failure_leaves_order_unapproved(self) -> None:
        basis = _basis()
        token = price_basis_token(fingerprint_final_price_basis(basis))
        gateway = FakeGateway(
            order=FakeOrder(name="DCO-1"),
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
            basis=basis,
            fail_insert=True,
        )
        with self.assertRaises(RuntimeError):
            approve_order_final_price(
                gateway,
                order_name="DCO-1",
                expected_price_basis_token=token,
            )
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertIsNone(gateway.order.current_price_approval)
        self.assertEqual(gateway.order_updates, [])

    def test_cost_settings_editable_after_approval_when_capability_holds(self) -> None:
        self.assertTrue(
            can_edit_cost_settings_for_order(
                has_edit_cost_settings=True,
                price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            )
        )
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
        cost_source = COST_SERVICE.read_text(encoding="utf-8")
        plan_source = PLAN_COST_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("assert_cost_settings_unlocked_for_order", cost_source)
        self.assertNotIn("assert_cost_settings_unlocked_for_order", plan_source)
        self.assertIn("maybe_invalidate_final_price_approval", plan_source)
        self.assertEqual(
            COST_SETTINGS_FIELDS,
            ("board_rate_usd", "cutting_cost_per_board_usd", "offcut_price_usd"),
        )

    def test_snapshot_exposes_action_fields_and_endpoint_is_contracted(self) -> None:
        cost_source = COST_SERVICE.read_text(encoding="utf-8")
        for needle in (
            "price_basis_token",
            "can_approve_final_price",
            "can_edit_cost_settings",
            "can_cancel_final_price_approval",
            "final_price_cancellation_blocker",
            "approval_note",
            "price_approval_status",
            "final_price_approval_blocker",
        ):
            self.assertIn(needle, cost_source)
        contracts = ENDPOINT_CONTRACTS.read_text(encoding="utf-8")
        self.assertIn("final_price_approval_service", contracts)
        self.assertIn("approve_order_final_price", contracts)
        self.assertIn("cancel_order_final_price_approval", contracts)
        self.assertIn(Capability.APPROVE_FINAL_PRICE, {"approve_final_price"})

    def test_general_save_forgery_guard_still_blocks_status_and_link(self) -> None:
        with self.assertRaises(Exception):
            assert_order_price_approval_fields_unchanged(
                previous_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
                previous_link=None,
                incoming_status=PRICE_APPROVAL_STATUS_APPROVED,
                incoming_link="DCPA-1",
                allow_mutation=False,
            )

    def test_zero_is_valid_money_and_missing_input_is_distinct(self) -> None:
        evaluate_final_price_approval_eligibility(
            order_name="DCO-1",
            order_status="Draft",
            revision_state="Current",
            docstatus=0,
            cutting_plan="PLAN-1",
            plan_belongs_to_order=True,
            plan_is_current=True,
            pending_price_labels=(),
            board_rate_present=True,
            cutting_rate_present=True,
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            offcut_price_usd=0,
            approved_amount_usd=0,
        )
        with self.assertRaises(FinalPriceApprovalEligibilityError) as missing:
            evaluate_final_price_approval_eligibility(
                order_name="DCO-1",
                order_status="Draft",
                revision_state="Current",
                docstatus=0,
                cutting_plan="PLAN-1",
                plan_belongs_to_order=True,
                plan_is_current=True,
                pending_price_labels=(),
                board_rate_present=False,
                cutting_rate_present=True,
                board_rate_usd=0,
                cutting_cost_per_board_usd=1,
                offcut_price_usd=0,
                approved_amount_usd=10,
            )
        self.assertEqual(missing.exception.code, "board_rate_missing")

    def test_fingerprint_changes_when_basis_changes_but_total_stays_equal(self) -> None:
        first = _basis()
        second = _basis()
        # Keep approved amount identical while changing an input that still affects basis.
        second["plan"]["board_rate_usd"] = 12
        second["plan"]["mdf_cost_usd"] = 24
        self.assertEqual(first["approved_amount_usd"], second["approved_amount_usd"])
        self.assertNotEqual(
            fingerprint_final_price_basis(first),
            fingerprint_final_price_basis(second),
        )


if __name__ == "__main__":
    unittest.main()
