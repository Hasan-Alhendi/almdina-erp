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


def assert_order_ready_for_dispatch(order: Any) -> None:
    """Compatibility validator used by the revision-aware dispatch endpoint."""

    state = commands.OrderState(
        name=str(order.name),
        status=str(order.status or ""),
        production_path=order.production_path or None,
        current_stage=order.current_production_stage or None,
        has_cutting_plan=bool(order.cutting_plan_json),
        plan_needs_recalculation=bool(order.plan_needs_recalculation),
        drawing_dxf_status=order.drawing_dxf_status or None,
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
def dispatch_order(order_name: str, path: str, assignee: str) -> dict[str, Any]:
    return _execute(commands.dispatch_order, order_name, path, assignee)


@frappe.whitelist()
def start_my_stage(stage_name: str) -> dict[str, Any]:
    return _execute(commands.start_my_stage, stage_name)


@frappe.whitelist()
def handoff_to_next(
    stage_name: str,
    next_assignee: str | None = None,
) -> dict[str, Any]:
    return _execute(commands.handoff_to_next, stage_name, next_assignee)


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
def return_order_to_draft(order_name: str) -> dict[str, Any]:
    """Compatibility endpoint: immutable orders create controlled revisions."""

    from almdina_erp.almdina_erp.services.order_revision_service import (
        create_order_revision,
    )

    return create_order_revision(
        order_name,
        reason=_("Legacy return-to-draft request converted to a controlled revision."),
    )


# Private compatibility aliases retained for older Python callers and tests.
_transition = commands._transition
_next_stage = commands._next_stage
_validate_path = commands._validate_path


__all__ = [
    "assert_order_ready_for_dispatch",
    "dispatch_order",
    "get_handoff_workers",
    "handoff_to_next",
    "mark_delivered",
    "return_order_to_draft",
    "revert_department",
    "start_my_stage",
]
