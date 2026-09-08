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


def is_pre_dispatch_draft(
    *,
    status: str | None,
    current_production_stage: str | None = None,
) -> bool:
    """True while the order is still Draft and has not been dispatched.

    A planned production route on Draft is a dispatch choice, not an active
    shop-floor stage. Plan mutations stay available until dispatch creates
    ``current_production_stage``.
    """

    if str(current_production_stage or "").strip():
        return False
    return can_edit_order(status)


def can_recalculate_drawing_system_plan(
    *,
    has_recalculate_permission: bool,
    approved_plan: str | None,
    production_path: str | None,
    status: str | None,
    current_stage_type: str | None,
) -> bool:
    """Evaluate when an approved snapshot may be replaced by a new calculation.

    Draft remains fully mutable before dispatch, including when a plan was
    already approved or a production route was chosen. At Drawing the approved
    snapshot stays production-authoritative while a replacement is prepared;
    explicit re-approval is what activates the newly calculated plan. After
    the order leaves Drawing the exception stays closed.
    """
    del approved_plan
    if not has_recalculate_permission:
        return False
    if can_edit_order(status):
        return True
    return is_drawing_stage(
        production_path=production_path,
        status=status,
        current_stage_type=current_stage_type,
    )
