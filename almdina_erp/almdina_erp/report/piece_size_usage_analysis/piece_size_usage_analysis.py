from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.report_permission_service import (
    require_operational_report_access,
)


ACTIVE_HISTORY_STATUSES = (
    "Approved",
    "At Sharyoun",
    "At Drawing",
    "At CNC",
    "At Sanding",
    "Ready for Delivery",
    "Delivered",
    "Cutting In Progress",
    "Cut Completed",
    "Edge Banding In Progress",
    "Production In Progress",
    "Quality Check",
    "Completed",
    "Replacement Required",
    "Partially Completed",
)


def execute(filters: dict[str, Any] | None = None):
    require_operational_report_access()
    filters = frappe._dict(filters or {})
    conditions, values = get_conditions(filters)
    rows = frappe.db.sql(
        f"""
        select
            d.width_cm,
            d.length_cm,
            o.board_description,
            o.board_length_cm,
            o.board_width_cm,
            sum(coalesce(d.qty, 0)) as total_qty,
            count(distinct o.name) as order_count,
            sum(coalesce(d.area_m2, 0)) as total_area_m2,
            sum(coalesce(d.edge_meters, 0)) as total_edge_meters
        from `tabDoor Cutting Order Detail` d
        inner join `tabDoor Cutting Order` o
            on o.name = d.parent
           and d.parenttype = 'Door Cutting Order'
        where o.status in %(statuses)s
          {conditions}
        group by
            d.width_cm,
            d.length_cm,
            o.board_description,
            o.board_length_cm,
            o.board_width_cm
        order by total_qty desc, order_count desc, d.width_cm desc, d.length_cm desc
        """,
        {**values, "statuses": ACTIVE_HISTORY_STATUSES},
        as_dict=True,
    )
    return get_columns(), rows


def get_conditions(filters: Any) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    values: dict[str, Any] = {}
    if filters.from_date:
        conditions.append("o.order_date >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.to_date:
        conditions.append("o.order_date <= %(to_date)s")
        values["to_date"] = filters.to_date
    if filters.customer:
        conditions.append("o.customer = %(customer)s")
        values["customer"] = filters.customer
    if filters.board_description:
        conditions.append("o.board_description like %(board_description)s")
        values["board_description"] = f"%{filters.board_description}%"
    return ((" and " + " and ".join(conditions)) if conditions else ""), values


def get_columns() -> list[dict[str, Any]]:
    return [
        {"label": _("Width CM"), "fieldname": "width_cm", "fieldtype": "Float", "width": 90},
        {"label": _("Length CM"), "fieldname": "length_cm", "fieldtype": "Float", "width": 90},
        {"label": _("Board Description"), "fieldname": "board_description", "fieldtype": "Data", "width": 180},
        {"label": _("Board Length (CM)"), "fieldname": "board_length_cm", "fieldtype": "Float", "width": 105},
        {"label": _("Board Width (CM)"), "fieldname": "board_width_cm", "fieldtype": "Float", "width": 105},
        {"label": _("Total Quantity"), "fieldname": "total_qty", "fieldtype": "Int", "width": 100},
        {"label": _("Orders"), "fieldname": "order_count", "fieldtype": "Int", "width": 80},
        {"label": _("Total Area M2"), "fieldname": "total_area_m2", "fieldtype": "Float", "precision": 3, "width": 105},
        {"label": _("Total Edge Meters"), "fieldname": "total_edge_meters", "fieldtype": "Float", "precision": 3, "width": 115},
    ]
