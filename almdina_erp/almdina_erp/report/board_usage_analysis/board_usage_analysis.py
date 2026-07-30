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
            src.board_description,
            count(distinct p.door_cutting_order) as order_count,
            count(src.name) as boards_used,
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
        group by src.board_description
        order by boards_used desc, src.board_description
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
    if filters.board_description:
        conditions.append("src.board_description like %(board_description)s")
        values["board_description"] = f"%{filters.board_description}%"
    if filters.customer:
        conditions.append("o.customer = %(customer)s")
        values["customer"] = filters.customer

    return ((" and " + " and ".join(conditions)) if conditions else ""), values


def get_columns() -> list[dict[str, Any]]:
    return [
        {"label": _("Board Description"), "fieldname": "board_description", "fieldtype": "Data", "width": 200},
        {"label": _("Orders"), "fieldname": "order_count", "fieldtype": "Int", "width": 80},
        {"label": _("Boards Used"), "fieldname": "boards_used", "fieldtype": "Int", "width": 100},
        {"label": _("Total Source Area M2"), "fieldname": "total_source_area_m2", "fieldtype": "Float", "precision": 3, "width": 125},
        {"label": _("Used Area M2"), "fieldname": "used_area_m2", "fieldtype": "Float", "precision": 3, "width": 105},
        {"label": _("Planned Waste Area M2"), "fieldname": "planned_waste_area_m2", "fieldtype": "Float", "precision": 3, "width": 130},
    ]
