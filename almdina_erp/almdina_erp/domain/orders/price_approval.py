"""Independent final-price approval state for a Door Cutting Order.

This is deliberately separate from:
- operational order ``status`` / production lifecycle
- ``customer_quote_status`` (special-leaf quote aggregation)
- Cutting Plan approval
- special door-leaf price approval capabilities
"""

from __future__ import annotations

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


__all__ = [
    "PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION",
    "PRICE_APPROVAL_STATUSES",
    "PRICE_APPROVAL_STATUS_APPROVED",
    "PRICE_APPROVAL_STATUS_UNAPPROVED",
    "PRICE_APPROVAL_VALIDITY_ACTIVE",
    "PRICE_APPROVAL_VALIDITY_INVALIDATED",
    "PRICE_APPROVAL_VALIDITY_STATUSES",
    "PROTECTED_ORDER_PRICE_APPROVAL_FIELDS",
    "PriceApprovalFieldForgeryError",
    "PriceApprovalRecordMutationError",
    "assert_order_price_approval_fields_unchanged",
    "assert_price_approval_record_immutable",
    "default_price_approval_status",
    "normalize_price_approval_link",
    "normalize_price_approval_status",
]
