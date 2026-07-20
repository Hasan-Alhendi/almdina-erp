from __future__ import annotations

from typing import Any

import frappe
from frappe import _


ACTIVE_HISTORY_STATUSES = (
    "Approved",
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
    filters = frappe._dict(filters or {})
    conditions, values = get_conditions(filters)
    rows = frappe.db.sql(
        f"""
        select
            d.width_cm,
            d.length_cm,
            o.board_item,
            o.board_material as material,
            o.board_color as color,
            o.board_thickness_mm as thickness_mm,
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
            o.board_item,
            o.board_material,
            o.board_color,
            o.board_thickness_mm
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
    if filters.board_item:
        conditions.append("o.board_item = %(board_item)s")
        values["board_item"] = filters.board_item
    if filters.material:
        conditions.append("o.board_material = %(material)s")
        values["material"] = filters.material
    if filters.color:
        conditions.append("o.board_color = %(color)s")
        values["color"] = filters.color
    if filters.thickness_mm not in (None, ""):
        conditions.append("abs(coalesce(o.board_thickness_mm, 0) - %(thickness_mm)s) <= 0.001")
        values["thickness_mm"] = filters.thickness_mm
    return ((" and " + " and ".join(conditions)) if conditions else ""), values


def get_columns() -> list[dict[str, Any]]:
    return [
        {"label": _("Width CM"), "fieldname": "width_cm", "fieldtype": "Float", "width": 90},
        {"label": _("Length CM"), "fieldname": "length_cm", "fieldtype": "Float", "width": 90},
        {"label": _("Board Item"), "fieldname": "board_item", "fieldtype": "Link", "options": "Item", "width": 145},
        {"label": _("Material"), "fieldname": "material", "fieldtype": "Data", "width": 110},
        {"label": _("Color"), "fieldname": "color", "fieldtype": "Data", "width": 100},
        {"label": _("Thickness MM"), "fieldname": "thickness_mm", "fieldtype": "Float", "width": 95},
        {"label": _("Total Quantity"), "fieldname": "total_qty", "fieldtype": "Int", "width": 100},
        {"label": _("Orders"), "fieldname": "order_count", "fieldtype": "Int", "width": 80},
        {"label": _("Total Area M2"), "fieldname": "total_area_m2", "fieldtype": "Float", "precision": 3, "width": 105},
        {"label": _("Total Edge Meters"), "fieldname": "total_edge_meters", "fieldtype": "Float", "precision": 3, "width": 115},
    ]
