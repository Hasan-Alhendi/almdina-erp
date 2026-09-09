from __future__ import annotations

from typing import Any, Callable, TypeVar

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.shop_floor.planned_dispatch import (
    PlannedDispatchError,
    PlannedDispatchPermissionDenied,
    dispatch_planned_order as dispatch_planned_order_use_case,
    get_planned_dispatch_context as get_planned_dispatch_context_use_case,
)
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_command_repository import (
    FrappeShopFloorCommandRepository,
)


_Result = TypeVar("_Result")
_repository = FrappeShopFloorCommandRepository()


def _execute(function: Callable[..., _Result], *args: Any) -> _Result:
    try:
        return function(_repository, *args)
    except PlannedDispatchPermissionDenied as error:
        frappe.throw(_(str(error)), frappe.PermissionError)
    except (PlannedDispatchError, ValueError) as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def get_planned_dispatch_context(order_name: str) -> dict[str, Any]:
    """Return the persisted READY_TO_DISPATCH plan for read-only presentation."""

    return _execute(get_planned_dispatch_context_use_case, order_name)


@frappe.whitelist()
def dispatch_planned_order(order_name: str) -> dict[str, Any]:
    """Start production from the persisted server-side dispatch plan only."""

    return _execute(dispatch_planned_order_use_case, order_name)


__all__ = [
    "dispatch_planned_order",
    "get_planned_dispatch_context",
]
