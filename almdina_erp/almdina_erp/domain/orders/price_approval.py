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

# Historical approval text. Absent, None, and blank are stored as no note.
APPROVAL_NOTE_MAX_LENGTH = 500

# Fixed reason for authorized manual cancel (distinct from auto-invalidation).
MANUAL_PRICE_APPROVAL_CANCELLED = "manual_price_approval_cancelled"

# Fields an authorized invalidation must not rewrite, including the original note.
PROTECTED_APPROVAL_HISTORY_FIELDS = (
    "door_cutting_order",
    "cutting_plan",
    "approved_amount",
    "currency",
    "approved_by",
    "approved_on",
    "pricing_basis_fingerprint",
    "fingerprint_formula_version",
    "approval_note",
)


class PriceApprovalFieldForgeryError(ValueError):
    """Raised when a client tries to forge order price-approval fields."""


class PriceApprovalRecordMutationError(ValueError):
    """Raised when a price-approval audit row is mutated outside controlled transitions."""


class ApprovalNoteError(ValueError):
    """Raised when an approval note cannot be stored as entered."""


def normalize_approval_note(value: Any) -> str | None:
    """Return a stored approval note, or None when the caller left it blank.

    Leading and trailing whitespace is removed. Line breaks inside the note stay.
    Non-text values and notes longer than the limit are rejected without truncation.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise ApprovalNoteError("Approval note must be text.")
    text = value.strip()
    if not text:
        return None
    if len(text) > APPROVAL_NOTE_MAX_LENGTH:
        raise ApprovalNoteError(
            f"Approval note cannot exceed {APPROVAL_NOTE_MAX_LENGTH} characters."
        )
    return text


def _history_value(source: Any, fieldname: str) -> Any:
    if isinstance(source, dict):
        return source.get(fieldname)
    getter = getattr(source, "get", None)
    if callable(getter):
        return getter(fieldname)
    return getattr(source, fieldname, None)


def assert_invalidation_preserves_approval_details(
    *,
    previous: Any,
    incoming: Any,
) -> None:
    """Authorized invalidation may close a record, not rewrite what was approved."""

    for fieldname in PROTECTED_APPROVAL_HISTORY_FIELDS:
        if _history_value(previous, fieldname) != _history_value(incoming, fieldname):
            raise PriceApprovalRecordMutationError(
                "Invalidating a price approval cannot rewrite historical approval details."
            )


def _user_link(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PriceApprovalRecordMutationError("Invalidated by must be a user link.")
    text = value.strip()
    return text or None


def assert_invalidated_by_mutation_allowed(
    *,
    allow_authorized_invalidation: bool,
    previous_invalidated_by: Any,
    incoming_invalidated_by: Any,
) -> None:
    """Record the invalidating user only on an authorized Active to Invalidated transition."""

    previous = _user_link(previous_invalidated_by)
    incoming = _user_link(incoming_invalidated_by)
    if previous == incoming:
        return
    if allow_authorized_invalidation:
        return
    raise PriceApprovalRecordMutationError(
        "Invalidated by can be recorded only during an authorized invalidation."
    )


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


def reconcile_order_price_approval_fields(
    *,
    previous_status: Any,
    previous_link: Any,
    incoming_status: Any,
    incoming_link: Any,
    allow_mutation: bool,
    is_new: bool = False,
) -> tuple[str, str | None]:
    """Return the status/link that ordinary saves must persist.

    Client values never create, clear, or restore approval. Only an authorized
    command (``allow_mutation``) may write its incoming values. A stale form that
    still carries Unapproved after a successful approve is restored from the
    trusted database values instead of failing the whole commercial save.
    """

    if allow_mutation:
        return (
            normalize_price_approval_status(incoming_status),
            normalize_price_approval_link(incoming_link),
        )
    if is_new:
        return PRICE_APPROVAL_STATUS_UNAPPROVED, None
    return (
        normalize_price_approval_status(previous_status),
        normalize_price_approval_link(previous_link),
    )


def assert_order_price_approval_fields_unchanged(
    *,
    previous_status: Any,
    previous_link: Any,
    incoming_status: Any,
    incoming_link: Any,
    allow_mutation: bool,
    is_new: bool = False,
) -> None:
    """Compatibility check: forged writes are ignored via reconcile, not trusted.

    Prefer :func:`reconcile_order_price_approval_fields` on save paths. This helper
    remains for contracts that assert client values cannot become authority.
    """

    if allow_mutation:
        return

    trusted_status, trusted_link = reconcile_order_price_approval_fields(
        previous_status=previous_status,
        previous_link=previous_link,
        incoming_status=incoming_status,
        incoming_link=incoming_link,
        allow_mutation=False,
        is_new=is_new,
    )
    actual_status = normalize_price_approval_status(incoming_status)
    actual_link = normalize_price_approval_link(incoming_link)
    if actual_status != trusted_status or actual_link != trusted_link:
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
    """Approved final price no longer freezes cost-settings edits.

    Kept as a named policy hook so call sites fail closed to ``False`` (unlocked)
    after the product contract change. Capability and lifecycle still govern edits.
    """

    del status
    return False


def can_edit_cost_settings_for_order(
    *,
    has_edit_cost_settings: bool,
    price_approval_status: Any,
) -> bool:
    """Cost-settings edits follow capability/lifecycle; Approved alone does not block."""

    del price_approval_status
    return bool(has_edit_cost_settings)


class FinalPriceApprovalEligibilityError(ValueError):
    """Raised when an order is not eligible for final-price approval."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(message)


class FinalPriceCancellationError(ValueError):
    """Raised when a manual final-price cancellation cannot proceed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(message)


def evaluate_final_price_cancellation_document_rules(
    *,
    order_name: str | None,
    order_status: str | None,
    revision_state: str | None,
    docstatus: int | None,
) -> None:
    """Document rules for manual cancel. Production stage is irrelevant.

    Cancelling an existing approval does not require a fresh plan or complete
    pricing. Cancelled orders and superseded revisions remain blocked.
    """

    if not str(order_name or "").strip():
        raise FinalPriceCancellationError(
            "order_missing",
            "The cutting order must be saved before its final price can be cancelled.",
        )
    if int(docstatus or 0) != 0:
        raise FinalPriceCancellationError(
            "docstatus_invalid",
            "The order document state does not allow final-price cancellation.",
        )
    if str(order_status or "").strip() == "Cancelled":
        raise FinalPriceCancellationError(
            "order_cancelled",
            "A cancelled order cannot have its final-price approval cancelled.",
        )
    if str(revision_state or "Current").strip() == "Superseded":
        raise FinalPriceCancellationError(
            "order_superseded",
            "A superseded order revision cannot have its final-price approval cancelled.",
        )


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
    "APPROVAL_NOTE_MAX_LENGTH",
    "MANUAL_PRICE_APPROVAL_CANCELLED",
    "PROTECTED_APPROVAL_HISTORY_FIELDS",
    "PROTECTED_ORDER_PRICE_APPROVAL_FIELDS",
    "ApprovalNoteError",
    "FinalPriceApprovalEligibilityError",
    "FinalPriceCancellationError",
    "PriceApprovalFieldForgeryError",
    "PriceApprovalRecordMutationError",
    "active_approval_matches_basis",
    "assert_invalidated_by_mutation_allowed",
    "assert_invalidation_preserves_approval_details",
    "assert_order_price_approval_fields_unchanged",
    "assert_price_approval_record_immutable",
    "normalize_approval_note",
    "can_edit_cost_settings_for_order",
    "cost_settings_locked_by_price_approval",
    "default_price_approval_status",
    "evaluate_final_price_approval_eligibility",
    "evaluate_final_price_cancellation_document_rules",
    "normalize_price_approval_link",
    "normalize_price_approval_status",
    "pricing_basis_diverged",
    "reconcile_order_price_approval_fields",
    "should_invalidate_final_price_approval",
]
