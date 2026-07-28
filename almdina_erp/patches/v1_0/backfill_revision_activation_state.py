from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.table_exists("Door Cutting Order"):
        return
    if not frappe.db.has_column("Door Cutting Order", "revision_state"):
        return

    # Existing orders are the current revision by default. Editable successors
    # created before this activation policy landed must wait for explicit approval.
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
           set revision_state = 'Current'
         where coalesce(revision_state, '') = ''
        """
    )
    frappe.db.sql(
        """
        update `tabDoor Cutting Order`
           set revision_state = 'Pending Activation'
         where coalesce(revision_of, '') <> ''
           and status in ('Draft', 'Pending Review', 'Rejected')
           and coalesce(revision_activated_on, '') = ''
        """
    )
