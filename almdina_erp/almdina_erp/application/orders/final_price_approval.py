"""Application use cases for commercial final-price approval and manual cancel.

Server-owned: capabilities are checked by the service before these use cases run.
The gateway gathers locked facts, persists the audit row, and updates order fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    fingerprint_final_price_basis,
    parse_price_basis_token,
    price_basis_token,
    pricing_basis_commercially_equivalent,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    MANUAL_PRICE_APPROVAL_CANCELLED,
    PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
    ApprovalNoteError,
    FinalPriceApprovalEligibilityError,
    FinalPriceCancellationError,
    active_approval_matches_basis,
    can_edit_cost_settings_for_order,
    evaluate_final_price_approval_eligibility,
    evaluate_final_price_cancellation_document_rules,
    normalize_approval_note,
    normalize_price_approval_status,
    should_invalidate_final_price_approval,
)


class FinalPriceApprovalTokenError(ValueError):
    """Client basis token is missing or no longer matches the locked server basis."""


@dataclass(frozen=True, slots=True)
class FinalPriceApprovalDecision:
    can_approve_final_price: bool
    reason_code: str | None
    reason_message: str | None
    can_edit_cost_settings: bool
    can_cancel_final_price_approval: bool
    cancel_reason_code: str | None
    cancel_reason_message: str | None
    price_approval_status: str
    price_basis_token: str | None
    current_price_approval: str | None


@dataclass(frozen=True, slots=True)
class FinalPriceApprovalResult:
    order_name: str
    price_approval_status: str
    current_price_approval: str
    approved_amount_usd: float
    currency: str
    cutting_plan: str
    pricing_basis_fingerprint: str
    fingerprint_formula_version: str
    approved_by: str
    approved_on: str
    approval_note: str | None
    reused_existing: bool
    price_basis_token: str


@dataclass(frozen=True, slots=True)
class FinalPriceInvalidationResult:
    order_name: str
    invalidated: bool
    previous_approval: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class FinalPriceCancellationResult:
    order_name: str
    price_approval_status: str
    current_price_approval: str | None
    cancelled_approval: str | None
    cancelled_now: bool
    reason: str | None
    can_approve_final_price: bool
    can_cancel_final_price_approval: bool
    cancel_reason_code: str | None
    cancel_reason_message: str | None


class FinalPriceApprovalGateway(Protocol):
    def lock_order(self, order_name: str) -> Any: ...

    def lock_cost_plan(self, plan_name: str) -> Any: ...

    def lock_approval(self, approval_name: str) -> Any: ...

    def resolve_cost_plan(self, order: Any) -> Any | None: ...

    def plan_belongs_to_order(self, plan: Any, order_name: str) -> bool: ...

    def plan_is_current(self, order: Any, plan: Any) -> bool: ...

    def build_basis_payload(self, order: Any, plan: Any) -> dict[str, Any]: ...

    def pending_price_labels(self, order: Any, plan: Any) -> tuple[str, ...]: ...

    def cost_input_presence(self, plan: Any) -> tuple[bool, bool]: ...

    def find_active_approval(self, order_name: str) -> Any | None: ...

    def load_approval(self, approval_name: str) -> Any | None: ...

    def insert_approval(
        self,
        *,
        order_name: str,
        cutting_plan: str,
        approved_amount: float,
        currency: str,
        fingerprint: str,
        formula_version: str,
        approval_note: str | None = None,
    ) -> Any: ...

    def update_order_price_approval(
        self,
        order_name: str,
        *,
        status: str,
        approval_name: str | None,
    ) -> None: ...

    def invalidate_approval(
        self,
        approval: Any,
        *,
        reason: str,
        actor: str | None = None,
    ) -> None: ...

    def current_user(self) -> str: ...

    def now_iso(self) -> str: ...


def decide_final_price_approval_actions(
    *,
    has_approve_final_price: bool,
    has_view_costs: bool,
    has_edit_cost_settings: bool,
    price_approval_status: Any,
    current_price_approval: Any,
    price_basis_token_value: str | None,
    eligibility_error: FinalPriceApprovalEligibilityError | None = None,
    has_cancel_final_price_approval: bool = False,
    order_status: Any = None,
    revision_state: Any = None,
    docstatus: int | None = None,
) -> FinalPriceApprovalDecision:
    """Central read-model decision for the Cost workspace approve/cancel actions."""

    status = normalize_price_approval_status(price_approval_status)
    link = str(current_price_approval or "").strip() or None
    can_edit = can_edit_cost_settings_for_order(
        has_edit_cost_settings=has_edit_cost_settings,
        price_approval_status=status,
        has_view_costs=has_view_costs,
        order_status=order_status,
        revision_state=revision_state,
        docstatus=docstatus,
    )

    cancel_ok = False
    cancel_code: str | None = None
    cancel_message: str | None = None
    if not has_cancel_final_price_approval or not has_view_costs:
        cancel_code = "missing_capability"
        cancel_message = "Final-price cancellation capability is required."
    else:
        try:
            evaluate_final_price_cancellation_document_rules(
                order_name="decision",
                order_status=order_status,
                revision_state=revision_state,
                docstatus=docstatus if docstatus is not None else 0,
            )
        except FinalPriceCancellationError as error:
            cancel_code = error.code
            cancel_message = str(error)
        else:
            if status != PRICE_APPROVAL_STATUS_APPROVED or not link:
                cancel_code = "not_approved"
                cancel_message = "There is no active final-price approval to cancel."
            else:
                cancel_ok = True

    if not has_approve_final_price or not has_view_costs:
        return FinalPriceApprovalDecision(
            can_approve_final_price=False,
            reason_code="missing_capability",
            reason_message="Final-price approval capability is required.",
            can_edit_cost_settings=can_edit,
            can_cancel_final_price_approval=cancel_ok,
            cancel_reason_code=cancel_code,
            cancel_reason_message=cancel_message,
            price_approval_status=status,
            price_basis_token=price_basis_token_value,
            current_price_approval=link,
        )
    if eligibility_error is not None:
        return FinalPriceApprovalDecision(
            can_approve_final_price=False,
            reason_code=eligibility_error.code,
            reason_message=str(eligibility_error),
            can_edit_cost_settings=can_edit,
            can_cancel_final_price_approval=cancel_ok,
            cancel_reason_code=cancel_code,
            cancel_reason_message=cancel_message,
            price_approval_status=status,
            price_basis_token=price_basis_token_value,
            current_price_approval=link,
        )
    return FinalPriceApprovalDecision(
        can_approve_final_price=True,
        reason_code=None,
        reason_message=None,
        can_edit_cost_settings=can_edit,
        can_cancel_final_price_approval=cancel_ok,
        cancel_reason_code=cancel_code,
        cancel_reason_message=cancel_message,
        price_approval_status=status,
        price_basis_token=price_basis_token_value,
        current_price_approval=link,
    )


def _approval_note_value(approval: Any) -> str | None:
    raw = getattr(approval, "approval_note", None)
    if raw is None and isinstance(approval, dict):
        raw = approval.get("approval_note")
    text = str(raw or "").strip()
    return text or None


def _result_from_approval(
    *,
    order_name: str,
    approval: Any,
    reused_existing: bool,
) -> FinalPriceApprovalResult:
    fingerprint = str(getattr(approval, "pricing_basis_fingerprint", None) or "")
    version = str(
        getattr(approval, "fingerprint_formula_version", None)
        or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION
    )
    return FinalPriceApprovalResult(
        order_name=order_name,
        price_approval_status=PRICE_APPROVAL_STATUS_APPROVED,
        current_price_approval=str(getattr(approval, "name", None) or ""),
        approved_amount_usd=float(getattr(approval, "approved_amount", 0) or 0),
        currency=str(getattr(approval, "currency", None) or "USD"),
        cutting_plan=str(getattr(approval, "cutting_plan", None) or ""),
        pricing_basis_fingerprint=fingerprint,
        fingerprint_formula_version=version,
        approved_by=str(getattr(approval, "approved_by", None) or ""),
        approved_on=str(getattr(approval, "approved_on", None) or ""),
        approval_note=_approval_note_value(approval),
        reused_existing=reused_existing,
        price_basis_token=price_basis_token(fingerprint, formula_version=version),
    )


def approve_order_final_price(
    gateway: FinalPriceApprovalGateway,
    *,
    order_name: str,
    expected_price_basis_token: str | None,
    approval_note: Any = None,
) -> FinalPriceApprovalResult:
    """Approve the current commercial total under optimistic basis-token concurrency.

    Writes only price-approval status/link and the approval audit row. Callers
    must not gate this on Draft or draft-restricted edit policies; production
    stage fields on the order are left untouched.

    ``approval_note`` is optional. Reusing an Active matching record returns that
    row's original note and ignores a different note on the repeat request.
    """

    name = str(order_name or "").strip()
    if not name:
        raise FinalPriceApprovalEligibilityError(
            "order_missing",
            "The cutting order must be saved before its final price can be approved.",
        )

    try:
        stored_note = normalize_approval_note(approval_note)
    except ApprovalNoteError:
        raise

    order = gateway.lock_order(name)
    plan = gateway.resolve_cost_plan(order)
    plan_name = str(getattr(plan, "name", None) or "").strip() if plan is not None else ""
    if plan_name:
        plan = gateway.lock_cost_plan(plan_name)

    expected_version, expected_digest = parse_price_basis_token(expected_price_basis_token)
    if not expected_version or not expected_digest:
        raise FinalPriceApprovalTokenError(
            "Refresh the cost page and review the current price before approving."
        )

    pending = gateway.pending_price_labels(order, plan) if plan is not None else ()
    board_present, cutting_present = (
        gateway.cost_input_presence(plan) if plan is not None else (False, False)
    )
    basis = gateway.build_basis_payload(order, plan) if plan is not None else {}
    fingerprint = fingerprint_final_price_basis(basis) if basis else ""
    token = price_basis_token(
        fingerprint,
        formula_version=str(basis.get("formula_version") or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION),
    )
    actual_version, actual_digest = parse_price_basis_token(token)

    evaluate_final_price_approval_eligibility(
        order_name=name,
        order_status=str(getattr(order, "status", None) or ""),
        revision_state=str(getattr(order, "revision_state", None) or "Current"),
        docstatus=int(getattr(order, "docstatus", 0) or 0),
        cutting_plan=plan_name,
        plan_belongs_to_order=bool(plan is not None and gateway.plan_belongs_to_order(plan, name)),
        plan_is_current=bool(plan is not None and gateway.plan_is_current(order, plan)),
        pending_price_labels=pending,
        board_rate_present=board_present,
        cutting_rate_present=cutting_present,
        board_rate_usd=float((basis.get("plan") or {}).get("board_rate_usd") or 0),
        cutting_cost_per_board_usd=float(
            (basis.get("plan") or {}).get("cutting_cost_per_board_usd") or 0
        ),
        offcut_price_usd=float((basis.get("plan") or {}).get("offcut_price_usd") or 0),
        approved_amount_usd=float(basis.get("approved_amount_usd") or 0),
    )

    if expected_version != actual_version or expected_digest != actual_digest:
        raise FinalPriceApprovalTokenError(
            "The price basis changed since it was last loaded. Refresh and review the price before approving."
        )

    existing = gateway.find_active_approval(name)
    if existing is not None:
        if active_approval_matches_basis(
            validity_status=getattr(existing, "validity_status", None),
            stored_fingerprint=getattr(existing, "pricing_basis_fingerprint", None),
            current_fingerprint=fingerprint,
        ):
            if str(getattr(order, "current_price_approval", None) or "") != str(existing.name):
                gateway.update_order_price_approval(
                    name,
                    status=PRICE_APPROVAL_STATUS_APPROVED,
                    approval_name=str(existing.name),
                )
            return _result_from_approval(
                order_name=name,
                approval=existing,
                reused_existing=True,
            )
        # Stale Active under lock: clear it, then record approval for the current basis.
        gateway.invalidate_approval(
            existing,
            reason="superseded_by_new_approval",
            actor=gateway.current_user(),
        )
        gateway.update_order_price_approval(
            name,
            status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            approval_name=None,
        )

    approval = gateway.insert_approval(
        order_name=name,
        cutting_plan=plan_name,
        approved_amount=float(basis.get("approved_amount_usd") or 0),
        currency=str(basis.get("currency") or "USD"),
        fingerprint=fingerprint,
        formula_version=str(
            basis.get("formula_version") or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION
        ),
        approval_note=stored_note,
    )
    gateway.update_order_price_approval(
        name,
        status=PRICE_APPROVAL_STATUS_APPROVED,
        approval_name=str(approval.name),
    )
    return _result_from_approval(
        order_name=name,
        approval=approval,
        reused_existing=False,
    )


def cancel_order_final_price_approval(
    gateway: FinalPriceApprovalGateway,
    *,
    order_name: str,
    expected_current_price_approval: str | None,
) -> FinalPriceCancellationResult:
    """Manually clear the Active final-price approval the client reviewed.

    Requires an exact ``expected_current_price_approval`` match so a newer Active
    row created after the page loaded is never cancelled by accident. Does not
    require a fresh plan, complete pricing, or approve/edit capabilities.
    """

    name = str(order_name or "").strip()
    expected = str(expected_current_price_approval or "").strip()
    if not expected:
        raise FinalPriceCancellationError(
            "expected_approval_missing",
            "Refresh the cost page and cancel the current price approval again.",
        )

    order = gateway.lock_order(name)
    evaluate_final_price_cancellation_document_rules(
        order_name=name,
        order_status=str(getattr(order, "status", None) or ""),
        revision_state=str(getattr(order, "revision_state", None) or "Current"),
        docstatus=int(getattr(order, "docstatus", 0) or 0),
    )

    expected_row = gateway.lock_approval(expected)
    if expected_row is None:
        raise FinalPriceCancellationError(
            "approval_missing",
            "The selected price approval was not found. Refresh and try again.",
        )
    if str(getattr(expected_row, "door_cutting_order", None) or "") != name:
        raise FinalPriceCancellationError(
            "foreign_approval",
            "The selected price approval belongs to another order.",
        )

    active = gateway.find_active_approval(name)
    active_name = str(getattr(active, "name", None) or "").strip() if active is not None else ""

    if active is not None and active_name != expected:
        raise FinalPriceCancellationError(
            "approval_changed",
            "The price approval changed since this page was loaded. Refresh and review before cancelling.",
        )

    if active is None:
        # Idempotent replay for the same cancelled row when no newer Active exists.
        validity = str(getattr(expected_row, "validity_status", None) or "").strip()
        if validity != PRICE_APPROVAL_VALIDITY_INVALIDATED:
            raise FinalPriceCancellationError(
                "not_approved",
                "There is no active final-price approval to cancel.",
            )
        if normalize_price_approval_status(
            getattr(order, "price_approval_status", None)
        ) == PRICE_APPROVAL_STATUS_APPROVED or str(
            getattr(order, "current_price_approval", None) or ""
        ).strip():
            gateway.update_order_price_approval(
                name,
                status=PRICE_APPROVAL_STATUS_UNAPPROVED,
                approval_name=None,
            )
        decision = decide_final_price_approval_actions(
            has_approve_final_price=False,
            has_view_costs=True,
            has_edit_cost_settings=False,
            has_cancel_final_price_approval=True,
            price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            current_price_approval=None,
            price_basis_token_value=None,
            order_status=getattr(order, "status", None),
            revision_state=getattr(order, "revision_state", None),
            docstatus=int(getattr(order, "docstatus", 0) or 0),
        )
        return FinalPriceCancellationResult(
            order_name=name,
            price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            current_price_approval=None,
            cancelled_approval=expected,
            cancelled_now=False,
            reason=str(getattr(expected_row, "invalidation_reason", None) or "") or None,
            can_approve_final_price=decision.can_approve_final_price,
            can_cancel_final_price_approval=decision.can_cancel_final_price_approval,
            cancel_reason_code=decision.cancel_reason_code,
            cancel_reason_message=decision.cancel_reason_message,
        )

    gateway.invalidate_approval(
        active,
        reason=MANUAL_PRICE_APPROVAL_CANCELLED,
        actor=gateway.current_user(),
    )
    gateway.update_order_price_approval(
        name,
        status=PRICE_APPROVAL_STATUS_UNAPPROVED,
        approval_name=None,
    )
    order.price_approval_status = PRICE_APPROVAL_STATUS_UNAPPROVED
    order.current_price_approval = None

    decision = decide_final_price_approval_actions(
        has_approve_final_price=False,
        has_view_costs=True,
        has_edit_cost_settings=False,
        has_cancel_final_price_approval=True,
        price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
        current_price_approval=None,
        price_basis_token_value=None,
        order_status=getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
        docstatus=int(getattr(order, "docstatus", 0) or 0),
    )
    return FinalPriceCancellationResult(
        order_name=name,
        price_approval_status=PRICE_APPROVAL_STATUS_UNAPPROVED,
        current_price_approval=None,
        cancelled_approval=expected,
        cancelled_now=True,
        reason=MANUAL_PRICE_APPROVAL_CANCELLED,
        can_approve_final_price=decision.can_approve_final_price,
        can_cancel_final_price_approval=decision.can_cancel_final_price_approval,
        cancel_reason_code=decision.cancel_reason_code,
        cancel_reason_message=decision.cancel_reason_message,
    )


def invalidate_order_final_price_approval(
    gateway: FinalPriceApprovalGateway,
    *,
    order_name: str,
    reason: str,
    only_if_basis_changed: bool = False,
) -> FinalPriceInvalidationResult:
    """Clear Approved final-price state when a pricing-basis mutation succeeds.

    Idempotent: Unapproved orders with no Active approval are a no-op and do not
    rewrite a prior invalidation reason/timestamp. Optional basis comparison
    skips invalidation when the live commercial fingerprint still matches the
    Active approval (e.g. production-approve of the same cost-authority plan).
    """

    name = str(order_name or "").strip()
    reason_code = str(reason or "").strip() or "pricing_basis_changed"
    if not name:
        return FinalPriceInvalidationResult(
            order_name="",
            invalidated=False,
            previous_approval=None,
            reason=None,
        )

    order = gateway.lock_order(name)
    active = gateway.find_active_approval(name)
    status = getattr(order, "price_approval_status", None)
    needs_status_clear = should_invalidate_final_price_approval(status)
    if not needs_status_clear and active is None:
        return FinalPriceInvalidationResult(
            order_name=name,
            invalidated=False,
            previous_approval=None,
            reason=None,
        )

    plan = gateway.resolve_cost_plan(order)
    plan_name = str(getattr(plan, "name", None) or "").strip() if plan is not None else ""
    if plan_name:
        plan = gateway.lock_cost_plan(plan_name)

    if only_if_basis_changed and active is not None:
        basis = gateway.build_basis_payload(order, plan) if plan is not None else {}
        # Ignore plan document identity so an algorithm change that keeps the same
        # board count and commercial totals does not clear Approved pricing.
        if pricing_basis_commercially_equivalent(
            stored_fingerprint=getattr(active, "pricing_basis_fingerprint", None),
            stored_cutting_plan=getattr(active, "cutting_plan", None),
            current_basis=basis,
        ):
            return FinalPriceInvalidationResult(
                order_name=name,
                invalidated=False,
                previous_approval=str(getattr(active, "name", None) or "") or None,
                reason=None,
            )

    previous_name = str(getattr(active, "name", None) or "").strip() or None
    if active is not None:
        gateway.invalidate_approval(
            active,
            reason=reason_code,
            actor=gateway.current_user(),
        )
    if needs_status_clear or previous_name:
        gateway.update_order_price_approval(
            name,
            status=PRICE_APPROVAL_STATUS_UNAPPROVED,
            approval_name=None,
        )
        order.price_approval_status = PRICE_APPROVAL_STATUS_UNAPPROVED
        order.current_price_approval = None
    return FinalPriceInvalidationResult(
        order_name=name,
        invalidated=True,
        previous_approval=previous_name,
        reason=reason_code,
    )


__all__ = [
    "FinalPriceApprovalDecision",
    "FinalPriceApprovalGateway",
    "FinalPriceApprovalResult",
    "FinalPriceApprovalTokenError",
    "FinalPriceCancellationResult",
    "FinalPriceInvalidationResult",
    "approve_order_final_price",
    "cancel_order_final_price_approval",
    "decide_final_price_approval_actions",
    "invalidate_order_final_price_approval",
]
