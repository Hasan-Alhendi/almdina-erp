from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Sequence

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_STAGE_TYPES,
    can_dispatch_from_status,
    can_mark_delivered,
    can_revert_department,
    first_stage_type,
    is_order_dispatched,
    next_stage_type,
    order_status_for_stage_type,
    production_path_sequence,
    resolve_shop_floor_stage_type,
    stage_sequence,
    transition_stage,
)


class ShopFloorCommandError(ValueError):
    """Raised when a shop-floor command violates a business rule."""


class ShopFloorPermissionDenied(PermissionError):
    """Raised when the current actor cannot execute a shop-floor command."""


@dataclass(frozen=True, slots=True)
class OrderState:
    name: str
    status: str
    production_path: str | None
    current_stage: str | None
    has_cutting_plan: bool
    plan_needs_recalculation: bool
    drawing_dxf_status: str | None = None


@dataclass(frozen=True, slots=True)
class StageState:
    name: str
    order_name: str
    stage_type: str
    status: str
    assigned_to: str | None
    sequence: int
    start_time: datetime | None = None
    paused_seconds: int = 0
    piece_label: str | None = None


class ShopFloorCommandPort(Protocol):
    def current_user(self) -> str: ...

    def require_dispatch_permission(self) -> None: ...

    def require_delivery_permission(self) -> None: ...

    def require_revert_permission(self) -> None: ...

    def require_stage_access(self, stage_name: str) -> None: ...

    def get_order_state(self, order_name: str) -> OrderState: ...

    def get_stage_state(self, stage_name: str) -> StageState: ...

    def validate_special_shapes(self, order_name: str) -> None: ...

    def assert_worker_for_stage(self, user: str, stage_type: str) -> None: ...

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]: ...

    def cancel_non_shop_floor_active_stages(self, order_name: str) -> None: ...

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
    ) -> StageState: ...

    def track_order_to_stage(
        self,
        order_name: str,
        *,
        stage_name: str,
        path: str | None = None,
    ) -> None: ...

    def track_order_ready_for_delivery(self, order_name: str) -> None: ...

    def track_order_delivered(self, order_name: str) -> None: ...

    def log_stage_event(
        self,
        stage_name: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None: ...

    def consume_stock_if_due(
        self,
        order_name: str,
        stage_type: str,
        trigger: str,
    ) -> None: ...

    def register_remnants_if_due(
        self,
        order_name: str,
        stage_type: str,
    ) -> dict[str, Any] | None: ...

    def close_open_pause(self, stage_name: str, resumed_by: str) -> None: ...

    def start_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
    ) -> StageState: ...

    def complete_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
        completed_qty: int,
    ) -> StageState: ...

    def required_piece_qty(self, order_name: str) -> int: ...

    def get_order_status(self, order_name: str) -> str | None: ...

    def list_revert_candidates(
        self,
        order_name: str,
        stage_type: str,
    ) -> Sequence[StageState]: ...

    def stage_exists(self, stage_name: str | None) -> bool: ...

    def list_later_stages(
        self,
        order_name: str,
        sequence: int,
    ) -> Sequence[StageState]: ...

    def cancel_stage(self, stage_name: str, *, target_status: str) -> StageState: ...

    def reopen_stage(self, stage_name: str, *, target_status: str) -> StageState: ...


def _transition(current_status: str, event: str, message: str) -> str:
    try:
        return transition_stage(current_status, event)
    except ValueError as error:
        raise ShopFloorCommandError(message) from error


def _next_stage(path: str, stage_type: str) -> str | None:
    try:
        return next_stage_type(path, stage_type)
    except ValueError as error:
        raise ShopFloorCommandError(
            f"Stage {stage_type} is not part of path {path}."
        ) from error


def _validate_path(path: str) -> None:
    try:
        production_path_sequence(path)
    except ValueError as error:
        raise ShopFloorCommandError(f"Invalid production path: {path}") from error


def assert_order_ready_for_dispatch(order: OrderState) -> None:
    if is_order_dispatched(
        production_path=order.production_path,
        current_stage=order.current_stage,
    ):
        raise ShopFloorCommandError(f"Order {order.name} is already dispatched.")
    if not can_dispatch_from_status(order.status):
        raise ShopFloorCommandError(
            "Only draft or rejected orders can be sent to production."
        )
    if not order.has_cutting_plan:
        raise ShopFloorCommandError(
            "Calculate a cutting plan before sending the order to production."
        )
    if order.plan_needs_recalculation:
        raise ShopFloorCommandError(
            "Recalculate the cutting plan before sending the order to production."
        )


def get_handoff_workers(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> list[dict[str, str]]:
    repository.require_stage_access(stage_name)
    stage = repository.get_stage_state(stage_name)
    order = repository.get_order_state(stage.order_name)
    if not order.production_path:
        raise ShopFloorCommandError("Order has no production path.")
    target_stage = _next_stage(order.production_path, stage.stage_type)
    return repository.get_users_for_stage(target_stage) if target_stage else []


def dispatch_order(
    repository: ShopFloorCommandPort,
    order_name: str,
    path: str,
    assignee: str,
) -> dict[str, Any]:
    repository.require_dispatch_permission()
    order = repository.get_order_state(order_name)
    assert_order_ready_for_dispatch(order)
    repository.validate_special_shapes(order_name)

    _validate_path(path)
    first_type = first_stage_type(path)
    repository.assert_worker_for_stage(assignee, first_type)
    repository.cancel_non_shop_floor_active_stages(order_name)

    stage = repository.create_stage(
        order_name=order_name,
        stage_type=first_type,
        assignee=assignee,
        sequence=stage_sequence(path, first_type),
    )
    repository.track_order_to_stage(order_name, path=path, stage_name=stage.name)
    repository.log_stage_event(
        stage.name,
        "Created",
        {"path": path, "assignee": assignee, "shop_floor_dispatch": True},
    )
    return {
        "name": order_name,
        "production_path": path,
        "stage": stage.name,
        "status": order_status_for_stage_type(first_type),
        "current_assignee": assignee,
        "department_status": "بحاجة للعمل",
    }


def start_my_stage(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> dict[str, Any]:
    repository.require_stage_access(stage_name)
    stage = repository.get_stage_state(stage_name)
    target_status = _transition(
        stage.status,
        "start",
        "Only a stage that needs work can be started.",
    )
    repository.consume_stock_if_due(
        stage.order_name,
        stage.stage_type,
        "Cutting Start",
    )
    actor = repository.current_user()
    updated = repository.start_stage(
        stage_name,
        actor=actor,
        target_status=target_status,
    )
    repository.log_stage_event(
        stage_name,
        "Start",
        {"assigned_to": updated.assigned_to, "shop_floor": True},
    )
    repository.track_order_to_stage(stage.order_name, stage_name=stage_name)
    return {
        "stage": stage_name,
        "status": updated.status,
        "order_status": repository.get_order_status(stage.order_name),
        "department_status": "قيد العمل",
    }


def handoff_to_next(
    repository: ShopFloorCommandPort,
    stage_name: str,
    next_assignee: str | None = None,
) -> dict[str, Any]:
    repository.require_stage_access(stage_name)
    stage = repository.get_stage_state(stage_name)
    target_status = _transition(
        stage.status,
        "finish",
        "Start the stage before sending it to the next department.",
    )
    order = repository.get_order_state(stage.order_name)
    path = order.production_path
    if not path:
        raise ShopFloorCommandError("Order has no production path.")
    if (
        stage.stage_type == "Drawing"
        and (order.drawing_dxf_status or "None") != "Approved by Drawing"
    ):
        raise ShopFloorCommandError(
            "Approve the production DXF before sending the order to CNC."
        )

    target_stage = _next_stage(path, stage.stage_type)
    actor = repository.current_user()
    if stage.status == "Paused":
        repository.close_open_pause(stage_name, actor)

    completed = repository.complete_stage(
        stage_name,
        actor=actor,
        target_status=target_status,
        completed_qty=repository.required_piece_qty(stage.order_name),
    )
    remnants = repository.register_remnants_if_due(
        stage.order_name,
        stage.stage_type,
    )
    repository.consume_stock_if_due(
        stage.order_name,
        stage.stage_type,
        "Cutting Finish",
    )
    repository.log_stage_event(
        stage_name,
        "Finish",
        {
            "shop_floor": True,
            "handoff": True,
            "next_stage_type": target_stage,
            "remnants": remnants or {},
        },
    )

    if not target_stage:
        repository.track_order_ready_for_delivery(stage.order_name)
        return {
            "stage": stage_name,
            "status": completed.status,
            "order_status": "Ready for Delivery",
            "ready_for_delivery": True,
        }

    if not next_assignee:
        raise ShopFloorCommandError("Select the next worker.")
    repository.assert_worker_for_stage(next_assignee, target_stage)
    next_stage = repository.create_stage(
        order_name=stage.order_name,
        stage_type=target_stage,
        assignee=next_assignee,
        sequence=stage_sequence(path, target_stage),
    )
    repository.track_order_to_stage(stage.order_name, stage_name=next_stage.name)
    repository.log_stage_event(
        next_stage.name,
        "Created",
        {
            "from_stage": stage_name,
            "assignee": next_assignee,
            "shop_floor_handoff": True,
        },
    )
    return {
        "stage": stage_name,
        "status": completed.status,
        "next_stage": next_stage.name,
        "next_stage_type": target_stage,
        "order_status": order_status_for_stage_type(target_stage),
        "ready_for_delivery": False,
    }


def mark_delivered(
    repository: ShopFloorCommandPort,
    order_name: str,
) -> dict[str, Any]:
    repository.require_delivery_permission()
    status = repository.get_order_status(order_name)
    if not can_mark_delivered(status):
        raise ShopFloorCommandError(
            "Only orders ready for delivery can be marked as delivered."
        )
    repository.track_order_delivered(order_name)
    return {"name": order_name, "status": "Delivered"}


def revert_department(
    repository: ShopFloorCommandPort,
    order_name: str,
    target_stage: str | None = None,
    target_stage_type: str | None = None,
) -> dict[str, Any]:
    repository.require_revert_permission()
    order = repository.get_order_state(order_name)
    if order.status == "Delivered":
        raise ShopFloorCommandError("Delivered orders cannot be reverted.")
    if not can_revert_department(
        order.status,
        production_path=order.production_path,
    ):
        raise ShopFloorCommandError("Order is not on the shop-floor path.")

    raw_target = target_stage_type or target_stage
    try:
        stage_type = resolve_shop_floor_stage_type(raw_target)
    except ValueError as error:
        raise ShopFloorCommandError("Select a stage to revert to.") from error

    candidates = repository.list_revert_candidates(order_name, stage_type)
    stage_name = next(
        (row.name for row in candidates if not row.piece_label),
        None,
    )
    if not stage_name and target_stage and repository.stage_exists(target_stage):
        stage_name = target_stage
    if not stage_name:
        raise ShopFloorCommandError(
            f"No shop-floor stage found for {stage_type or target_stage or ''}."
        )

    stage = repository.get_stage_state(stage_name)
    if stage.order_name != order_name:
        raise ShopFloorCommandError("Stage does not belong to this order.")
    if stage.stage_type not in SHOP_FLOOR_STAGE_TYPES:
        raise ShopFloorCommandError("Only shop-floor stages can be reverted to.")

    for later in repository.list_later_stages(order_name, stage.sequence):
        if later.piece_label:
            continue
        cancelled_status = _transition(
            later.status,
            "cancel",
            "Later production stage cannot be cancelled.",
        )
        repository.cancel_stage(later.name, target_status=cancelled_status)
        repository.log_stage_event(
            later.name,
            "Cancel",
            {"reason": "Reverted to earlier stage", "target": stage.stage_type},
        )

    reopened_status = _transition(
        stage.status,
        "reopen",
        "Target production stage cannot be reopened.",
    )
    reopened = repository.reopen_stage(stage.name, target_status=reopened_status)
    repository.log_stage_event(
        reopened.name,
        "Override",
        {"reopened": True, "shop_floor_revert": True},
    )
    repository.track_order_to_stage(order_name, stage_name=reopened.name)
    return {
        "name": order_name,
        "stage": reopened.name,
        "stage_type": reopened.stage_type,
        "status": order_status_for_stage_type(reopened.stage_type),
        "department_status": "بحاجة للعمل",
    }


__all__ = [
    "OrderState",
    "ShopFloorCommandError",
    "ShopFloorCommandPort",
    "ShopFloorPermissionDenied",
    "StageState",
    "assert_order_ready_for_dispatch",
    "dispatch_order",
    "get_handoff_workers",
    "handoff_to_next",
    "mark_delivered",
    "revert_department",
    "start_my_stage",
]
