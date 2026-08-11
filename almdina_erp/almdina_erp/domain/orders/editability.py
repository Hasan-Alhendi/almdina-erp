from __future__ import annotations

from collections.abc import Collection


DRAFT_LIKE_STATUSES = frozenset({"Draft", "Pending Review", "Rejected"})
LOCKED_ORDER_STATUSES = frozenset({"Delivered", "Cancelled"})
# Once cutting has started (Sharyoun/CNC) or later stages, in-place edits stop.
CUTTING_OR_LATER_STATUSES = frozenset(
    {
        "At Sharyoun",
        "At CNC",
        "At Sanding",
        "Ready for Delivery",
        "Delivered",
        "Cancelled",
        "Completed",
        "Cutting In Progress",
        "Cut Completed",
        "Edge Banding In Progress",
        "Quality Check",
        "Partially Completed",
    }
)


def normalize_status(status: str | None) -> str:
    """Return the business default used for orders without an explicit status."""
    return status or "Draft"


def is_draft_like(status: str | None) -> bool:
    return normalize_status(status) in DRAFT_LIKE_STATUSES


def is_locked_status(status: str | None) -> bool:
    return (status or "") in LOCKED_ORDER_STATUSES


def is_before_cutting(status: str | None) -> bool:
    """True while the order has not reached Sharyoun/CNC cutting or later."""
    normalized = normalize_status(status)
    if normalized in LOCKED_ORDER_STATUSES:
        return False
    return normalized not in CUTTING_OR_LATER_STATUSES


def can_edit_order(
    status: str | None,
    roles: Collection[str] = (),
    *,
    privileged: bool | None = None,
) -> bool:
    """Decide whether an order document may be edited in place.

    In-place editing is restricted to Draft only. Once the order leaves Draft
    (dispatch, rejection leftovers, etc.) changes go through return-to-draft or
    a controlled revision — never through a privileged edit session.
    """

    del roles, privileged
    return normalize_status(status) == "Draft"


def is_drawing_stage(
    *,
    production_path: str | None,
    status: str | None,
    current_stage_type: str | None,
) -> bool:
    """Evaluate whether an order is currently handled by the drawing department."""
    del production_path  # Route names are configurable; the active stage owns behavior.
    return normalize_status(status) == "At Drawing" or current_stage_type == "Drawing"


def can_recalculate_drawing_system_plan(
    *,
    has_recalculate_permission: bool,
    approved_plan: str | None,
    production_path: str | None,
    status: str | None,
    current_stage_type: str | None,
) -> bool:
    """Evaluate the exceptional drawing-stage recalculation policy."""
    if not has_recalculate_permission:
        return False
    if approved_plan:
        return False
    return is_drawing_stage(
        production_path=production_path,
        status=status,
        current_stage_type=current_stage_type,
    )
