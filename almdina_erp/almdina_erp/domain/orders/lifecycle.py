from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


ORDER_STATUSES = (
    "Draft",
    "Pending Review",
    "Approved",
    "At Sharyoun",
    "At Drawing",
    "At CNC",
    "At Sanding",
    "Ready for Delivery",
    "Delivered",
    "Cutting In Progress",
    "Cut Completed",
    "Edge Banding In Progress",
    "Production In Progress",
    "Quality Check",
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

PRODUCTION_PATHS: dict[str, tuple[str, ...]] = {
    "Sharyoun": ("Sharyoun", "Sanding"),
    "Drawing": ("Drawing", "CNC", "Sanding"),
}

SHOP_FLOOR_ORDER_STATUSES: dict[str, str] = {
    "Sharyoun": "At Sharyoun",
    "Drawing": "At Drawing",
    "CNC": "At CNC",
    "Sanding": "At Sanding",
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

SHOP_FLOOR_STAGE_TYPES = tuple(SHOP_FLOOR_ORDER_STATUSES)
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
    "cancel": (frozenset({"Pending", "In Progress", "Paused", "Completed"}), "Cancelled"),
    "reopen": (frozenset({"Pending", "In Progress", "Paused", "Completed", "Cancelled"}), "Pending"),
}


@dataclass(frozen=True, slots=True)
class StageState:
    stage_type: str
    status: str


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


def order_status_for_stage_type(stage_type: str) -> str:
    mapped = SHOP_FLOOR_ORDER_STATUSES.get(stage_type)
    if mapped:
        return mapped
    if stage_type == "Cutting":
        return "Cutting In Progress"
    if stage_type == "Edge Banding":
        return "Edge Banding In Progress"
    if stage_type == "Quality Check":
        return "Quality Check"
    return "Production In Progress"


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

    if normalized_current in {"Ready for Delivery", "Delivered"}:
        return normalized_current

    if production_path:
        if current_stage and current_stage.status != "Cancelled":
            mapped = SHOP_FLOOR_ORDER_STATUSES.get(current_stage.stage_type)
            if mapped:
                return mapped
        if normalized_current.startswith("At "):
            return normalized_current

    stage_list = tuple(stages)
    if not stage_list:
        return normalized_current

    if all(stage.status in TERMINAL_STAGE_STATUSES for stage in stage_list):
        sanding_completed = any(
            stage.stage_type == "Sanding" and stage.status == "Completed"
            for stage in stage_list
        )
        return "Ready for Delivery" if sanding_completed else "Completed"

    active = next(
        (stage for stage in stage_list if stage.status in ACTIVE_STAGE_STATUSES),
        None,
    )
    if active:
        return order_status_for_stage_type(active.stage_type)

    cutting = next((stage for stage in stage_list if stage.stage_type == "Cutting"), None)
    edge = next((stage for stage in stage_list if stage.stage_type == "Edge Banding"), None)
    if cutting and cutting.status == "Completed" and edge and edge.status == "Pending":
        return "Cut Completed"
    return "Approved"
