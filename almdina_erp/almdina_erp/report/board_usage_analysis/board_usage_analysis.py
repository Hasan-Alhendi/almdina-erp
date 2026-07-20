from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def execute(filters: dict[str, Any] | None = None):
    filters = frappe._dict(filters or {})
    conditions, values = get_conditions(filters)
    rows = frappe.db.sql(
        f"""
        select
            src.board_item,
            src.material,
            src.color,
            src.thickness_mm,
            count(distinct p.door_cutting_order) as order_count,
            sum(case when src.source_type = 'Full Board' then 1 else 0 end) as full_boards_used,
            sum(case when src.source_type = 'Remnant' then 1 else 0 end) as remnants_used,
            sum(coalesce(src.source_area_m2, 0)) as total_source_area_m2,
            sum(coalesce(src.used_area_m2, 0)) as used_area_m2,
            sum(coalesce(src.waste_area_m2, 0)) as planned_waste_area_m2
        from `tabCutting Plan Source` src
        inner join `tabCutting Plan` p
            on p.name = src.parent
           and src.parenttype = 'Cutting Plan'
        inner join `tabDoor Cutting Order` o
            on o.name = p.door_cutting_order
        where p.plan_kind = 'Order'
          and p.status = 'Approved'
          {conditions}
        group by src.board_item, src.material, src.color, src.thickness_mm
        order by full_boards_used desc, remnants_used desc, src.material, src.color
        """,
        values,
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
    if filters.board_item:
        conditions.append("src.board_item = %(board_item)s")
        values["board_item"] = filters.board_item
    if filters.material:
        conditions.append("src.material = %(material)s")
        values["material"] = filters.material
    if filters.color:
        conditions.append("src.color = %(color)s")
        values["color"] = filters.color
    if filters.thickness_mm not in (None, ""):
        conditions.append("abs(coalesce(src.thickness_mm, 0) - %(thickness_mm)s) <= 0.001")
        values["thickness_mm"] = filters.thickness_mm
    if filters.customer:
        conditions.append("o.customer = %(customer)s")
        values["customer"] = filters.customer

    return ((" and " + " and ".join(conditions)) if conditions else ""), values


def get_columns() -> list[dict[str, Any]]:
    return [
        {"label": _("Board Item"), "fieldname": "board_item", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Material"), "fieldname": "material", "fieldtype": "Data", "width": 115},
        {"label": _("Color"), "fieldname": "color", "fieldtype": "Data", "width": 105},
        {"label": _("Thickness MM"), "fieldname": "thickness_mm", "fieldtype": "Float", "width": 100},
        {"label": _("Orders"), "fieldname": "order_count", "fieldtype": "Int", "width": 80},
        {"label": _("Full Boards Used"), "fieldname": "full_boards_used", "fieldtype": "Int", "width": 105},
        {"label": _("Remnants Used"), "fieldname": "remnants_used", "fieldtype": "Int", "width": 100},
        {"label": _("Total Source Area M2"), "fieldname": "total_source_area_m2", "fieldtype": "Float", "precision": 3, "width": 125},
        {"label": _("Used Area M2"), "fieldname": "used_area_m2", "fieldtype": "Float", "precision": 3, "width": 105},
        {"label": _("Planned Waste Area M2"), "fieldname": "planned_waste_area_m2", "fieldtype": "Float", "precision": 3, "width": 130},
    ]
