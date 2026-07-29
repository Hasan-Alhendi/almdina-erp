from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    department_for_stage_type,
    department_status_for_stage_status,
    order_status_for_stage_type,
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
        values["current_department"] = department_for_stage_type(stage.stage_type)
        values["current_assignee"] = stage.assigned_to
        values["department_status"] = department_status_for_stage_status(stage.status)
        values["status"] = order_status_for_stage_type(stage.stage_type)
    if values:
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            values,
            update_modified=True,
        )


def required_piece_qty(order_name: str) -> int:
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
    "get_order",
    "get_order_path",
    "get_order_status",
    "required_piece_qty",
    "set_order_tracking",
]
