from __future__ import annotations

import frappe


def execute() -> None:
    """Clear previously stored or backfilled machine values on existing orders."""

    if not frappe.db.has_column("Door Cutting Order", "order_cutting_machine"):
        return
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
           set order_cutting_machine = NULL
         where ifnull(order_cutting_machine, '') != ''
        """
    )
