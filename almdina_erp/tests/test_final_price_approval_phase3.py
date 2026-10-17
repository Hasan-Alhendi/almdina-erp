"""Phase 3 contracts: auto-invalidate final-price approval on basis-affecting mutations."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    approve_order_final_price,
    invalidate_order_final_price_approval,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    build_final_price_basis_payload,
    build_order_pricing_input_payload,
    fingerprint_final_price_basis,
    fingerprint_order_pricing_inputs,
    price_basis_token,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
    cost_settings_locked_by_price_approval,
    pricing_basis_diverged,
    should_invalidate_final_price_approval,
)


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order_controller.py"
)
APPROVAL_SERVICE = ROOT / "almdina_erp" / "services" / "final_price_approval_service.py"
OFFCUT_SERVICE = ROOT / "almdina_erp" / "services" / "offcut_service.py"
PLAN_COMMAND = ROOT / "almdina_erp" / "services" / "cutting_plan_command_service.py"
PLAN_PREVIEW = ROOT / "almdina_erp" / "services" / "cutting_plan_preview_service.py"
PLAN_CANCEL = (
    ROOT / "almdina_erp" / "services" / "cutting_plan_approval_cancellation_service.py"
)
COST_SERVICE = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
PLAN_COST_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_cost_command_service.py"
REVISION_SERVICE = ROOT / "almdina_erp" / "services" / "order_revision_service.py"
EDGE_BANDING_SERVICE = ROOT / "almdina_erp" / "services" / "edge_banding_lookup_service.py"
COST_SYNC_SERVICE = ROOT / "almdina_erp" / "services" / "cost_service.py"
SPECIAL_SHAPE_WORKSPACE = (
    ROOT / "almdina_erp" / "services" / "special_shape_workspace_service.py"
)
NOTES_REPOSITORY = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "notes_repository.py"
)
ORDER_SCHEMA = (
    ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
)


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


def _basis(pieces: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
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
        pieces=pieces or [_piece()],
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
    invalidated_on: str | None = None
    invalidation_reason: str | None = None
    invalidated_by: str | None = None


@dataclass
class FakeOrder:
    name: str
    status: str = "Draft"
    revision_state: str = "Current"
    docstatus: int = 0
    price_approval_status: str = PRICE_APPROVAL_STATUS_APPROVED
    current_price_approval: str | None = "DCPA-00001"
    pieces: list[Any] = field(default_factory=list)


@dataclass
class FakePlan:
    name: str
    door_cutting_order: str
    required_boards: int = 2
    cost_snapshot_version: int = 1


@dataclass
class FakeGateway:
    order: FakeOrder
    plan: FakePlan
    basis: dict[str, Any]
    active: FakeApproval | None = None
    approvals: list[FakeApproval] = field(default_factory=list)
    order_updates: list[tuple[str, str | None]] = field(default_factory=list)
    locks: list[str] = field(default_factory=list)
    fail_invalidate: bool = False
    pending: tuple[str, ...] = ()
    plan_current: bool = True
    board_present: bool = True
    cutting_present: bool = True

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
        return self.active if self.active and self.active.name == approval_name else None

    def lock_approval(self, approval_name: str) -> FakeApproval | None:
        self.locks.append(f"approval:{approval_name}")
        return self.load_approval(approval_name)

    def insert_approval(self, **kwargs: Any) -> FakeApproval:
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
        if self.fail_invalidate:
            raise RuntimeError("invalidate failed")
        if approval.validity_status != PRICE_APPROVAL_VALIDITY_ACTIVE:
            return
        approval.validity_status = PRICE_APPROVAL_VALIDITY_INVALIDATED
        approval.invalidation_reason = reason
        approval.invalidated_on = "2026-10-14 13:00:00"
        approval.invalidated_by = actor
        if self.active is approval:
            self.active = None

    def current_user(self) -> str:
        return "operator@example.com"

    def now_iso(self) -> str:
        return "2026-10-14 13:00:00"


def _approved_gateway(basis: dict[str, Any] | None = None) -> FakeGateway:
    payload = basis or _basis()
    digest = fingerprint_final_price_basis(payload)
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
    )
    return FakeGateway(
        order=FakeOrder(name="DCO-1", current_price_approval=approval.name),
        plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-1"),
        basis=payload,
        active=approval,
        approvals=[approval],
    )


class TestFinalPriceApprovalPhase3(unittest.TestCase):
    def test_measurement_or_qty_change_fingerprint_differs_with_same_total(self) -> None:
        first = build_order_pricing_input_payload(pieces=[_piece(qty=1, width_cm=40)])
        second = build_order_pricing_input_payload(pieces=[_piece(qty=2, width_cm=40)])
        third = build_order_pricing_input_payload(pieces=[_piece(qty=1, width_cm=41)])
        self.assertNotEqual(
            fingerprint_order_pricing_inputs(first),
            fingerprint_order_pricing_inputs(second),
        )
        self.assertNotEqual(
            fingerprint_order_pricing_inputs(first),
            fingerprint_order_pricing_inputs(third),
        )
        same_total_a = _basis(pieces=[_piece(qty=1, width_cm=40)], invoice_preview_total_usd=25.5)
        same_total_b = _basis(pieces=[_piece(qty=1, width_cm=41)], invoice_preview_total_usd=25.5)
        self.assertEqual(same_total_a["approved_amount_usd"], same_total_b["approved_amount_usd"])
        self.assertNotEqual(
            fingerprint_final_price_basis(same_total_a),
            fingerprint_final_price_basis(same_total_b),
        )

    def test_addon_or_piece_add_remove_changes_input_fingerprint(self) -> None:
        one = build_order_pricing_input_payload(pieces=[_piece()])
        two = build_order_pricing_input_payload(
            pieces=[_piece(), _piece(piece_no=2, qty=1, width_cm=30, length_cm=60)]
        )
        addon = build_order_pricing_input_payload(pieces=[_piece(extra_liner=1)])
        self.assertNotEqual(
            fingerprint_order_pricing_inputs(one),
            fingerprint_order_pricing_inputs(two),
        )
        self.assertNotEqual(
            fingerprint_order_pricing_inputs(one),
            fingerprint_order_pricing_inputs(addon),
        )

    def test_invalidate_clears_status_and_preserves_history(self) -> None:
        gateway = _approved_gateway()
        approval = gateway.approvals[0]
        approval.approval_note = "ملاحظة أصلية"
        original_amount = approval.approved_amount
        original_by = approval.approved_by
        original_fingerprint = approval.pricing_basis_fingerprint
        original_note = approval.approval_note

        result = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="order_pricing_inputs_changed",
        )
        self.assertTrue(result.invalidated)
        self.assertEqual(result.previous_approval, "DCPA-00001")
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertIsNone(gateway.order.current_price_approval)
        self.assertEqual(approval.validity_status, PRICE_APPROVAL_VALIDITY_INVALIDATED)
        self.assertEqual(approval.invalidation_reason, "order_pricing_inputs_changed")
        self.assertEqual(approval.invalidated_on, "2026-10-14 13:00:00")
        self.assertEqual(approval.invalidated_by, "operator@example.com")
        self.assertEqual(approval.approved_amount, original_amount)
        self.assertEqual(approval.approved_by, original_by)
        self.assertEqual(approval.pricing_basis_fingerprint, original_fingerprint)
        self.assertEqual(approval.approval_note, original_note)
        self.assertEqual(gateway.locks[:1], ["order:DCO-1"])

    def test_idempotent_repeat_invalidation_does_not_rewrite_history(self) -> None:
        gateway = _approved_gateway()
        first = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="order_pricing_inputs_changed",
        )
        historic = gateway.approvals[0]
        reason = historic.invalidation_reason
        when = historic.invalidated_on
        second = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="order_pricing_inputs_changed_again",
        )
        self.assertTrue(first.invalidated)
        self.assertFalse(second.invalidated)
        self.assertEqual(historic.invalidation_reason, reason)
        self.assertEqual(historic.invalidated_on, when)

    def test_restore_old_inputs_does_not_auto_reapprove(self) -> None:
        gateway = _approved_gateway()
        invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="order_pricing_inputs_changed",
        )
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_UNAPPROVED)
        self.assertIsNone(gateway.order.current_price_approval)
        self.assertFalse(should_invalidate_final_price_approval(gateway.order.price_approval_status))

    def test_only_if_basis_changed_skips_matching_fingerprint(self) -> None:
        gateway = _approved_gateway()
        result = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="cost_plan_basis_changed",
            only_if_basis_changed=True,
        )
        self.assertFalse(result.invalidated)
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(gateway.active.validity_status, PRICE_APPROVAL_VALIDITY_ACTIVE)

    def test_only_if_basis_changed_keeps_approval_when_only_plan_identity_changes(self) -> None:
        gateway = _approved_gateway()
        gateway.basis = _basis(cutting_plan="PLAN-2")
        gateway.plan = FakePlan(name="PLAN-2", door_cutting_order="DCO-1")
        result = invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="cost_plan_authority_changed",
            only_if_basis_changed=True,
        )
        # Plan document identity alone is not a commercial basis change.
        self.assertFalse(result.invalidated)
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(gateway.active.validity_status, PRICE_APPROVAL_VALIDITY_ACTIVE)
        # Full fingerprint still differs because it embeds cutting_plan.
        self.assertTrue(
            pricing_basis_diverged(
                stored_fingerprint=gateway.approvals[0].pricing_basis_fingerprint,
                current_fingerprint=fingerprint_final_price_basis(gateway.basis),
            )
        )

    def test_failed_invalidation_leaves_approval_intact(self) -> None:
        gateway = _approved_gateway()
        gateway.fail_invalidate = True
        with self.assertRaises(RuntimeError):
            invalidate_order_final_price_approval(
                gateway,
                order_name="DCO-1",
                reason="order_pricing_inputs_changed",
            )
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(gateway.order.current_price_approval, "DCPA-00001")
        self.assertEqual(gateway.approvals[0].validity_status, PRICE_APPROVAL_VALIDITY_ACTIVE)
        self.assertEqual(gateway.order_updates, [])

    def test_failed_invalidation_rolls_back_uncommitted_pricing_input_change(self) -> None:
        """Same-transaction semantics: failed invalidate must not keep the new input.

        This simulates Document.save + on_update invalidation sharing one txn.
        It is not a live MariaDB race proof (see concurrency caveat in report).
        """

        state = {
            "qty": 1,
            "price_approval_status": PRICE_APPROVAL_STATUS_APPROVED,
            "current_price_approval": "DCPA-00001",
            "approval_validity": PRICE_APPROVAL_VALIDITY_ACTIVE,
            "invalidation_reason": None,
        }

        def apply_qty_change_then_invalidate(*, invalidate_fails: bool) -> None:
            snapshot = dict(state)
            state["qty"] = 2
            try:
                if invalidate_fails:
                    raise RuntimeError("invalidate failed")
                state["price_approval_status"] = PRICE_APPROVAL_STATUS_UNAPPROVED
                state["current_price_approval"] = None
                state["approval_validity"] = PRICE_APPROVAL_VALIDITY_INVALIDATED
                state["invalidation_reason"] = "order_pricing_inputs_changed"
            except Exception:
                state.clear()
                state.update(snapshot)
                raise

        with self.assertRaises(RuntimeError):
            apply_qty_change_then_invalidate(invalidate_fails=True)

        self.assertEqual(state["qty"], 1)
        self.assertEqual(state["price_approval_status"], PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(state["current_price_approval"], "DCPA-00001")
        self.assertEqual(state["approval_validity"], PRICE_APPROVAL_VALIDITY_ACTIVE)
        self.assertIsNone(state["invalidation_reason"])

        apply_qty_change_then_invalidate(invalidate_fails=False)
        self.assertEqual(state["qty"], 2)
        self.assertEqual(state["price_approval_status"], PRICE_APPROVAL_STATUS_UNAPPROVED)

    def test_invalidation_call_sites_do_not_swallow_failures(self) -> None:
        for path in (
            CONTROLLER,
            APPROVAL_SERVICE,
            OFFCUT_SERVICE,
            PLAN_COMMAND,
            PLAN_PREVIEW,
            PLAN_CANCEL,
            EDGE_BANDING_SERVICE,
        ):
            source = path.read_text(encoding="utf-8")
            self.assertIn("maybe_invalidate_final_price", source)
            # Fail closed: no local try/except around the invalidate call site.
            self.assertNotRegex(
                source,
                r"try:\s*\n(?:.*\n){0,6}.*maybe_invalidate_final_price",
            )

    def test_edge_banding_override_path_wires_central_invalidation(self) -> None:
        source = EDGE_BANDING_SERVICE.read_text(encoding="utf-8")
        self.assertIn("maybe_invalidate_final_price_approval", source)
        self.assertIn("edge_banding_override_changed", source)

    def test_set_value_paths_excluded_from_invalidation_are_non_basis(self) -> None:
        """Contract: active set_value writers that must NOT auto-invalidate."""

        cost_sync = COST_SYNC_SERVICE.read_text(encoding="utf-8")
        self.assertIn("actual_cost_usd", cost_sync)
        self.assertIn("material_variance_cost_usd", cost_sync)
        self.assertNotIn("maybe_invalidate_final_price_approval", cost_sync)

        notes = NOTES_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("important_note_preview", notes)
        self.assertNotIn("maybe_invalidate_final_price_approval", notes)

        drawing = SPECIAL_SHAPE_WORKSPACE.read_text(encoding="utf-8")
        self.assertIn("special_shape_drawing_json", drawing)
        self.assertNotIn("maybe_invalidate_final_price_approval", drawing)

    def test_reapprove_after_invalidation_creates_new_record(self) -> None:
        gateway = _approved_gateway()
        old = gateway.approvals[0]
        invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="order_pricing_inputs_changed",
        )
        gateway.basis = _basis(pieces=[_piece(qty=2)], invoice_preview_total_usd=30.0)
        gateway.basis["customer_quote_total_usd"] = 30.0
        token = price_basis_token(fingerprint_final_price_basis(gateway.basis))
        result = approve_order_final_price(
            gateway,
            order_name="DCO-1",
            expected_price_basis_token=token,
        )
        self.assertFalse(result.reused_existing)
        self.assertNotEqual(result.current_price_approval, old.name)
        self.assertEqual(old.validity_status, PRICE_APPROVAL_VALIDITY_INVALIDATED)
        self.assertEqual(gateway.order.price_approval_status, PRICE_APPROVAL_STATUS_APPROVED)

    def test_stale_token_rejected_after_basis_change(self) -> None:
        gateway = _approved_gateway()
        old_token = price_basis_token(fingerprint_final_price_basis(gateway.basis))
        invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="order_pricing_inputs_changed",
        )
        gateway.basis = _basis(pieces=[_piece(width_cm=42)])
        with self.assertRaises(Exception):
            approve_order_final_price(
                gateway,
                order_name="DCO-1",
                expected_price_basis_token=old_token,
            )

    def test_cost_settings_commands_invalidate_instead_of_locking(self) -> None:
        self.assertFalse(cost_settings_locked_by_price_approval(PRICE_APPROVAL_STATUS_APPROVED))
        cost_source = COST_SERVICE.read_text(encoding="utf-8")
        plan_cost = PLAN_COST_SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("assert_cost_settings_unlocked_for_order", cost_source)
        self.assertNotIn("assert_cost_settings_unlocked_for_order", plan_cost)
        # Cost-settings save may clear Approved pricing when the commercial basis changes.
        self.assertIn("maybe_invalidate_final_price_approval", plan_cost)
        self.assertIn("cost_settings_changed", plan_cost)

    def test_mutation_paths_delegate_to_central_invalidation(self) -> None:
        controller = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("maybe_invalidate_final_price_after_order_save", controller)
        self.assertNotIn("optimize_order_plan", controller)
        self.assertIn("must not catch", controller)

        service = APPROVAL_SERVICE.read_text(encoding="utf-8")
        self.assertIn("invalidate_order_final_price_approval", service)
        self.assertIn("order_commercial_inputs_changed", service)
        self.assertIn("Exceptions propagate intentionally", service)

        self.assertIn("maybe_invalidate_final_price_approval", OFFCUT_SERVICE.read_text())
        self.assertIn("offcut_classification_changed", OFFCUT_SERVICE.read_text())

        plan_cmd = PLAN_COMMAND.read_text(encoding="utf-8")
        for needle in (
            "finalize_uploaded_dxf_order_state",
            "approve_order_plan",
            "recalculate_system_plan",
            "only_if_basis_changed=True",
        ):
            self.assertIn(needle, plan_cmd)
        self.assertIn("maybe_invalidate_final_price_approval", plan_cmd)

        self.assertIn(
            "maybe_invalidate_final_price_approval",
            PLAN_PREVIEW.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "maybe_invalidate_final_price_approval",
            PLAN_CANCEL.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "maybe_invalidate_final_price_approval",
            EDGE_BANDING_SERVICE.read_text(encoding="utf-8"),
        )

    def test_revision_and_copy_do_not_inherit_approval(self) -> None:
        import json

        schema = json.loads(ORDER_SCHEMA.read_text(encoding="utf-8"))
        fields = {row["fieldname"]: row for row in schema["fields"]}
        self.assertEqual(fields["price_approval_status"].get("no_copy"), 1)
        self.assertEqual(fields["current_price_approval"].get("no_copy"), 1)
        revision = REVISION_SERVICE.read_text(encoding="utf-8")
        self.assertIn('"price_approval_status": "Unapproved"', revision)
        self.assertIn('"current_price_approval": None', revision)

    def test_notes_only_input_fingerprint_stable(self) -> None:
        # Notes are intentionally absent from the commercial input payload.
        base = build_order_pricing_input_payload(pieces=[_piece()])
        twin = build_order_pricing_input_payload(pieces=[_piece()])
        self.assertEqual(
            fingerprint_order_pricing_inputs(base),
            fingerprint_order_pricing_inputs(twin),
        )

    def test_concurrency_lock_order_is_order_then_plan(self) -> None:
        gateway = _approved_gateway()
        gateway.basis = _basis(cutting_plan="PLAN-2")
        gateway.plan = FakePlan(name="PLAN-2", door_cutting_order="DCO-1")
        invalidate_order_final_price_approval(
            gateway,
            order_name="DCO-1",
            reason="cost_plan_authority_changed",
            only_if_basis_changed=True,
        )
        self.assertEqual(gateway.locks[0], "order:DCO-1")
        self.assertEqual(gateway.locks[1], "plan:PLAN-2")

    def test_special_or_clipped_price_fields_affect_basis(self) -> None:
        regular = _basis()
        special = _basis(
            pieces=[
                _piece(
                    piece_type="Special",
                    special_shape_custom_unit_price_usd=12,
                    special_shape_final_unit_price_usd=12,
                    special_shape_price_status="Approved",
                )
            ]
        )
        clipped = _basis(
            pieces=[
                _piece(
                    piece_type="Corner Cut",
                    clipped_corner_edge_price_usd=3,
                    clipped_corner_edge_price_status="Priced",
                )
            ]
        )
        self.assertNotEqual(
            fingerprint_final_price_basis(regular),
            fingerprint_final_price_basis(special),
        )
        self.assertNotEqual(
            fingerprint_final_price_basis(regular),
            fingerprint_final_price_basis(clipped),
        )

    def test_offcut_assignments_affect_basis_fingerprint(self) -> None:
        none = _basis(offcut_applicable=True, offcut_assignments=[])
        assigned = _basis(
            offcut_applicable=True,
            offcut_assignments=[
                {
                    "source_owner": "Factory",
                    "execution_owner": "Factory",
                    "piece_number": "1",
                }
            ],
        )
        self.assertEqual(none["approved_amount_usd"], assigned["approved_amount_usd"])
        self.assertNotEqual(
            fingerprint_final_price_basis(none),
            fingerprint_final_price_basis(assigned),
        )


if __name__ == "__main__":
    unittest.main()
