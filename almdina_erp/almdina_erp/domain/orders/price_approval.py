"""Independent final-price approval state for a Door Cutting Order.

This is deliberately separate from:
- operational order ``status`` / production lifecycle
- ``customer_quote_status`` (special-leaf quote aggregation)
- Cutting Plan approval
- special door-leaf price approval capabilities
"""

from __future__ import annotations

import math
from typing import Any


PRICE_APPROVAL_STATUS_UNAPPROVED = "Unapproved"
PRICE_APPROVAL_STATUS_APPROVED = "Approved"
PRICE_APPROVAL_STATUSES = (
    PRICE_APPROVAL_STATUS_UNAPPROVED,
    PRICE_APPROVAL_STATUS_APPROVED,
)

PRICE_APPROVAL_VALIDITY_ACTIVE = "Active"
PRICE_APPROVAL_VALIDITY_INVALIDATED = "Invalidated"
PRICE_APPROVAL_VALIDITY_STATUSES = (
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
)

# Fingerprint formula version reserved for phase-2 approval recording.
PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION = "1"

PROTECTED_ORDER_PRICE_APPROVAL_FIELDS = (
    "price_approval_status",
    "current_price_approval",
)


class PriceApprovalFieldForgeryError(ValueError):
    """Raised when a client tries to forge order price-approval fields."""


class PriceApprovalRecordMutationError(ValueError):
    """Raised when a price-approval audit row is mutated outside controlled transitions."""


def default_price_approval_status() -> str:
    return PRICE_APPROVAL_STATUS_UNAPPROVED


def normalize_price_approval_status(value: Any) -> str:
    text = str(value or "").strip()
    if text in PRICE_APPROVAL_STATUSES:
        return text
    return PRICE_APPROVAL_STATUS_UNAPPROVED


def normalize_price_approval_link(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def assert_order_price_approval_fields_unchanged(
    *,
    previous_status: Any,
    previous_link: Any,
    incoming_status: Any,
    incoming_link: Any,
    allow_mutation: bool,
    is_new: bool = False,
) -> None:
    """Reject forged status/link writes unless an authorized command opts in."""

    if allow_mutation:
        return

    expected_status = (
        PRICE_APPROVAL_STATUS_UNAPPROVED
        if is_new
        else normalize_price_approval_status(previous_status)
    )
    expected_link = None if is_new else normalize_price_approval_link(previous_link)
    actual_status = normalize_price_approval_status(incoming_status)
    actual_link = normalize_price_approval_link(incoming_link)

    if actual_status != expected_status or actual_link != expected_link:
        raise PriceApprovalFieldForgeryError(
            "Price approval status and current approval link are command-owned "
            "and cannot be changed through ordinary document save."
        )


def assert_price_approval_record_immutable(
    *,
    is_new: bool,
    allow_status_transition: bool,
    previous_validity: Any,
    incoming_validity: Any,
) -> None:
    """Keep approval history intact; only controlled invalidate transitions later."""

    if is_new:
        return
    if allow_status_transition:
        previous = str(previous_validity or "").strip()
        incoming = str(incoming_validity or "").strip()
        if previous == PRICE_APPROVAL_VALIDITY_ACTIVE and incoming == PRICE_APPROVAL_VALIDITY_INVALIDATED:
            return
        raise PriceApprovalRecordMutationError(
            "Only an Active price approval may transition to Invalidated."
        )
    raise PriceApprovalRecordMutationError(
        "Door Cutting Price Approval records are immutable after insert."
    )


def cost_settings_locked_by_price_approval(status: Any) -> bool:
    """Approved final price freezes cost-settings inputs until phase-3 invalidation."""

    return normalize_price_approval_status(status) == PRICE_APPROVAL_STATUS_APPROVED


def can_edit_cost_settings_for_order(
    *,
    has_edit_cost_settings: bool,
    price_approval_status: Any,
) -> bool:
    """Capability remains granted; Approved status alone blocks cost-settings edits."""

    if not has_edit_cost_settings:
        return False
    return not cost_settings_locked_by_price_approval(price_approval_status)


class FinalPriceApprovalEligibilityError(ValueError):
    """Raised when an order is not eligible for final-price approval."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(message)


def evaluate_final_price_approval_eligibility(
    *,
    order_name: str | None,
    order_status: str | None,
    revision_state: str | None,
    docstatus: int | None,
    cutting_plan: str | None,
    plan_belongs_to_order: bool,
    plan_is_current: bool,
    pending_price_labels: tuple[str, ...] | list[str],
    board_rate_present: bool,
    cutting_rate_present: bool,
    board_rate_usd: float,
    cutting_cost_per_board_usd: float,
    offcut_price_usd: float,
    approved_amount_usd: float,
) -> None:
    """Fail closed when the saved commercial price cannot be approved yet.

    Production stage is intentionally irrelevant: Draft, Drawing, CNC, Sanding,
    or later operational states may all receive final-price approval when access,
    cost visibility, and pricing completeness/freshness hold. This policy must
    not reuse draft-restricted edit_order or special-leaf pricing rules.
    Only Cancelled (and superseded revisions) block among operational states.
    """

    if not str(order_name or "").strip():
        raise FinalPriceApprovalEligibilityError(
            "order_missing",
            "The cutting order must be saved before its final price can be approved.",
        )
    if int(docstatus or 0) != 0:
        raise FinalPriceApprovalEligibilityError(
            "docstatus_invalid",
            "The order document state does not allow final-price approval.",
        )
    # Do not require Draft or a specific production department/stage.
    if str(order_status or "").strip() == "Cancelled":
        raise FinalPriceApprovalEligibilityError(
            "order_cancelled",
            "A cancelled order cannot receive final-price approval.",
        )
    if str(revision_state or "Current").strip() == "Superseded":
        raise FinalPriceApprovalEligibilityError(
            "order_superseded",
            "A superseded order revision cannot receive final-price approval.",
        )
    if not str(cutting_plan or "").strip():
        raise FinalPriceApprovalEligibilityError(
            "cost_plan_missing",
            "A valid cost-reference cutting plan is required before approving the final price.",
        )
    if not plan_belongs_to_order:
        raise FinalPriceApprovalEligibilityError(
            "foreign_plan",
            "The selected cutting plan belongs to another order.",
        )
    if not plan_is_current:
        raise FinalPriceApprovalEligibilityError(
            "stale_plan",
            "The cost-reference cutting plan is outdated. Recalculate and review the price first.",
        )
    pending = tuple(str(label).strip() for label in pending_price_labels if str(label or "").strip())
    if pending:
        raise FinalPriceApprovalEligibilityError(
            "pending_prices",
            "Special or corner prices are still pending: {0}.".format(", ".join(pending)),
        )
    if not board_rate_present:
        raise FinalPriceApprovalEligibilityError(
            "board_rate_missing",
            "Board rate must be entered on the cost page before approving the final price.",
        )
    if not cutting_rate_present:
        raise FinalPriceApprovalEligibilityError(
            "cutting_rate_missing",
            "Cutting fee per board must be entered on the cost page before approving the final price.",
        )
    for label, value in (
        ("Board rate", board_rate_usd),
        ("Cutting fee per board", cutting_cost_per_board_usd),
        ("Offcut price", offcut_price_usd),
        ("Final price total", approved_amount_usd),
    ):
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise FinalPriceApprovalEligibilityError(
                "invalid_amount",
                f"{label} must be a valid number.",
            ) from exc
        if not math.isfinite(number):
            raise FinalPriceApprovalEligibilityError(
                "invalid_amount",
                f"{label} must be finite.",
            )
        if number < 0:
            raise FinalPriceApprovalEligibilityError(
                "negative_amount",
                f"{label} cannot be negative.",
            )


def active_approval_matches_basis(
    *,
    validity_status: Any,
    stored_fingerprint: Any,
    current_fingerprint: str,
) -> bool:
    """Idempotent reuse requires an Active record for the exact current basis."""

    if str(validity_status or "").strip() != PRICE_APPROVAL_VALIDITY_ACTIVE:
        return False
    return str(stored_fingerprint or "").strip() == str(current_fingerprint or "").strip()


def should_invalidate_final_price_approval(status: Any) -> bool:
    """Approved commercial price must clear when a pricing-basis mutation lands."""

    return normalize_price_approval_status(status) == PRICE_APPROVAL_STATUS_APPROVED


def pricing_basis_diverged(
    *,
    stored_fingerprint: Any,
    current_fingerprint: str,
) -> bool:
    """True when the live commercial basis no longer matches the Active approval."""

    stored = str(stored_fingerprint or "").strip()
    current = str(current_fingerprint or "").strip()
    if not stored or not current:
        return True
    return stored != current


__all__ = [
    "PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION",
    "PRICE_APPROVAL_STATUSES",
    "PRICE_APPROVAL_STATUS_APPROVED",
    "PRICE_APPROVAL_STATUS_UNAPPROVED",
    "PRICE_APPROVAL_VALIDITY_ACTIVE",
    "PRICE_APPROVAL_VALIDITY_INVALIDATED",
    "PRICE_APPROVAL_VALIDITY_STATUSES",
    "PROTECTED_ORDER_PRICE_APPROVAL_FIELDS",
    "FinalPriceApprovalEligibilityError",
    "PriceApprovalFieldForgeryError",
    "PriceApprovalRecordMutationError",
    "active_approval_matches_basis",
    "assert_order_price_approval_fields_unchanged",
    "assert_price_approval_record_immutable",
    "can_edit_cost_settings_for_order",
    "cost_settings_locked_by_price_approval",
    "default_price_approval_status",
    "evaluate_final_price_approval_eligibility",
    "normalize_price_approval_link",
    "normalize_price_approval_status",
    "pricing_basis_diverged",
    "should_invalidate_final_price_approval",
]
