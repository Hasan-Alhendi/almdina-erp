from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


# The Select schema keeps historical values readable during migration. Runtime
# routing never derives physical position from these legacy status strings.
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

STAGE_STATUSES = ("Pending", "In Progress", "Paused", "Completed", "Cancelled")

# Compatibility exports deliberately contain no routing data. They prevent old
# import sites from becoming a second source of truth while callers are retired.
PRODUCTION_PATHS: dict[str, tuple[str, ...]] = {}
SHOP_FLOOR_ORDER_STATUSES: dict[str, str] = {}
STAGE_DEPARTMENTS: dict[str, str] = {}
SHOP_FLOOR_STAGE_TYPES: tuple[str, ...] = ()

# Physical workflow position belongs to Production Routing, never to order status.
PRODUCTION_ORDER_STATUS = "Production In Progress"
DEPARTMENT_STATUS_BY_STAGE_STATUS: dict[str, str] = {
    "Pending": "بحاجة للعمل",
    "In Progress": "قيد العمل",
    "Paused": "قيد العمل",
    "Completed": "مكتمل",
}

# These are business-operation categories rather than path topology. They remain
# bounded to cutting-specific policy until that capability gets explicit metadata.
CUTTING_LIKE_STAGE_TYPES = frozenset({"Sharyoun", "CNC", "Cutting"})
ACTIVE_STAGE_STATUSES = frozenset({"Pending", "In Progress", "Paused"})
TERMINAL_STAGE_STATUSES = frozenset({"Completed", "Cancelled"})
LOCKED_ORDER_STATUSES = frozenset({"Delivered", "Cancelled"})
DISPATCHABLE_ORDER_STATUSES = frozenset({"Draft", "Rejected", "Pending Review", "Approved"})
PRE_PRODUCTION_ORDER_STATUSES = frozenset({"Draft", "Pending Review", "Rejected", "Approved"})

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


def normalize_order_status(status: str | None) -> str:
    return status or "Draft"


def _fixed_routing_retired() -> ValueError:
    return ValueError("Fixed production paths are retired; resolve the configured Production Routing instead.")


def production_path_sequence(path: str) -> tuple[str, ...]:
    _ = path
    raise _fixed_routing_retired()


def first_stage_type(path: str) -> str:
    _ = path
    raise _fixed_routing_retired()


def next_stage_type(path: str, current_stage_type: str) -> str | None:
    _ = (path, current_stage_type)
    raise _fixed_routing_retired()


def stage_sequence(path: str, stage_type: str) -> int:
    _ = (path, stage_type)
    raise _fixed_routing_retired()


def department_for_stage_type(stage_type: str) -> str | None:
    _ = stage_type
    return None


def department_status_for_stage_status(stage_status: str) -> str | None:
    return DEPARTMENT_STATUS_BY_STAGE_STATUS.get(stage_status)


def resolve_shop_floor_stage_type(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Select a stage to revert to.")
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
    # Return/revert authorization is capability-gated, not status-gated. These
    # helpers remain permissive compatibility predicates for legacy callers.
    # The action is capability-gated; status/path do not authorize it.
    _ = normalize_order_status(status)
    return True


def can_revert_department(status: str | None, *, production_path: str | None) -> bool:
    # Return/revert authorization is capability-gated, not status-gated.
    # The action is capability-gated; status/path do not authorize it.
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
    _ = stage_type
    return PRODUCTION_ORDER_STATUS


def derive_order_status(
    *,
    current_status: str | None,
    production_path: str | None,
    current_stage: StageState | None,
    stages: Iterable[StageState],
    has_open_replacements: bool,
) -> str:
    """Derive generic order status without encoding physical route topology."""
    normalized_current = normalize_order_status(current_status)
    if has_open_replacements:
        return "Replacement Required"
    if normalized_current in {"Ready for Delivery", "Delivered", "Cancelled"}:
        return normalized_current
    if current_stage and current_stage.status != "Cancelled":
        return PRODUCTION_ORDER_STATUS

    stage_list = tuple(stages)
    if any(stage.status in ACTIVE_STAGE_STATUSES for stage in stage_list):
        return PRODUCTION_ORDER_STATUS
    if stage_list and all(stage.status in TERMINAL_STAGE_STATUSES for stage in stage_list):
        return "Ready for Delivery" if production_path else "Completed"
    if production_path:
        return PRODUCTION_ORDER_STATUS
    return normalized_current
