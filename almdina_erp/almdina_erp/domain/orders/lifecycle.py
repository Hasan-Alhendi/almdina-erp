from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


# Lifecycle/business states remain stable. Production stage statuses are dynamic
# and are projected from the stage label carried by the runtime Production Stage.
ORDER_STATUSES = (
    "Draft",
    "Pending Review",
    "Approved",
    "Ready for Delivery",
    "Delivered",
    "Completed",
    "Rejected",
    "On Hold",
    "Cancelled",
    "Replacement Required",
    "Partially Completed",
)

STAGE_STATUSES = (
    "Pending",
    "In Progress",
    "Paused",
    "Completed",
    "Cancelled",
)

# Legacy helpers are retained for compatibility callers only. Runtime routing is
# owned by Production Routing and Production Stage Definition.
PRODUCTION_PATHS: dict[str, tuple[str, ...]] = {
    "Sharyoun": ("Sharyoun", "Sanding"),
    "Drawing": ("Drawing", "CNC", "Sanding"),
}

STAGE_DEPARTMENTS: dict[str, str] = {
    "Sharyoun": "شريون",
    "Drawing": "رسم",
    "CNC": "CNC",
    "Sanding": "تقشيط",
}

DEPARTMENT_STATUS_BY_STAGE_STATUS: dict[str, str] = {
    "Pending": "بحاجة للعمل",
    "In Progress": "قيد العمل",
    "Paused": "قيد العمل",
    "Completed": "مكتمل",
}

SHOP_FLOOR_STAGE_TYPES = tuple(STAGE_DEPARTMENTS)
CUTTING_LIKE_STAGE_TYPES = frozenset({"Sharyoun", "CNC", "Cutting"})
ACTIVE_STAGE_STATUSES = frozenset({"Pending", "In Progress", "Paused"})
TERMINAL_STAGE_STATUSES = frozenset({"Completed", "Cancelled"})
LOCKED_ORDER_STATUSES = frozenset({"Delivered", "Cancelled"})
# Review/approve were retired: draft-like and leftover review/approved orders
# may all be sent straight to production.
DISPATCHABLE_ORDER_STATUSES = frozenset(
    {"Draft", "Rejected", "Pending Review", "Approved"}
)
PRE_PRODUCTION_ORDER_STATUSES = frozenset(
    {"Draft", "Pending Review", "Rejected", "Approved"}
)

STAGE_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "start": (frozenset({"Pending"}), "In Progress"),
    "pause": (frozenset({"In Progress"}), "Paused"),
    "resume": (frozenset({"Paused"}), "In Progress"),
    "finish": (frozenset({"In Progress", "Paused"}), "Completed"),
    "direct_handoff": (frozenset({"Pending"}), "Completed"),
    "cancel": (frozenset({"Pending", "In Progress", "Paused", "Completed"}), "Cancelled"),
    "reopen": (frozenset({"Pending", "In Progress", "Paused", "Completed", "Cancelled"}), "Pending"),
}


@dataclass(frozen=True, slots=True)
class StageState:
    stage_type: str
    status: str
    department_label: str | None = None


def normalize_order_status(status: str | None) -> str:
    return status or "Draft"


def production_path_sequence(path: str) -> tuple[str, ...]:
    try:
        return PRODUCTION_PATHS[path]
    except KeyError as exc:
        raise ValueError(f"Invalid production path: {path}") from exc


def first_stage_type(path: str) -> str:
    return production_path_sequence(path)[0]


def next_stage_type(path: str, current_stage_type: str) -> str | None:
    sequence = production_path_sequence(path)
    try:
        index = sequence.index(current_stage_type)
    except ValueError as exc:
        raise ValueError(f"Stage {current_stage_type} is not part of path {path}") from exc
    if index + 1 >= len(sequence):
        return None
    return sequence[index + 1]


def stage_sequence(path: str, stage_type: str) -> int:
    sequence = production_path_sequence(path)
    try:
        return (sequence.index(stage_type) + 1) * 10
    except ValueError as exc:
        raise ValueError(f"Stage {stage_type} is not part of path {path}") from exc


def department_for_stage_type(stage_type: str) -> str | None:
    return STAGE_DEPARTMENTS.get(stage_type)


def department_status_for_stage_status(stage_status: str) -> str | None:
    return DEPARTMENT_STATUS_BY_STAGE_STATUS.get(stage_status)


def resolve_shop_floor_stage_type(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Select a stage to revert to.")
    if raw in SHOP_FLOOR_STAGE_TYPES:
        return raw
    for stage_type, department in STAGE_DEPARTMENTS.items():
        if raw == department:
            return stage_type
    return raw


def is_cutting_like_stage(stage_type: str) -> bool:
    return stage_type in CUTTING_LIKE_STAGE_TYPES


def is_order_dispatched(*, production_path: str | None, current_stage: str | None) -> bool:
    return bool(production_path or current_stage)


def can_dispatch_from_status(status: str | None) -> bool:
    return normalize_order_status(status) in DISPATCHABLE_ORDER_STATUSES


def can_mark_delivered(status: str | None) -> bool:
    return normalize_order_status(status) == "Ready for Delivery"


def can_return_to_draft(status: str | None) -> bool:
    """Return-to-draft is capability-gated, not status-gated.

    Status is accepted for API compatibility; callers authorize via
    ``RETURN_ORDER_TO_DRAFT``. Already-draft documents are a no-op at runtime.
    """

    _ = normalize_order_status(status)
    return True


def can_revert_department(status: str | None, *, production_path: str | None) -> bool:
    """Revert is capability-gated; status/path do not authorize the action.

    Structural target checks (existing earlier stages) remain in the command.
    """

    _ = normalize_order_status(status)
    _ = production_path
    return True


def can_transition_stage(current_status: str, event: str) -> bool:
    transition = STAGE_TRANSITIONS.get(event)
    return bool(transition and current_status in transition[0])


def transition_stage(current_status: str, event: str) -> str:
    transition = STAGE_TRANSITIONS.get(event)
    if not transition:
        raise ValueError(f"Unknown stage event: {event}")
    allowed_from, target = transition
    if current_status not in allowed_from:
        raise ValueError(f"Cannot {event} stage from {current_status}")
    return target


def order_status_for_stage(
    stage_type: str | None,
    department_label: str | None = None,
) -> str:
    """Return the exact user-defined production-stage label for display status.

    ``department_label`` is the runtime snapshot copied from the selected
    Production Stage Definition. ``stage_type`` is only a defensive fallback for
    older execution rows that do not carry a label.
    """

    label = str(department_label or "").strip()
    if label:
        return label
    return str(stage_type or "").strip() or "Production"


def order_status_for_stage_type(stage_type: str) -> str:
    """Compatibility helper for legacy callers without a stage-label snapshot."""

    return order_status_for_stage(stage_type)


def derive_order_status(
    *,
    current_status: str | None,
    production_path: str | None,
    current_stage: StageState | None,
    stages: Iterable[StageState],
    has_open_replacements: bool,
) -> str:
    """Derive the order status from lifecycle facts without reading Frappe state."""
    normalized_current = normalize_order_status(current_status)

    if has_open_replacements:
        return "Replacement Required"

    if normalized_current in {"Ready for Delivery", "Delivered", "Cancelled"}:
        return normalized_current

    if production_path and current_stage and current_stage.status != "Cancelled":
        return order_status_for_stage(
            current_stage.stage_type,
            current_stage.department_label,
        )

    stage_list = tuple(stages)
    if not stage_list:
        return normalized_current

    if all(stage.status in TERMINAL_STAGE_STATUSES for stage in stage_list):
        return "Completed"

    active = next(
        (stage for stage in stage_list if stage.status in ACTIVE_STAGE_STATUSES),
        None,
    )
    if active:
        return order_status_for_stage(active.stage_type, active.department_label)

    return normalized_current if normalized_current in ORDER_STATUSES else "Approved"
