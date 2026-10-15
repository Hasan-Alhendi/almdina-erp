"""Application use case for approving the commercial final price of one order.

Server-owned: capabilities are checked by the service before this use case runs.
The gateway gathers locked facts, persists the audit row, and updates order fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    fingerprint_final_price_basis,
    parse_price_basis_token,
    price_basis_token,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
    PRICE_APPROVAL_STATUS_APPROVED,
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    FinalPriceApprovalEligibilityError,
    active_approval_matches_basis,
    can_edit_cost_settings_for_order,
    evaluate_final_price_approval_eligibility,
    normalize_price_approval_status,
    pricing_basis_diverged,
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
    reused_existing: bool
    price_basis_token: str


@dataclass(frozen=True, slots=True)
class FinalPriceInvalidationResult:
    order_name: str
    invalidated: bool
    previous_approval: str | None
    reason: str | None


class FinalPriceApprovalGateway(Protocol):
    def lock_order(self, order_name: str) -> Any: ...

    def lock_cost_plan(self, plan_name: str) -> Any: ...

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
) -> FinalPriceApprovalDecision:
    """Central read-model decision for the Cost workspace (phase-2/3 UI)."""

    status = normalize_price_approval_status(price_approval_status)
    can_edit = can_edit_cost_settings_for_order(
        has_edit_cost_settings=has_edit_cost_settings,
        price_approval_status=status,
    )
    if not has_approve_final_price or not has_view_costs:
        return FinalPriceApprovalDecision(
            can_approve_final_price=False,
            reason_code="missing_capability",
            reason_message="Final-price approval capability is required.",
            can_edit_cost_settings=can_edit,
            price_approval_status=status,
            price_basis_token=price_basis_token_value,
            current_price_approval=str(current_price_approval or "").strip() or None,
        )
    if eligibility_error is not None:
        return FinalPriceApprovalDecision(
            can_approve_final_price=False,
            reason_code=eligibility_error.code,
            reason_message=str(eligibility_error),
            can_edit_cost_settings=can_edit,
            price_approval_status=status,
            price_basis_token=price_basis_token_value,
            current_price_approval=str(current_price_approval or "").strip() or None,
        )
    return FinalPriceApprovalDecision(
        can_approve_final_price=True,
        reason_code=None,
        reason_message=None,
        can_edit_cost_settings=can_edit,
        price_approval_status=status,
        price_basis_token=price_basis_token_value,
        current_price_approval=str(current_price_approval or "").strip() or None,
    )


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
        reused_existing=reused_existing,
        price_basis_token=price_basis_token(fingerprint, formula_version=version),
    )


def approve_order_final_price(
    gateway: FinalPriceApprovalGateway,
    *,
    order_name: str,
    expected_price_basis_token: str | None,
) -> FinalPriceApprovalResult:
    """Approve the current commercial total under optimistic basis-token concurrency.

    Writes only price-approval status/link and the approval audit row. Callers
    must not gate this on Draft or draft-restricted edit policies; production
    stage fields on the order are left untouched.
    """

    name = str(order_name or "").strip()
    if not name:
        raise FinalPriceApprovalEligibilityError(
            "order_missing",
            "The cutting order must be saved before its final price can be approved.",
        )

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
        current_fingerprint = fingerprint_final_price_basis(basis) if basis else ""
        if not pricing_basis_diverged(
            stored_fingerprint=getattr(active, "pricing_basis_fingerprint", None),
            current_fingerprint=current_fingerprint,
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
    "FinalPriceInvalidationResult",
    "approve_order_final_price",
    "decide_final_price_approval_actions",
    "invalidate_order_final_price_approval",
]
