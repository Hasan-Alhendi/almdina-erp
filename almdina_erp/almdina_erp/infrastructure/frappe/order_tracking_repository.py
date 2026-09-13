from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    physical_execution_projection_from_snapshot,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    LOCKED_ORDER_STATUSES,
    department_for_stage_type,
    department_status_for_stage_status,
    normalize_order_status,
    order_status_for_stage,
)


def lock_order(order_name: str) -> None:
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )


def get_order(order_name: str) -> Any:
    return frappe.get_doc("Door Cutting Order", order_name)


def get_order_path(order_name: str) -> str | None:
    return frappe.db.get_value("Door Cutting Order", order_name, "production_path")


def get_order_status(order_name: str) -> str | None:
    return frappe.db.get_value("Door Cutting Order", order_name, "status")


def set_order_tracking(
    order_name: str,
    *,
    path: str | None = None,
    stage: Any | None = None,
    status: str | None = None,
    department: str | None = None,
    assignee: str | None = None,
    department_status: str | None = None,
    clear_stage: bool = False,
) -> None:
    values: dict[str, Any] = {}
    if path is not None:
        values["production_path"] = path
    if status is not None:
        values["status"] = status
    if department is not None:
        values["current_department"] = department
    if assignee is not None:
        values["current_assignee"] = assignee
    if department_status is not None:
        values["department_status"] = department_status
    if clear_stage:
        values["current_production_stage"] = None
    elif stage is not None:
        values["current_production_stage"] = stage.name
        stage_label = (
            getattr(stage, "department_label", None)
            or department_for_stage_type(stage.stage_type)
            or stage.stage_type
        )
        values["current_department"] = stage_label
        values["current_assignee"] = stage.assigned_to
        values["department_status"] = department_status_for_stage_status(stage.status)
        values["status"] = order_status_for_stage(stage.stage_type, stage_label)
    if values:
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            values,
            update_modified=True,
        )


def clear_factory_tracking(
    order_name: str,
    *,
    fallback_status: str,
) -> dict[str, Any]:
    """Clear stale factory routing after OFFCUT becomes customer-only.

    The production path/current-stage fields are execution projections, not order
    requirements. When no physical piece remains executable by the factory they
    must be cleared so old assignments cannot keep the order dispatched. Locked
    terminal statuses are preserved exactly.
    """

    current_status = normalize_order_status(get_order_status(order_name))
    values: dict[str, Any] = {
        "production_path": None,
        "current_production_stage": None,
        "current_department": "",
        "current_assignee": "",
        "department_status": "",
    }
    if current_status not in LOCKED_ORDER_STATUSES:
        values["status"] = fallback_status
    frappe.db.set_value(
        "Door Cutting Order",
        order_name,
        values,
        update_modified=True,
    )
    return values


def required_piece_qty(order_name: str) -> int:
    order = get_order(order_name)
    plan = None
    if order is not None:
        # Keep this focused adapter loadable by lightweight shop-floor harnesses;
        # runtime plan resolution is needed only for a real persisted order.
        from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
            approved_plan_for_order,
            current_working_plan,
        )

        plan = approved_plan_for_order(order) or current_working_plan(order_name)
    snapshot_json = str(getattr(plan, "snapshot_json", None) or "") if plan else ""
    if snapshot_json.strip():
        try:
            snapshot = frappe.parse_json(snapshot_json) or {}
            return physical_execution_projection_from_snapshot(
                snapshot
            ).factory_executable_quantity
        except (OffcutPolicyError, TypeError, ValueError):
            # Orders created before physical identities existed retain their legacy
            # quantity projection instead of being blocked by a migration gap.
            pass
    rows = frappe.get_all(
        "Door Cutting Order Detail",
        filters={
            "parent": order_name,
            "parenttype": "Door Cutting Order",
        },
        fields=["qty"],
    )
    return sum(cint(row.qty) for row in rows)


__all__ = [
    "clear_factory_tracking",
    "get_order",
    "get_order_path",
    "get_order_status",
    "lock_order",
    "required_piece_qty",
    "set_order_tracking",
]
