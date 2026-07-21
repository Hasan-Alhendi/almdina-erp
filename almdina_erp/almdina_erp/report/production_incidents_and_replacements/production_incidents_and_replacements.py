from __future__ import annotations

from typing import Any

import frappe
from frappe import _


def execute(filters: dict[str, Any] | None = None):
    filters = frappe._dict(filters or {})
    conditions: list[str] = []
    values: dict[str, Any] = {}

    if filters.from_date:
        conditions.append("date(i.incident_datetime) >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.to_date:
        conditions.append("date(i.incident_datetime) <= %(to_date)s")
        values["to_date"] = filters.to_date
    if filters.worker:
        conditions.append("i.worker = %(worker)s")
        values["worker"] = filters.worker
    if filters.reason:
        conditions.append("i.reason = %(reason)s")
        values["reason"] = filters.reason
    if filters.status:
        conditions.append("i.status = %(status)s")
        values["status"] = filters.status
    if filters.order_name:
        conditions.append("i.door_cutting_order = %(order_name)s")
        values["order_name"] = filters.order_name

    where = " and " + " and ".join(conditions) if conditions else ""
    data = frappe.db.sql(
        f"""
        select
            i.name as incident,
            i.incident_datetime,
            i.door_cutting_order,
            i.piece_label,
            i.production_stage,
            i.worker,
            i.reason,
            i.status as incident_status,
            i.requires_replacement,
            r.name as replacement_piece,
            r.status as replacement_status,
            r.selected_remnant,
            r.cutting_plan,
            r.planned_internal_loss_usd,
            r.internal_loss_cost_usd,
            r.charge_customer,
            r.completed_on
        from `tabProduction Incident` i
        left join `tabReplacement Piece` r on r.incident = i.name
        where 1 = 1 {where}
        order by i.incident_datetime desc, i.modified desc
        """,
        values,
        as_dict=True,
    )
    for row in data:
        if row.reason:
            row.reason = _(row.reason)
        if row.incident_status:
            row.incident_status = _(row.incident_status)
        if row.replacement_status:
            row.replacement_status = _(row.replacement_status)
    return get_columns(), data


def get_columns():
    return [
        {"label": _("Incident"), "fieldname": "incident", "fieldtype": "Link", "options": "Production Incident", "width": 145},
        {"label": _("Date / Time"), "fieldname": "incident_datetime", "fieldtype": "Datetime", "width": 145},
        {"label": _("Order"), "fieldname": "door_cutting_order", "fieldtype": "Link", "options": "Door Cutting Order", "width": 145},
        {"label": _("Piece"), "fieldname": "piece_label", "fieldtype": "Data", "width": 80},
        {"label": _("Stage"), "fieldname": "production_stage", "fieldtype": "Link", "options": "Production Stage", "width": 140},
        {"label": _("Worker"), "fieldname": "worker", "fieldtype": "Link", "options": "User", "width": 145},
        {"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 130},
        {"label": _("Incident Status"), "fieldname": "incident_status", "fieldtype": "Data", "width": 110},
        {"label": _("Replacement"), "fieldname": "replacement_piece", "fieldtype": "Link", "options": "Replacement Piece", "width": 145},
        {"label": _("Replacement Status"), "fieldname": "replacement_status", "fieldtype": "Data", "width": 120},
        {"label": _("Remnant"), "fieldname": "selected_remnant", "fieldtype": "Link", "options": "Board Remnant", "width": 135},
        {"label": _("Mini Plan"), "fieldname": "cutting_plan", "fieldtype": "Link", "options": "Cutting Plan", "width": 135},
        {"label": _("Planned Loss USD"), "fieldname": "planned_internal_loss_usd", "fieldtype": "Currency", "width": 115},
        {"label": _("Actual Loss USD"), "fieldname": "internal_loss_cost_usd", "fieldtype": "Currency", "width": 115},
        {"label": _("Charge Customer"), "fieldname": "charge_customer", "fieldtype": "Check", "width": 105},
        {"label": _("Completed On"), "fieldname": "completed_on", "fieldtype": "Datetime", "width": 145},
    ]
