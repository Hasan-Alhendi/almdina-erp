from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters: dict[str, Any] | None = None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    conditions, values = get_conditions(filters)

    rows = frappe.db.sql(
        f"""
        select
            o.name as order_name,
            o.order_date,
            o.customer,
            o.status,
            o.board_description,
            o.board_length_cm,
            o.board_width_cm,
            o.required_boards,
            coalesce(p.total_source_area_m2, 0) as total_source_area_m2,
            coalesce(p.used_area_m2, o.total_area_m2, 0) as used_area_m2,
            coalesce(p.waste_area_m2, o.waste_area_m2, 0) as waste_area_m2,
            coalesce(p.waste_percent, o.waste_percent, 0) as waste_percent,
            coalesce(p.total_cost_usd, o.total_cost_usd, 0) as planned_cost_usd,
            coalesce(r.internal_loss_cost_usd, 0) as internal_loss_cost_usd,
            coalesce(p.total_cost_usd, o.total_cost_usd, 0)
              + coalesce(r.internal_loss_cost_usd, 0) as actual_cost_usd,
            coalesce(o.customer_quote_total_usd, o.total_cost_usd, 0)
              as customer_quote_total_usd
        from `tabDoor Cutting Order` o
        left join `tabCutting Plan` p on p.name = o.approved_plan
        left join (
            select door_cutting_order, sum(internal_loss_cost_usd) as internal_loss_cost_usd
            from `tabReplacement Piece`
            where status = 'Completed' and coalesce(charge_customer, 0) = 0
            group by door_cutting_order
        ) r on r.door_cutting_order = o.name
        where 1 = 1 {conditions}
        order by o.order_date desc, o.modified desc
        """,
        values,
        as_dict=True,
    )

    for row in rows:
        # Status values are stored in English for workflow stability, but reports
        # must display them in the active user language.
        if row.status:
            row.status = _(row.status)
        row.variance_usd = flt(row.actual_cost_usd) - flt(row.planned_cost_usd)
    return columns, rows


def get_conditions(filters: Any) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    values: dict[str, Any] = {}
    mapping = {
        "from_date": ("o.order_date >= %(from_date)s", "from_date"),
        "to_date": ("o.order_date <= %(to_date)s", "to_date"),
        "customer": ("o.customer = %(customer)s", "customer"),
        "status": ("o.status = %(status)s", "status"),
        "board_description": (
            "o.board_description like %(board_description)s",
            "board_description",
        ),
    }
    for fieldname, (condition, key) in mapping.items():
        if filters.get(fieldname):
            conditions.append(condition)
            value = filters.get(fieldname)
            values[key] = (
                f"%{value}%"
                if fieldname == "board_description"
                else value
            )
    return (" and " + " and ".join(conditions)) if conditions else "", values


def get_columns() -> list[dict[str, Any]]:
    return [
        {"label": _("Order"), "fieldname": "order_name", "fieldtype": "Link", "options": "Door Cutting Order", "width": 150},
        {"label": _("Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 95},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
        {"label": _("Board Description"), "fieldname": "board_description", "fieldtype": "Data", "width": 180},
        {"label": _("Board Length (CM)"), "fieldname": "board_length_cm", "fieldtype": "Float", "width": 105},
        {"label": _("Board Width (CM)"), "fieldname": "board_width_cm", "fieldtype": "Float", "width": 105},
        {"label": _("Full Boards"), "fieldname": "required_boards", "fieldtype": "Int", "width": 90},
        {"label": _("Total Source Area M2"), "fieldname": "total_source_area_m2", "fieldtype": "Float", "precision": 3, "width": 120},
        {"label": _("Used Area M2"), "fieldname": "used_area_m2", "fieldtype": "Float", "precision": 3, "width": 105},
        {"label": _("Waste Area M2"), "fieldname": "waste_area_m2", "fieldtype": "Float", "precision": 3, "width": 110},
        {"label": _("Waste %"), "fieldname": "waste_percent", "fieldtype": "Percent", "width": 90},
        {"label": _("Planned Cost USD"), "fieldname": "planned_cost_usd", "fieldtype": "Currency", "width": 120},
        {"label": _("Internal Loss USD"), "fieldname": "internal_loss_cost_usd", "fieldtype": "Currency", "width": 120},
        {"label": _("Actual Cost USD"), "fieldname": "actual_cost_usd", "fieldtype": "Currency", "width": 120},
        {"label": _("Variance USD"), "fieldname": "variance_usd", "fieldtype": "Currency", "width": 110},
        {"label": _("Customer Quote Total USD"), "fieldname": "customer_quote_total_usd", "fieldtype": "Currency", "width": 140},
    ]
