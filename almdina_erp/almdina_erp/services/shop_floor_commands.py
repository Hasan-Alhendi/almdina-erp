from __future__ import annotations

from typing import Any, Callable, TypeVar

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.shop_floor import commands
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_command_repository import (
    FrappeShopFloorCommandRepository,
)


_Result = TypeVar("_Result")
_repository = FrappeShopFloorCommandRepository()


def _execute(function: Callable[..., _Result], *args: Any, **kwargs: Any) -> _Result:
    try:
        return function(_repository, *args, **kwargs)
    except commands.ShopFloorPermissionDenied as error:
        frappe.throw(_(str(error)), frappe.PermissionError)
    except commands.ShopFloorCommandError as error:
        frappe.throw(_(str(error)))
    raise AssertionError("frappe.throw must interrupt execution")


def _production_plan_facts(order: Any) -> Any:
    from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
        production_plan_facts,
    )
    return production_plan_facts(order)


def assert_order_ready_for_dispatch(order: Any) -> None:
    """Compatibility facade over canonical Cutting Plan runtime facts."""
    plan = _production_plan_facts(order)
    state = commands.OrderState(
        name=str(order.name),
        status=str(getattr(order, "status", None) or ""),
        production_path=getattr(order, "production_path", None) or None,
        current_stage=getattr(order, "current_production_stage", None) or None,
        has_cutting_plan=plan.has_cutting_plan,
        plan_needs_recalculation=plan.plan_needs_recalculation,
        has_approved_plan=plan.has_approved_plan,
        drawing_dxf_status=getattr(order, "drawing_dxf_status", None) or None,
        has_factory_work=bool(getattr(plan, "has_factory_work", True)),
    )
    try:
        commands.assert_order_ready_for_dispatch(state)
    except commands.ShopFloorCommandError as error:
        frappe.throw(_(str(error)))
    order.ensure_special_shapes_documented()


@frappe.whitelist()
def get_handoff_workers(stage_name: str) -> list[dict[str, str]]:
    return _execute(commands.get_handoff_workers, stage_name)


@frappe.whitelist()
def get_handoff_context(stage_name: str) -> dict[str, Any]:
    return _execute(commands.get_handoff_context, stage_name)


@frappe.whitelist()
def dispatch_order(order_name: str, path: str, assignee: str) -> dict[str, Any]:
    return _execute(commands.dispatch_order, order_name, path, assignee)


@frappe.whitelist()
def start_my_stage(stage_name: str) -> dict[str, Any]:
    return _execute(commands.start_my_stage, stage_name)


def _stage_completion_whatsapp_context(stage_name: str) -> dict[str, str] | None:
    name = str(stage_name or "").strip()
    if not name:
        return None
    row = frappe.db.get_value(
        "Production Stage",
        name,
        ["door_cutting_order", "stage_type"],
        as_dict=True,
    )
    if not row:
        return None
    order_name = str(row.door_cutting_order or "").strip()
    stage_type = str(row.stage_type or "").strip()
    path = frappe.db.get_value("Door Cutting Order", order_name, "production_path")
    if not order_name or not stage_type or not path:
        return None
    from almdina_erp.almdina_erp.infrastructure.frappe.production_routing_repository import (
        get_route,
    )

    try:
        stage = get_route(str(path)).stage(stage_type)
    except ValueError:
        return None
    if not stage.notify_whatsapp_on_complete:
        return None
    return {
        "order_name": order_name,
        "stage_type": stage.stage_type,
        "stage_label": stage.department_label,
    }


@frappe.whitelist()
def handoff_to_next(
    stage_name: str,
    next_assignee: str | None = None,
) -> dict[str, Any]:
    notify = _stage_completion_whatsapp_context(stage_name)
    result = _execute(commands.handoff_to_next, stage_name, next_assignee)
    if not notify:
        return result
    from almdina_erp.almdina_erp.services.whatsapp_service import notify_stage_completion

    payload = dict(result or {})
    payload["whatsapp"] = notify_stage_completion(
        notify["order_name"],
        notify["stage_type"],
        notify["stage_label"],
    )
    return payload


@frappe.whitelist()
def reassign_worker(stage_name: str, assignee: str) -> dict[str, Any]:
    return _execute(commands.reassign_worker, stage_name, assignee)


@frappe.whitelist()
def mark_delivered(order_name: str) -> dict[str, Any]:
    return _execute(commands.mark_delivered, order_name)


@frappe.whitelist()
def revert_department(
    order_name: str,
    target_stage: str | None = None,
    target_stage_type: str | None = None,
) -> dict[str, Any]:
    return _execute(
        commands.revert_department,
        order_name,
        target_stage,
        target_stage_type,
    )


@frappe.whitelist()
def return_order_to_draft(order_name: str, reason: str | None = None) -> dict[str, Any]:
    """Compatibility endpoint for the in-place lifecycle return-to-draft action."""
    from almdina_erp.almdina_erp.services.order_revision_service import (
        return_order_to_draft as reset_same_order,
    )
    return reset_same_order(order_name, reason=reason)


_transition = commands._transition
_next_stage = commands._next_stage
_validate_path = commands._validate_path


__all__ = [
    "assert_order_ready_for_dispatch",
    "dispatch_order",
    "get_handoff_context",
    "get_handoff_workers",
    "handoff_to_next",
    "mark_delivered",
    "reassign_worker",
    "return_order_to_draft",
    "revert_department",
    "start_my_stage",
]
