"""Access policy for Door Cutting Price Approval financial history rows.

Phase 1 prepares the record and gates without creating approval endpoints.
Desk create/write/delete stay closed; read requires cost visibility and the
same parent-order scope used for Door Cutting Order access.
"""

from __future__ import annotations


def can_read_price_approval_record(
    *,
    has_view_costs: bool,
    can_access_parent_order: bool,
) -> bool:
    """Financial approval details require both cost visibility and order scope."""

    return bool(has_view_costs) and bool(can_access_parent_order)


def can_mutate_price_approval_via_desk() -> bool:
    """Ordinary Desk CRUD never owns approval history mutations."""

    return False


__all__ = [
    "can_mutate_price_approval_via_desk",
    "can_read_price_approval_record",
]
