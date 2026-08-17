from __future__ import annotations

import frappe


def execute() -> None:
    """Backfill the best available original assignment time for legacy stages."""

    if not frappe.db.has_column("Production Stage", "assignment_time"):
        return
    frappe.db.sql(
        """
        update `tabProduction Stage`
           set assignment_time = creation
         where assignment_time is null
           and ifnull(assigned_to, '') != ''
        """
    )
