from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.stock_service import validate_stock_for_order


ACTIVE_PRE_CONSUMPTION_STATUSES = (
    "Approved",
    "Cutting In Progress",
    "Cut Completed",
    "Edge Banding In Progress",
    "Production In Progress",
    "Quality Check",
    "Replacement Required",
    "Partially Completed",
)


def execute(filters: dict[str, Any] | None = None):
    filters = frappe._dict(filters or {})
    order_filters: dict[str, Any] = {
        "approved_plan": ["is", "set"],
        "status": ["in", ACTIVE_PRE_CONSUMPTION_STATUSES],
    }
    if filters.order_name:
        order_filters["name"] = filters.order_name
    if filters.customer:
        order_filters["customer"] = filters.customer

    orders = frappe.get_all(
        "Door Cutting Order",
        filters=order_filters,
        fields=["name", "order_date", "customer", "status", "approved_plan"],
        order_by="order_date asc, creation asc",
    )

    rows: list[dict[str, Any]] = []
    for order in orders:
        # Once the approved-plan material issue is submitted, current Bin levels
        # no longer represent a shortage for that order; the material is already
        # physically consumed and should not appear in a pending-shortage report.
        consumed = frappe.db.exists(
            "Material Consumption Log",
            {
                "door_cutting_order": order.name,
                "cutting_plan": order.approved_plan,
                "status": "Submitted",
            },
        )
        if consumed:
            continue

        availability = validate_stock_for_order(order.name, throw_on_shortage=False)
        for material in availability.get("materials") or []:
            if filters.shortage_only and not material.get("shortage_qty"):
                continue
            rows.append(
                {
                    "order_name": order.name,
                    "order_date": order.order_date,
                    "customer": order.customer,
                    "order_status": _(order.status) if order.status else "",
                    "item_code": material.get("item_code"),
                    "kind": _(material.get("kind")) if material.get("kind") else "",
                    "warehouse": material.get("warehouse"),
                    "required_qty": material.get("required_qty"),
                    "actual_qty": material.get("actual_qty"),
                    "reserved_qty": material.get("reserved_by_other_reservations"),
                    "available_qty": material.get("available_qty"),
                    "shortage_qty": material.get("shortage_qty"),
                    "planned_unit": _(material.get("planned_unit")) if material.get("planned_unit") else "",
                    "planned_qty": material.get("planned_qty"),
                }
            )

    return get_columns(), rows


def get_columns():
    return [
        {"label": _("Order"), "fieldname": "order_name", "fieldtype": "Link", "options": "Door Cutting Order", "width": 150},
        {"label": _("Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 95},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
        {"label": _("Order Status"), "fieldname": "order_status", "fieldtype": "Data", "width": 135},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 145},
        {"label": _("Material Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 105},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 145},
        {"label": _("Required Stock Qty"), "fieldname": "required_qty", "fieldtype": "Float", "width": 115},
        {"label": _("Physical Stock"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 105},
        {"label": _("Reserved Elsewhere"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 115},
        {"label": _("Available After Reservations"), "fieldname": "available_qty", "fieldtype": "Float", "width": 145},
        {"label": _("Shortage"), "fieldname": "shortage_qty", "fieldtype": "Float", "width": 90},
        {"label": _("Business Unit"), "fieldname": "planned_unit", "fieldtype": "Data", "width": 95},
        {"label": _("Planned Business Qty"), "fieldname": "planned_qty", "fieldtype": "Float", "width": 125},
    ]
