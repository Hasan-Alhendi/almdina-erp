from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters: dict[str, Any] | None = None):
    filters = frappe._dict(filters or {})
    conditions: list[str] = []
    values: dict[str, Any] = {}

    for fieldname, column in (
        ("status", "r.status"),
        ("board_item", "r.board_item"),
        ("warehouse", "r.warehouse"),
        ("material", "r.material"),
        ("color", "r.color"),
    ):
        if filters.get(fieldname):
            conditions.append(f"{column} = %({fieldname})s")
            values[fieldname] = filters.get(fieldname)

    where = " and " + " and ".join(conditions) if conditions else ""
    data = frappe.db.sql(
        f"""
        select
            r.name as remnant,
            r.status,
            r.board_item,
            r.material,
            r.color,
            r.thickness_mm,
            r.width_mm,
            r.length_mm,
            r.area_m2,
            r.warehouse,
            r.location,
            r.source_order,
            r.source_plan,
            r.parent_remnant,
            r.reserved_for_order,
            r.creation
        from `tabBoard Remnant` r
        where 1 = 1 {where}
        order by r.status asc, r.area_m2 desc, r.creation asc
        """,
        values,
        as_dict=True,
    )
    current = getdate(today())
    for row in data:
        row.age_days = date_diff(current, getdate(row.creation)) if row.creation else 0
        if row.status:
            row.status = _(row.status)
    return get_columns(), data


def get_columns():
    return [
        {"label": _("Remnant"), "fieldname": "remnant", "fieldtype": "Link", "options": "Board Remnant", "width": 145},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 95},
        {"label": _("Board Item"), "fieldname": "board_item", "fieldtype": "Link", "options": "Item", "width": 140},
        {"label": _("Material"), "fieldname": "material", "fieldtype": "Data", "width": 100},
        {"label": _("Color"), "fieldname": "color", "fieldtype": "Data", "width": 90},
        {"label": _("Thickness MM"), "fieldname": "thickness_mm", "fieldtype": "Float", "width": 95},
        {"label": _("Width MM"), "fieldname": "width_mm", "fieldtype": "Float", "width": 90},
        {"label": _("Length MM"), "fieldname": "length_mm", "fieldtype": "Float", "width": 95},
        {"label": _("Area M2"), "fieldname": "area_m2", "fieldtype": "Float", "precision": 4, "width": 90},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 140},
        {"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 110},
        {"label": _("Age Days"), "fieldname": "age_days", "fieldtype": "Int", "width": 80},
        {"label": _("Source Order"), "fieldname": "source_order", "fieldtype": "Link", "options": "Door Cutting Order", "width": 145},
        {"label": _("Source Plan"), "fieldname": "source_plan", "fieldtype": "Link", "options": "Cutting Plan", "width": 140},
        {"label": _("Parent Remnant"), "fieldname": "parent_remnant", "fieldtype": "Link", "options": "Board Remnant", "width": 140},
        {"label": _("Reserved For"), "fieldname": "reserved_for_order", "fieldtype": "Link", "options": "Door Cutting Order", "width": 145},
    ]
