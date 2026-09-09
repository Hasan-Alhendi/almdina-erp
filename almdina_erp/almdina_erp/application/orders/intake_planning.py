from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.intake_lifecycle import (
    DATA_ENTRY,
    READY_TO_DISPATCH,
    IntakeFacts,
    IntakeLifecycleError,
    IntakePermissionError,
    assert_pending_dispatch_editable,
    should_initialize_data_entry,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute


class IntakePlanningPort(Protocol):
    def current_user(self) -> str: ...

    def is_admin(self) -> bool: ...

    def can_edit_order(self, order: Any) -> bool: ...

    def get_order(self, order_name: str, *, for_update: bool = False) -> Any: ...

    def list_orders_without_intake_stage(self) -> Sequence[Any]: ...

    def get_route(self, route_name: str) -> ProductionRoute: ...

    def list_active_routes(self) -> Sequence[ProductionRoute]: ...

    def assert_assignee_qualified(self, user: str, operational_role: str) -> None: ...

    def list_workers_for_role(self, operational_role: str) -> list[dict[str, str]]: ...

    def initialize_data_entry(
        self,
        order: Any,
        *,
        assignee: str,
        workflow_stage: str,
    ) -> None: ...

    def save_pending_dispatch_plan(
        self,
        order: Any,
        *,
        route_name: str,
        assignee: str,
        workflow_stage: str,
        planned_by: str,
    ) -> None: ...


def _value(row: Any, fieldname: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname, default)
    return getattr(row, fieldname, default)


def _facts(order: Any) -> IntakeFacts:
    return IntakeFacts(
        workflow_stage=str(_value(order, "workflow_stage") or "").strip(),
        production_path=str(_value(order, "production_path") or "").strip(),
        current_production_stage=str(
            _value(order, "current_production_stage") or ""
        ).strip(),
        current_assignee=str(_value(order, "current_assignee") or "").strip(),
        owner=str(_value(order, "owner") or "").strip(),
    )


def initialize_data_entry(repository: IntakePlanningPort, order: Any) -> bool:
    """Initialize DATA_ENTRY once, after the order exists on the server."""

    facts = _facts(order)
    if not should_initialize_data_entry(facts):
        return False
    owner = facts.owner
    if not owner:
        raise IntakeLifecycleError("تعذر تحديد مدخل البيانات الذي أنشأ الطلب.")
    repository.initialize_data_entry(
        order,
        assignee=owner,
        workflow_stage=DATA_ENTRY,
    )
    return True


def backfill_data_entry(repository: IntakePlanningPort) -> int:
    """Backfill DATA_ENTRY for persisted legacy orders that never entered production.

    The repository only narrows candidates to rows with no intake stage. Domain facts
    remain the final eligibility gate, so repeated migrations and historical rows that
    already entered production are both safe.
    """

    initialized = 0
    for order in repository.list_orders_without_intake_stage():
        if initialize_data_entry(repository, order):
            initialized += 1
    return initialized


def _assert_edit_access(repository: IntakePlanningPort, order: Any) -> None:
    if repository.can_edit_order(order):
        return
    raise IntakePermissionError("لا تملك صلاحية إنهاء إدخال بيانات هذا الطلب.")


def _route_projection(route: ProductionRoute) -> dict[str, Any]:
    return {
        "value": route.name,
        "label": route.label,
        "stage_count": len(route.stages),
        "operational_role": route.first_stage.operational_role,
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
    }


def get_finish_data_entry_options(
    repository: IntakePlanningPort,
    order_name: str,
) -> dict[str, Any]:
    order = repository.get_order(order_name)
    _assert_edit_access(repository, order)
    assert_pending_dispatch_editable(
        _facts(order),
        actor=repository.current_user(),
        is_admin=repository.is_admin(),
    )

    routes = list(repository.list_active_routes())
    if not routes:
        raise IntakeLifecycleError(
            "أنشئ مسار إنتاج وفعّله قبل إنهاء إدخال البيانات."
        )

    planned_route = str(_value(order, "planned_production_route") or "").strip()
    available_names = {route.name for route in routes}
    default_route = planned_route if planned_route in available_names else routes[0].name
    return {
        "workflow_stage": str(_value(order, "workflow_stage") or ""),
        "default_route": default_route,
        "planned_first_assignee": str(
            _value(order, "planned_first_assignee") or ""
        ),
        "routes": [_route_projection(route) for route in routes],
        "workers": {
            route.name: repository.list_workers_for_role(
                route.first_stage.operational_role
            )
            for route in routes
        },
    }


def finish_data_entry(
    repository: IntakePlanningPort,
    order_name: str,
    route_name: str,
    assignee: str,
) -> dict[str, Any]:
    """Persist a pending dispatch plan without starting production."""

    order = repository.get_order(order_name, for_update=True)
    _assert_edit_access(repository, order)
    facts = _facts(order)
    assert_pending_dispatch_editable(
        facts,
        actor=repository.current_user(),
        is_admin=repository.is_admin(),
    )

    resolved_route = str(route_name or "").strip()
    resolved_assignee = str(assignee or "").strip()
    if not resolved_route:
        raise IntakeLifecycleError("اختر مسار الإنتاج.")
    if not resolved_assignee:
        raise IntakeLifecycleError("اختر العامل الذي سيستلم أول مرحلة.")

    route = repository.get_route(resolved_route)
    repository.assert_assignee_qualified(
        resolved_assignee,
        route.first_stage.operational_role,
    )
    actor = repository.current_user()
    repository.save_pending_dispatch_plan(
        order,
        route_name=route.name,
        assignee=resolved_assignee,
        workflow_stage=READY_TO_DISPATCH,
        planned_by=actor,
    )
    return {
        "order_name": str(_value(order, "name") or order_name),
        "workflow_stage": READY_TO_DISPATCH,
        "planned_production_route": route.name,
        "planned_first_assignee": resolved_assignee,
        "current_assignee": facts.current_assignee,
        "production_path": facts.production_path or None,
        "current_production_stage": facts.current_production_stage or None,
    }


__all__ = [
    "IntakePlanningPort",
    "backfill_data_entry",
    "finish_data_entry",
    "get_finish_data_entry_options",
    "initialize_data_entry",
]
