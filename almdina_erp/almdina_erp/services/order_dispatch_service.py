from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.services import shop_floor_commands
from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role
from almdina_erp.almdina_erp.services.order_revision_activation import (
    assert_order_revision_dispatchable,
)


def _lock_and_validate(order_name: str) -> Any:
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    assert_order_revision_dispatchable(order)
    return order


@frappe.whitelist()
def dispatch_order(order_name: str, path: str, assignee: str) -> dict[str, Any]:
    """Serialize dispatch against revision activation and reject stale revisions."""

    _lock_and_validate(order_name)
    return shop_floor_commands.dispatch_order(order_name, path, assignee)


@frappe.whitelist()
def validate_order_for_dispatch(order_name: str) -> dict[str, Any]:
    """Backward-compatible pre-dispatch validation used by the legacy API."""

    require_any_role("Order Entry", "Production Manager")
    order = _lock_and_validate(order_name)
    order.check_permission("write")
    shop_floor_commands.assert_order_ready_for_dispatch(order)
    return {
        "name": order.name,
        "status": order.status,
        "revision_state": getattr(order, "revision_state", None) or "Current",
        "ready_for_dispatch": True,
    }
