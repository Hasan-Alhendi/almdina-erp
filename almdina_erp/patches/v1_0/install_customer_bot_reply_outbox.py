"""Add the reply-intent unique keys. Existing bot settings and sessions stay put."""

from __future__ import annotations


def execute() -> None:
    import frappe

    if not frappe.db.table_exists("Customer Bot Reply Intent"):
        return
    frappe.db.add_unique(
        "Customer Bot Reply Intent",
        ["reply_id"],
        "unique_customer_bot_reply_id",
    )
    frappe.db.add_unique(
        "Customer Bot Reply Intent",
        ["connection_ref", "provider_event_id", "sequence"],
        "unique_customer_bot_reply_intent",
    )
