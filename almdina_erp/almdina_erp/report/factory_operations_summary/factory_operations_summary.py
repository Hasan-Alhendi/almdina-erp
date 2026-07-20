from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


PRODUCTION_STATUSES = (
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
    date_sql, values = _date_conditions(filters)
    rows: list[dict[str, Any]] = []

    status_rows = frappe.db.sql(
        f"""
        select status, count(*) as count
        from `tabDoor Cutting Order`
        where status not in ('Draft', 'Rejected', 'Cancelled')
          {date_sql}
        group by status
        order by status
        """,
        values,
        as_dict=True,
    )
    for row in status_rows:
        rows.append(_metric(_("Orders — {0}").format(row.status), row.count, _("Orders"), "Order Status"))

    active_count = frappe.db.count(
        "Door Cutting Order",
        filters={
            "status": ["in", PRODUCTION_STATUSES],
            **_date_filter_dict(filters),
        },
    )
    rows.append(_metric(_("Orders In Production / Attention"), active_count, _("Orders"), "Production"))

    plan_totals = frappe.db.sql(
        f"""
        select
            coalesce(sum(p.required_boards), 0) as full_boards,
            coalesce(sum(p.total_source_area_m2), 0) as source_area,
            coalesce(sum(p.used_area_m2), 0) as used_area,
            coalesce(sum(p.waste_area_m2), 0) as waste_area,
            coalesce(sum(p.reusable_remnant_area_m2), 0) as reusable_area,
            coalesce(sum(p.scrap_area_m2), 0) as scrap_area,
            coalesce(sum(p.total_cost_usd), 0) as planned_cost
        from `tabCutting Plan` p
        inner join `tabDoor Cutting Order` o on o.name = p.door_cutting_order
        where p.plan_kind = 'Order'
          and p.status = 'Approved'
          {date_sql}
        """,
        values,
        as_dict=True,
    )[0]

    actual_cost = frappe.db.sql(
        f"""
        select
            coalesce(sum(coalesce(p.total_cost_usd, o.total_cost_usd, 0)), 0)
              + coalesce(sum(coalesce(m.material_variance_cost_usd, 0)), 0)
              + coalesce(sum(coalesce(r.internal_loss_cost_usd, 0)), 0) as actual_cost,
            coalesce(sum(coalesce(m.material_variance_cost_usd, 0)), 0) as material_variance,
            coalesce(sum(coalesce(r.internal_loss_cost_usd, 0)), 0) as internal_loss
        from `tabDoor Cutting Order` o
        left join `tabCutting Plan` p on p.name = o.approved_plan
        left join (
            select door_cutting_order, sum(material_variance_cost_usd) as material_variance_cost_usd
            from `tabMaterial Consumption Log`
            where status = 'Submitted' and coalesce(actual_recorded, 0) = 1
            group by door_cutting_order
        ) m on m.door_cutting_order = o.name
        left join (
            select door_cutting_order, sum(internal_loss_cost_usd) as internal_loss_cost_usd
            from `tabReplacement Piece`
            where status = 'Completed' and coalesce(charge_customer, 0) = 0
            group by door_cutting_order
        ) r on r.door_cutting_order = o.name
        where o.approved_plan is not null
          and o.status != 'Cancelled'
          {date_sql}
        """,
        values,
        as_dict=True,
    )[0]

    rows.extend(
        [
            _metric(_("Full Boards Used"), plan_totals.full_boards, _("Boards"), "Material"),
            _metric(_("Total Source Area"), plan_totals.source_area, "m²", "Waste"),
            _metric(_("Used Piece Area"), plan_totals.used_area, "m²", "Waste"),
            _metric(_("Approved Waste Area"), plan_totals.waste_area, "m²", "Waste"),
            _metric(_("Reusable Remnant Area"), plan_totals.reusable_area, "m²", "Waste"),
            _metric(_("Scrap Area"), plan_totals.scrap_area, "m²", "Waste"),
            _metric(_("Planned Cost"), plan_totals.planned_cost, "USD", "Cost"),
            _metric(_("Material Variance Cost"), actual_cost.material_variance, "USD", "Cost"),
            _metric(_("Internal Replacement Loss"), actual_cost.internal_loss, "USD", "Cost"),
            _metric(_("Actual Cost"), actual_cost.actual_cost, "USD", "Cost"),
        ]
    )

    replacement_filters = {"status": ["not in", ["Completed", "Cancelled"]]}
    if filters.from_date:
        replacement_filters["creation"] = [">=", filters.from_date]
    open_replacements = frappe.db.count("Replacement Piece", filters=replacement_filters)
    rows.append(_metric(_("Open Replacement Pieces"), open_replacements, _("Pieces"), "Quality"))

    open_incidents_filters = {"status": ["!=", "Resolved"]}
    if filters.from_date:
        open_incidents_filters["incident_datetime"] = [">=", filters.from_date]
    open_incidents = frappe.db.count("Production Incident", filters=open_incidents_filters)
    rows.append(_metric(_("Open Production Incidents"), open_incidents, _("Incidents"), "Quality"))

    remnant_rows = frappe.db.sql(
        """
        select status, count(*) as count, coalesce(sum(area_m2), 0) as area
        from `tabBoard Remnant`
        where status in ('Available', 'Reserved')
        group by status
        """,
        as_dict=True,
    )
    for row in remnant_rows:
        rows.append(_metric(_("Remnants — {0}").format(row.status), row.count, _("Pieces"), "Remnants"))
        rows.append(_metric(_("Remnant Area — {0}").format(row.status), row.area, "m²", "Remnants"))

    return get_columns(), rows


def _date_conditions(filters: Any) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    values: dict[str, Any] = {}
    if filters.from_date:
        conditions.append("o.order_date >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.to_date:
        conditions.append("o.order_date <= %(to_date)s")
        values["to_date"] = filters.to_date
    return ((" and " + " and ".join(conditions)) if conditions else ""), values


def _date_filter_dict(filters: Any) -> dict[str, Any]:
    if filters.from_date and filters.to_date:
        return {"order_date": ["between", [filters.from_date, filters.to_date]]}
    if filters.from_date:
        return {"order_date": [">=", filters.from_date]}
    if filters.to_date:
        return {"order_date": ["<=", filters.to_date]}
    return {}


def _metric(label: str, value: Any, unit: str, category: str) -> dict[str, Any]:
    return {
        "category": category,
        "metric": label,
        "value": flt(value),
        "unit": unit,
    }


def get_columns() -> list[dict[str, Any]]:
    return [
        {"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 120},
        {"label": _("Metric"), "fieldname": "metric", "fieldtype": "Data", "width": 260},
        {"label": _("Value"), "fieldname": "value", "fieldtype": "Float", "precision": 3, "width": 140},
        {"label": _("Unit"), "fieldname": "unit", "fieldtype": "Data", "width": 100},
    ]
