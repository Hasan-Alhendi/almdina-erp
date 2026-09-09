from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.intake_lifecycle import (
    IntakeFacts,
    IntakeLifecycleError,
    IntakePermissionError,
    assert_ready_to_dispatch,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    department_status_for_stage_status,
    order_status_for_stage_type,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class PlannedDispatchError(ValueError):
    """Raised when the persisted dispatch plan cannot start production safely."""


class PlannedDispatchPermissionDenied(PermissionError):
    """Raised when the current actor cannot start the persisted dispatch plan."""


@dataclass(frozen=True, slots=True)
class PlannedDispatchOrderState:
    name: str
    status: str
    workflow_stage: str
    production_path: str | None
    current_stage: str | None
    current_assignee: str | None
    owner: str | None
    planned_route: str | None
    planned_assignee: str | None
    has_cutting_plan: bool
    plan_needs_recalculation: bool
    drawing_dxf_status: str | None = None


class PlannedDispatchPort(Protocol):
    def current_user(self) -> str: ...

    def is_admin(self, user: str | None = None) -> bool: ...

    def capabilities_for_order(self, order_name: str) -> frozenset[str]: ...

    def lock_order(self, order_name: str) -> None: ...

    def get_planned_dispatch_order(self, order_name: str) -> PlannedDispatchOrderState: ...

    def get_production_route(self, route_name: str) -> ProductionRoute: ...

    def assert_worker_for_role(self, user: str, role: str) -> None: ...

    def validate_special_shapes(self, order_name: str) -> None: ...

    def has_active_order_stage(self, order_name: str) -> bool: ...

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
        department_label: str | None = None,
        operational_role: str | None = None,
    ) -> Any: ...

    def activate_planned_dispatch(
        self,
        order_name: str,
        *,
        path: str,
        stage_name: str,
    ) -> None: ...

    def log_stage_event(
        self,
        stage_name: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None: ...


def _intake_facts(order: PlannedDispatchOrderState) -> IntakeFacts:
    return IntakeFacts(
        workflow_stage=str(order.workflow_stage or "").strip(),
        production_path=str(order.production_path or "").strip(),
        current_production_stage=str(order.current_stage or "").strip(),
        current_assignee=str(order.current_assignee or "").strip(),
        owner=str(order.owner or "").strip(),
    )


def _assert_intake_boundary(
    repository: PlannedDispatchPort,
    order: PlannedDispatchOrderState,
) -> None:
    actor = repository.current_user()
    try:
        assert_ready_to_dispatch(
            _intake_facts(order),
            actor=actor,
            is_admin=repository.is_admin(actor),
        )
    except IntakePermissionError as error:
        raise PlannedDispatchPermissionDenied(str(error)) from error
    except IntakeLifecycleError as error:
        raise PlannedDispatchError(str(error)) from error


def _route(repository: PlannedDispatchPort, route_name: str) -> ProductionRoute:
    try:
        return repository.get_production_route(route_name)
    except ValueError as error:
        raise PlannedDispatchError(str(error)) from error


def _assert_dispatch_authorized(
    repository: PlannedDispatchPort,
    order: PlannedDispatchOrderState,
    route: ProductionRoute,
) -> None:
    decision = decide_production_action(
        Capability.DISPATCH_ORDER,
        capabilities=repository.capabilities_for_order(order.name),
        facts=ProductionActionFacts(
            order_status=order.status,
            production_path=order.production_path,
            current_stage_name=order.current_stage,
            has_cutting_plan=order.has_cutting_plan,
            plan_needs_recalculation=order.plan_needs_recalculation,
            route_starts_with_planning=route.starts_with_planning,
            drawing_dxf_status=order.drawing_dxf_status,
        ),
    )
    if decision.allowed:
        return
    if decision.code == "missing_capability":
        raise PlannedDispatchPermissionDenied(decision.reason)
    raise PlannedDispatchError(decision.reason)


def _persisted_plan(order: PlannedDispatchOrderState) -> tuple[str, str]:
    route_name = str(order.planned_route or "").strip()
    assignee = str(order.planned_assignee or "").strip()
    if not route_name:
        raise PlannedDispatchError("لا توجد خطة إرسال محفوظة لمسار الإنتاج.")
    if not assignee:
        raise PlannedDispatchError("لا يوجد عامل أول محفوظ في خطة الإرسال.")
    return route_name, assignee


def _route_projection(route: ProductionRoute) -> dict[str, Any]:
    return {
        "value": route.name,
        "label": route.label,
        "stages": [
            {
                "sequence": stage.sequence,
                "stage_type": stage.stage_type,
                "department": stage.department_label,
                "operational_role": stage.operational_role,
                "is_planning_stage": stage.is_planning_stage,
            }
            for stage in route.stages
        ],
        "first_stage": {
            "stage_type": route.first_stage.stage_type,
            "department": route.first_stage.department_label,
            "operational_role": route.first_stage.operational_role,
            "sequence": route.first_stage.sequence,
        },
    }


def get_planned_dispatch_context(
    repository: PlannedDispatchPort,
    order_name: str,
) -> dict[str, Any]:
    """Return the persisted plan for read-only READY_TO_DISPATCH presentation."""

    order = repository.get_planned_dispatch_order(order_name)
    _assert_intake_boundary(repository, order)
    route_name, assignee = _persisted_plan(order)
    route = _route(repository, route_name)
    return {
        "order_name": order.name,
        "workflow_stage": order.workflow_stage,
        "planned_production_route": route.name,
        "planned_first_assignee": assignee,
        "route": _route_projection(route),
    }


def dispatch_planned_order(
    repository: PlannedDispatchPort,
    order_name: str,
) -> dict[str, Any]:
    """Atomically convert the persisted intake plan into real production work.

    The order row lock is acquired before any mutation decision. Frappe's request
    transaction owns commit/rollback; this use case deliberately performs no manual
    commit so stage creation, order tracking and audit remain one transaction.
    """

    repository.lock_order(order_name)
    order = repository.get_planned_dispatch_order(order_name)
    _assert_intake_boundary(repository, order)

    route_name, assignee = _persisted_plan(order)
    route = _route(repository, route_name)
    _assert_dispatch_authorized(repository, order, route)

    if repository.has_active_order_stage(order.name):
        raise PlannedDispatchError(
            "يوجد سجل إنتاج نشط غير متوافق مع حالة الطلب. لا يمكن الإرسال قبل معالجة التعارض."
        )

    try:
        repository.validate_special_shapes(order.name)
    except ValueError as error:
        raise PlannedDispatchError(str(error)) from error

    first = route.first_stage
    try:
        repository.assert_worker_for_role(assignee, first.operational_role)
    except ValueError as error:
        raise PlannedDispatchError(str(error)) from error

    # The order row remains locked. A second compliant dispatch waits, then re-reads
    # the post-commit state and fails the exact READY_TO_DISPATCH boundary above.
    if repository.has_active_order_stage(order.name):
        raise PlannedDispatchError(
            "يوجد سجل إنتاج نشط غير متوافق مع حالة الطلب. لا يمكن الإرسال قبل معالجة التعارض."
        )

    stage = repository.create_stage(
        order_name=order.name,
        stage_type=first.stage_type,
        assignee=assignee,
        sequence=first.sequence,
        department_label=first.department_label,
        operational_role=first.operational_role,
    )
    repository.activate_planned_dispatch(
        order.name,
        path=route.name,
        stage_name=str(stage.name),
    )
    repository.log_stage_event(
        str(stage.name),
        "Created",
        {
            "planned_dispatch": True,
            "dispatch_actor": repository.current_user(),
            "path": route.name,
            "first_stage_type": first.stage_type,
            "assignee": assignee,
        },
    )
    return {
        "name": order.name,
        "workflow_stage": None,
        "production_path": route.name,
        "stage": str(stage.name),
        "status": order_status_for_stage_type(first.stage_type),
        "department": first.department_label,
        "current_assignee": assignee,
        "department_status": department_status_for_stage_status(str(stage.status)),
    }


__all__ = [
    "PlannedDispatchError",
    "PlannedDispatchOrderState",
    "PlannedDispatchPermissionDenied",
    "PlannedDispatchPort",
    "dispatch_planned_order",
    "get_planned_dispatch_context",
]
