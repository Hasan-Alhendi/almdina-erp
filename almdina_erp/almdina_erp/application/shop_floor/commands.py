from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Sequence

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    next_stage_type,
    order_status_for_stage_type,
    production_path_sequence,
    resolve_shop_floor_stage_type,
    transition_stage,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute
from almdina_erp.almdina_erp.domain.security.authorization import Capability


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
    has_approved_plan: bool = False
    drawing_dxf_status: str | None = None


@dataclass(frozen=True, slots=True)
class StageState:
    name: str
    order_name: str
    stage_type: str
    status: str
    assigned_to: str | None
    sequence: int
    department_label: str | None = None
    operational_role: str | None = None
    start_time: datetime | None = None
    paused_seconds: int = 0
    piece_label: str | None = None


class ShopFloorCommandPort(Protocol):
    def current_user(self) -> str: ...

    def capabilities_for_order(self, order_name: str) -> frozenset[str]: ...

    def lock_order(self, order_name: str) -> None: ...

    def lock_stage(self, stage_name: str) -> None: ...

    def get_order_state(self, order_name: str) -> OrderState: ...

    def get_stage_state(self, stage_name: str) -> StageState: ...

    def validate_special_shapes(self, order_name: str) -> None: ...

    def get_production_route(self, route_name: str) -> ProductionRoute: ...

    def assert_worker_for_role(self, user: str, role: str) -> None: ...

    def get_users_for_role(self, role: str) -> list[dict[str, str]]: ...

    def cancel_active_order_stages(self, order_name: str) -> None: ...

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
        department_label: str | None = None,
        operational_role: str | None = None,
    ) -> StageState: ...

    def reassign_stage(self, stage_name: str, *, assignee: str) -> StageState: ...

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
    """Legacy path helper retained only for compatibility callers."""

    try:
        return next_stage_type(path, stage_type)
    except ValueError as error:
        raise ShopFloorCommandError(
            f"المرحلة {stage_type} ليست ضمن المسار {path}."
        ) from error


def _validate_path(path: str) -> None:
    """Legacy path helper retained only for compatibility callers."""

    try:
        production_path_sequence(path)
    except ValueError as error:
        raise ShopFloorCommandError(f"مسار الإنتاج غير صالح: {path}") from error


def _production_route(
    repository: ShopFloorCommandPort,
    route_name: str,
) -> ProductionRoute:
    try:
        return repository.get_production_route(route_name)
    except ValueError as error:
        raise ShopFloorCommandError(str(error)) from error


def _locked_order(
    repository: ShopFloorCommandPort,
    order_name: str,
) -> OrderState:
    repository.lock_order(order_name)
    return repository.get_order_state(order_name)


def _locked_stage_scope(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> tuple[StageState, OrderState]:
    """Lock mutations in a stable order: order row first, then stage row.

    The preliminary stage read is used only to resolve its immutable parent order.
    All authorization and state decisions use the post-lock snapshots.
    """

    probe = repository.get_stage_state(stage_name)
    repository.lock_order(probe.order_name)
    repository.lock_stage(stage_name)
    stage = repository.get_stage_state(stage_name)
    if stage.order_name != probe.order_name:
        raise ShopFloorCommandError("تغيّر ارتباط المرحلة بالطلب أثناء التنفيذ. أعد المحاولة.")
    order = repository.get_order_state(stage.order_name)
    return stage, order


def _facts(
    order: OrderState,
    *,
    stage: StageState | None = None,
    actor: str | None = None,
) -> ProductionActionFacts:
    return ProductionActionFacts(
        order_status=order.status,
        production_path=order.production_path,
        current_stage_name=order.current_stage,
        has_cutting_plan=order.has_cutting_plan,
        plan_needs_recalculation=order.plan_needs_recalculation,
        stage_name=stage.name if stage else None,
        stage_type=stage.stage_type if stage else None,
        stage_status=stage.status if stage else None,
        assigned_to=stage.assigned_to if stage else None,
        actor=actor,
        drawing_dxf_status=order.drawing_dxf_status,
    )


def _assert_action_allowed(
    repository: ShopFloorCommandPort,
    action: str,
    order: OrderState,
    *,
    stage: StageState | None = None,
    actor: str | None = None,
) -> None:
    decision = decide_production_action(
        action,
        capabilities=repository.capabilities_for_order(order.name),
        facts=_facts(order, stage=stage, actor=actor),
    )
    if decision.allowed:
        return
    if decision.code == "missing_capability":
        raise ShopFloorPermissionDenied(decision.reason)
    raise ShopFloorCommandError(decision.reason)


def _assert_route_dispatch_gate(route: ProductionRoute, order: OrderState) -> None:
    if route.requires_approved_plan_before_dispatch and not order.has_approved_plan:
        raise ShopFloorCommandError(
            "يجب اعتماد خطة القص قبل إرسال الطلب إلى مسار يبدأ بالتنفيذ الفعلي."
        )


def _assert_planning_handoff_gate(
    route: ProductionRoute,
    stage: StageState,
    order: OrderState,
) -> None:
    try:
        route_stage = route.stage(stage.stage_type)
    except ValueError as error:
        raise ShopFloorCommandError(str(error)) from error
    if not route_stage.is_planning_stage:
        return
    if not order.has_approved_plan:
        raise ShopFloorCommandError(
            "اعتمد خطة القص بعد مراجعتها قبل تسليم مرحلة التخطيط إلى القسم التالي."
        )
    if order.plan_needs_recalculation:
        raise ShopFloorCommandError(
            "خطة القص تغيّرت وتحتاج إلى إعادة حساب واعتماد جديد قبل مغادرة مرحلة التخطيط."
        )


def assert_order_ready_for_dispatch(order: OrderState) -> None:
    """Compatibility validator that evaluates generic state only.

    Route-specific approval requirements are enforced by ``dispatch_order`` after
    loading the selected configurable route.
    """

    decision = decide_production_action(
        Capability.DISPATCH_ORDER,
        capabilities={Capability.DISPATCH_ORDER},
        facts=_facts(order),
    )
    if not decision.allowed:
        raise ShopFloorCommandError(decision.reason)


def get_handoff_context(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> dict[str, Any]:
    stage = repository.get_stage_state(stage_name)
    order = repository.get_order_state(stage.order_name)
    _assert_action_allowed(
        repository,
        Capability.HANDOFF_ASSIGNED_STAGE,
        order,
        stage=stage,
        actor=repository.current_user(),
    )
    if not order.production_path:
        raise ShopFloorCommandError("الطلب لا يحتوي على مسار إنتاج.")
    route = _production_route(repository, order.production_path)
    _assert_planning_handoff_gate(route, stage, order)
    try:
        target_stage = route.next_stage(stage.stage_type)
    except ValueError as error:
        raise ShopFloorCommandError(str(error)) from error
    if not target_stage:
        return {
            "final_stage": True,
            "next_stage_type": None,
            "next_department": None,
            "operational_role": None,
            "workers": [],
        }
    return {
        "final_stage": False,
        "next_stage_type": target_stage.stage_type,
        "next_department": target_stage.department_label,
        "operational_role": target_stage.operational_role,
        "workers": repository.get_users_for_role(target_stage.operational_role),
    }


def get_handoff_workers(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> list[dict[str, str]]:
    return list(get_handoff_context(repository, stage_name)["workers"])


def get_reassignment_workers(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> list[dict[str, str]]:
    stage = repository.get_stage_state(stage_name)
    order = repository.get_order_state(stage.order_name)
    _assert_action_allowed(
        repository,
        Capability.REASSIGN_WORKER,
        order,
        stage=stage,
        actor=repository.current_user(),
    )
    role = stage.operational_role
    if not role:
        route = _production_route(repository, order.production_path or "")
        role = route.stage(stage.stage_type).operational_role
    return repository.get_users_for_role(role)


def dispatch_order(
    repository: ShopFloorCommandPort,
    order_name: str,
    path: str,
    assignee: str,
) -> dict[str, Any]:
    order = _locked_order(repository, order_name)
    _assert_action_allowed(repository, Capability.DISPATCH_ORDER, order)
    repository.validate_special_shapes(order_name)

    route = _production_route(repository, path)
    _assert_route_dispatch_gate(route, order)
    first = route.first_stage
    repository.assert_worker_for_role(assignee, first.operational_role)
    repository.cancel_active_order_stages(order_name)

    stage = repository.create_stage(
        order_name=order_name,
        stage_type=first.stage_type,
        assignee=assignee,
        sequence=first.sequence,
        department_label=first.department_label,
        operational_role=first.operational_role,
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
        "status": order_status_for_stage_type(first.stage_type),
        "department": first.department_label,
        "current_assignee": assignee,
        "department_status": "بحاجة للعمل",
    }


def start_my_stage(
    repository: ShopFloorCommandPort,
    stage_name: str,
) -> dict[str, Any]:
    stage, order = _locked_stage_scope(repository, stage_name)
    actor = repository.current_user()
    _assert_action_allowed(
        repository,
        Capability.START_ASSIGNED_STAGE,
        order,
        stage=stage,
        actor=actor,
    )
    target_status = _transition(
        stage.status,
        "start",
        "يمكن بدء المرحلة فقط عندما تكون بحالة بحاجة للعمل.",
    )
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
    stage, order = _locked_stage_scope(repository, stage_name)
    actor = repository.current_user()
    _assert_action_allowed(
        repository,
        Capability.HANDOFF_ASSIGNED_STAGE,
        order,
        stage=stage,
        actor=actor,
    )
    target_status = _transition(
        stage.status,
        "finish",
        "ابدأ المرحلة أولًا قبل تسليمها إلى القسم التالي.",
    )
    path = order.production_path
    if not path:
        raise ShopFloorCommandError("الطلب لا يحتوي على مسار إنتاج.")

    route = _production_route(repository, path)
    _assert_planning_handoff_gate(route, stage, order)
    try:
        target_stage = route.next_stage(stage.stage_type)
    except ValueError as error:
        raise ShopFloorCommandError(str(error)) from error
    if target_stage:
        if not next_assignee:
            raise ShopFloorCommandError("اختر العامل الذي سيستلم المرحلة التالية.")
        repository.assert_worker_for_role(
            next_assignee,
            target_stage.operational_role,
        )
    if stage.status == "Paused":
        repository.close_open_pause(stage_name, actor)

    completed = repository.complete_stage(
        stage_name,
        actor=actor,
        target_status=target_status,
        completed_qty=repository.required_piece_qty(stage.order_name),
    )
    repository.log_stage_event(
        stage_name,
        "Finish",
        {
            "shop_floor": True,
            "handoff": True,
            "next_stage_type": target_stage.stage_type if target_stage else None,
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

    next_stage = repository.create_stage(
        order_name=stage.order_name,
        stage_type=target_stage.stage_type,
        assignee=next_assignee,
        sequence=target_stage.sequence,
        department_label=target_stage.department_label,
        operational_role=target_stage.operational_role,
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
        "next_stage_type": target_stage.stage_type,
        "next_department": target_stage.department_label,
        "order_status": order_status_for_stage_type(target_stage.stage_type),
        "ready_for_delivery": False,
    }


def reassign_worker(
    repository: ShopFloorCommandPort,
    stage_name: str,
    assignee: str,
) -> dict[str, Any]:
    stage, order = _locked_stage_scope(repository, stage_name)
    _assert_action_allowed(
        repository,
        Capability.REASSIGN_WORKER,
        order,
        stage=stage,
        actor=repository.current_user(),
    )
    role = stage.operational_role
    if not role:
        route = _production_route(repository, order.production_path or "")
        role = route.stage(stage.stage_type).operational_role
    repository.assert_worker_for_role(assignee, role)
    if assignee == stage.assigned_to:
        return {
            "stage": stage.name,
            "order_name": stage.order_name,
            "assigned_to": assignee,
            "changed": False,
        }

    previous_assignee = stage.assigned_to
    updated = repository.reassign_stage(stage.name, assignee=assignee)
    repository.track_order_to_stage(stage.order_name, stage_name=stage.name)
    repository.log_stage_event(
        stage.name,
        "Override",
        {
            "shop_floor_reassignment": True,
            "previous_assignee": previous_assignee,
            "assignee": assignee,
            "reassigned_by": repository.current_user(),
        },
    )
    return {
        "stage": updated.name,
        "order_name": updated.order_name,
        "assigned_to": updated.assigned_to,
        "changed": True,
    }


def mark_delivered(
    repository: ShopFloorCommandPort,
    order_name: str,
) -> dict[str, Any]:
    order = _locked_order(repository, order_name)
    _assert_action_allowed(repository, Capability.MARK_DELIVERED, order)
    repository.track_order_delivered(order_name)
    return {"name": order_name, "status": "Delivered"}


def revert_department(
    repository: ShopFloorCommandPort,
    order_name: str,
    target_stage: str | None = None,
    target_stage_type: str | None = None,
) -> dict[str, Any]:
    order = _locked_order(repository, order_name)
    _assert_action_allowed(repository, Capability.REVERT_DEPARTMENT, order)

    raw_target = target_stage_type or target_stage
    try:
        stage_type = resolve_shop_floor_stage_type(raw_target)
    except ValueError as error:
        raise ShopFloorCommandError("اختر مرحلة إنتاج للرجوع إليها.") from error

    candidates = repository.list_revert_candidates(order_name, stage_type)
    stage_name = next(
        (row.name for row in candidates if not row.piece_label),
        None,
    )
    if not stage_name and target_stage and repository.stage_exists(target_stage):
        stage_name = target_stage
    if not stage_name:
        raise ShopFloorCommandError(
            f"لا توجد مرحلة إنتاج محفوظة من النوع {stage_type or target_stage or ''} لهذا الطلب."
        )

    repository.lock_stage(stage_name)
    stage = repository.get_stage_state(stage_name)
    if stage.order_name != order_name:
        raise ShopFloorCommandError("المرحلة المحددة لا تتبع هذا الطلب.")
    route = _production_route(repository, order.production_path or "")
    if not route.contains(stage.stage_type):
        raise ShopFloorCommandError("يمكن الرجوع فقط إلى مرحلة موجودة في مسار الإنتاج المحدد.")

    later_stages = [
        later
        for later in repository.list_later_stages(order_name, stage.sequence)
        if not later.piece_label
    ]
    for later in later_stages:
        repository.lock_stage(later.name)
    for later in later_stages:
        later = repository.get_stage_state(later.name)
        cancelled_status = _transition(
            later.status,
            "cancel",
            "تعذر إلغاء إحدى المراحل اللاحقة أثناء الرجوع.",
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
        "تعذر إعادة فتح مرحلة الإنتاج المحددة.",
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
    "get_handoff_context",
    "get_handoff_workers",
    "get_reassignment_workers",
    "handoff_to_next",
    "mark_delivered",
    "reassign_worker",
    "revert_department",
    "start_my_stage",
]
