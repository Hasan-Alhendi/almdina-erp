from __future__ import annotations

import frappe
from frappe.utils import cint


def execute() -> None:
    """Make the former hard-coded Drawing planning gate explicit in route data."""

    if not frappe.db.exists("DocType", "Production Routing Stage"):
        return
    meta = frappe.get_meta("Production Routing Stage")
    if not meta.has_field("is_planning_stage"):
        return

    route_names = frappe.get_all("Production Routing", pluck="name")
    for route_name in route_names:
        rows = frappe.get_all(
            "Production Routing Stage",
            filters={
                "parent": route_name,
                "parenttype": "Production Routing",
                "required": 1,
            },
            fields=["name", "stage_type", "sequence", "idx", "is_planning_stage"],
            order_by="sequence asc, idx asc",
        )
        if not rows:
            continue

        already_planning = [row for row in rows if cint(row.is_planning_stage)]
        if already_planning:
            continue

        first = rows[0]
        if str(first.stage_type or "").strip() != "Drawing":
            continue
        frappe.db.set_value(
            "Production Routing Stage",
            first.name,
            "is_planning_stage",
            1,
            update_modified=False,
        )


__all__ = ["execute"]
