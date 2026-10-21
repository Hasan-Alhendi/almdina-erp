"""Public order list and status rules for the customer bot.

Results carry codes only. Conversation text is a later step. A result never
includes a price, a cost, a note, an assignee, a file, or a production detail
beyond the public status code.
"""

from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.orders.lifecycle import is_order_dispatched
from almdina_erp.almdina_erp.domain.orders.revisions import (
    RevisionState,
    is_current_revision,
    normalize_revision_state,
)


class PublicOrderStatus:
    AWAITING_START = "awaiting_start"
    IN_PROGRESS = "in_progress"
    READY_FOR_PICKUP = "ready_for_pickup"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    UNSUPPORTED = "unsupported"


class CurrentOrderListOutcome:
    NONE = "none"
    ONE = "one"
    MANY = "many"
    IDENTITY_UNAVAILABLE = "identity_unavailable"


class OrderSelectionOutcome:
    SELECTED = "selected"
    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"
    NOT_CURRENT = "not_current"
    IDENTITY_UNAVAILABLE = "identity_unavailable"


_STORED_DELIVERED = "Delivered"
_STORED_CANCELLED = "Cancelled"
_STORED_READY = "Ready for Delivery"
_STAGE_COMPLETED = "Completed"
_LIST_STATUSES = frozenset(
    {
        PublicOrderStatus.AWAITING_START,
        PublicOrderStatus.IN_PROGRESS,
        PublicOrderStatus.READY_FOR_PICKUP,
        PublicOrderStatus.UNSUPPORTED,
    }
)


@dataclass(frozen=True, slots=True)
class OrderStatusFacts:
    """Facts already loaded for one order. This is not a document snapshot."""

    stored_status: str
    production_path: str
    current_stage_name: str
    stage_row_name: str
    stage_status: str
    stage_type: str
    route_terminal: bool | None


@dataclass(frozen=True, slots=True)
class CustomerOrderSummary:
    order_name: str
    order_date: str | None
    public_status: str

    def __post_init__(self) -> None:
        if not self.order_name or self.public_status not in _LIST_STATUSES:
            raise ValueError("a current-order summary needs a name and a listable status")


@dataclass(frozen=True, slots=True)
class CurrentOrderList:
    outcome: str
    identity_code: str
    orders: tuple[CustomerOrderSummary, ...] = ()

    def __post_init__(self) -> None:
        count = len(self.orders)
        if self.outcome == CurrentOrderListOutcome.IDENTITY_UNAVAILABLE and count:
            raise ValueError("an unresolved identity cannot carry orders")
        if self.outcome == CurrentOrderListOutcome.NONE and count:
            raise ValueError("an empty list cannot carry orders")
        if self.outcome == CurrentOrderListOutcome.ONE and count != 1:
            raise ValueError("a single-order list must contain one order")
        if self.outcome == CurrentOrderListOutcome.MANY and count < 2:
            raise ValueError("a multi-order list must contain more than one order")


@dataclass(frozen=True, slots=True)
class OrderSelection:
    outcome: str
    identity_code: str
    order_name: str | None = None
    order_date: str | None = None
    public_status: str | None = None

    def __post_init__(self) -> None:
        if self.outcome in {
            OrderSelectionOutcome.NOT_FOUND,
            OrderSelectionOutcome.IDENTITY_UNAVAILABLE,
        }:
            if self.order_name or self.order_date or self.public_status:
                raise ValueError("a refused selection carries no order facts")
            return
        if self.outcome == OrderSelectionOutcome.NOT_CURRENT:
            if not self.order_name or self.order_date or self.public_status:
                raise ValueError("a non-current selection names the owned document only")
            return
        if self.outcome == OrderSelectionOutcome.CANCELLED:
            if self.public_status != PublicOrderStatus.CANCELLED or not self.order_name:
                raise ValueError("a cancelled selection carries the cancellation only")
            return
        if self.outcome == OrderSelectionOutcome.SELECTED:
            if not self.order_name or self.public_status not in {
                PublicOrderStatus.AWAITING_START,
                PublicOrderStatus.IN_PROGRESS,
                PublicOrderStatus.READY_FOR_PICKUP,
                PublicOrderStatus.DELIVERED,
                PublicOrderStatus.UNSUPPORTED,
            }:
                raise ValueError("a selected order needs a public status")
            return
        raise ValueError("unknown selection outcome")


def classify_public_order_status(facts: OrderStatusFacts) -> str:
    """Map stored status plus the current stage and route to a public code.

    Delivered and Cancelled win. Ready for pickup is true only when the
    current stage row is completed, the order still points at that row, and
    the route has no following stage. A completed middle stage stays in
    progress. A missing or contradictory route does not become ready.
    """

    stored = (facts.stored_status or "").strip() or "Draft"
    if stored == _STORED_DELIVERED:
        return PublicOrderStatus.DELIVERED
    if stored == _STORED_CANCELLED:
        return PublicOrderStatus.CANCELLED

    pointer_matches = bool(
        facts.current_stage_name
        and facts.stage_row_name
        and facts.current_stage_name == facts.stage_row_name
    )
    stage_completed = (facts.stage_status or "").strip() == _STAGE_COMPLETED
    has_stage = bool(facts.stage_row_name or facts.current_stage_name)
    proven_ready = bool(
        pointer_matches and stage_completed and facts.route_terminal is True
    )
    if proven_ready:
        return PublicOrderStatus.READY_FOR_PICKUP

    dispatched = is_order_dispatched(
        production_path=(facts.production_path or "").strip() or None,
        current_stage=(facts.current_stage_name or "").strip() or None,
    )
    stored_ready = stored == _STORED_READY
    route_unknown_on_completed_stage = bool(
        pointer_matches and stage_completed and facts.route_terminal is None
    )
    if stored_ready and (has_stage or dispatched):
        return PublicOrderStatus.UNSUPPORTED
    if route_unknown_on_completed_stage:
        return PublicOrderStatus.UNSUPPORTED
    if stored_ready:
        return PublicOrderStatus.READY_FOR_PICKUP
    if not dispatched:
        return PublicOrderStatus.AWAITING_START
    return PublicOrderStatus.IN_PROGRESS


def owned_revision_is_current(revision_state: str | None) -> bool:
    """Use the order revision rule: only Current copies are the live order.

    Blank or unknown states normalize to Current. Pending Activation and
    Superseded do not. This does not substitute a successor document name.
    """

    return is_current_revision(revision_state)


def plan_read_requires_current_revision(stored_status: str | None, revision_state: str | None) -> bool:
    """Refuse a non-current copy, except a delivered order read on that same document.

    Delivery does not retarget the read to a successor. Approval validity stays
    a separate check.
    """

    if str(stored_status or "").strip() == "Delivered":
        return False
    return not owned_revision_is_current(revision_state)


def revision_state_for_query(revision_state: str | None) -> str:
    return normalize_revision_state(revision_state)


def non_current_revision_states() -> frozenset[str]:
    return frozenset({RevisionState.PENDING_ACTIVATION, RevisionState.SUPERSEDED})


__all__ = [
    "CurrentOrderList",
    "CurrentOrderListOutcome",
    "CustomerOrderSummary",
    "OrderSelection",
    "OrderSelectionOutcome",
    "OrderStatusFacts",
    "PublicOrderStatus",
    "classify_public_order_status",
    "non_current_revision_states",
    "owned_revision_is_current",
    "plan_read_requires_current_revision",
    "revision_state_for_query",
]
