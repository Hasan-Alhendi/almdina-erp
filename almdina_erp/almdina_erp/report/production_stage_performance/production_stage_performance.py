from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters: dict[str, Any] | None = None):
    filters = frappe._dict(filters or {})
    conditions: list[str] = []
    values: dict[str, Any] = {}

    if filters.from_date:
        conditions.append("date(s.start_time) >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.to_date:
        conditions.append("date(s.start_time) <= %(to_date)s")
        values["to_date"] = filters.to_date
    if filters.worker:
        conditions.append("s.assigned_to = %(worker)s")
        values["worker"] = filters.worker
    if filters.stage_type:
        conditions.append("s.stage_type = %(stage_type)s")
        values["stage_type"] = filters.stage_type
    if filters.status:
        conditions.append("s.status = %(status)s")
        values["status"] = filters.status

    where = " and " + " and ".join(conditions) if conditions else ""
    data = frappe.db.sql(
        f"""
        select
            s.name as stage,
            s.door_cutting_order,
            s.stage_type,
            s.status,
            s.assigned_to as worker,
            s.start_time,
            s.finish_time,
            s.paused_seconds,
            s.actual_working_seconds,
            s.completed_qty,
            s.piece_label
        from `tabProduction Stage` s
        where 1 = 1 {where}
        order by s.start_time desc, s.modified desc
        """,
        values,
        as_dict=True,
    )
    for row in data:
        row.paused_minutes = flt(row.paused_seconds) / 60
        row.working_minutes = flt(row.actual_working_seconds) / 60

    return get_columns(), data


def get_columns():
    return [
        {"label": _("Stage"), "fieldname": "stage", "fieldtype": "Link", "options": "Production Stage", "width": 145},
        {"label": _("Order"), "fieldname": "door_cutting_order", "fieldtype": "Link", "options": "Door Cutting Order", "width": 145},
        {"label": _("Stage Type"), "fieldname": "stage_type", "fieldtype": "Data", "width": 130},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 105},
        {"label": _("Worker"), "fieldname": "worker", "fieldtype": "Link", "options": "User", "width": 150},
        {"label": _("Start"), "fieldname": "start_time", "fieldtype": "Datetime", "width": 145},
        {"label": _("Finish"), "fieldname": "finish_time", "fieldtype": "Datetime", "width": 145},
        {"label": _("Paused Minutes"), "fieldname": "paused_minutes", "fieldtype": "Float", "precision": 1, "width": 110},
        {"label": _("Working Minutes"), "fieldname": "working_minutes", "fieldtype": "Float", "precision": 1, "width": 115},
        {"label": _("Completed Qty"), "fieldname": "completed_qty", "fieldtype": "Int", "width": 105},
        {"label": _("Exceptional Piece"), "fieldname": "piece_label", "fieldtype": "Data", "width": 110},
    ]
