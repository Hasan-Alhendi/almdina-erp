from __future__ import annotations

from collections.abc import Collection


DRAFT_LIKE_STATUSES = frozenset({"Draft", "Pending Review", "Rejected"})
LOCKED_ORDER_STATUSES = frozenset({"Delivered", "Cancelled"})


def normalize_status(status: str | None) -> str:
    """Return the business default used for orders without an explicit status."""
    return status or "Draft"


def is_draft_like(status: str | None) -> bool:
    return normalize_status(status) in DRAFT_LIKE_STATUSES


def is_locked_status(status: str | None) -> bool:
    return (status or "") in LOCKED_ORDER_STATUSES


def can_edit_order(status: str | None, roles: Collection[str] = ()) -> bool:
    """Only draft-like documents are editable in place.

    The ``roles`` argument is retained for API compatibility, but privileged users
    must create a controlled revision instead of modifying approved history.
    """

    del roles
    return is_draft_like(status)


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
