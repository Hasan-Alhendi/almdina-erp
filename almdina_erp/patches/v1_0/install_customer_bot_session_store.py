"""Add the session unique keys without changing bot settings or retired phone rows."""

from __future__ import annotations


def execute() -> None:
    import frappe

    if frappe.db.table_exists("Customer Bot Conversation"):
        frappe.db.add_unique(
            "Customer Bot Conversation",
            ["connection_ref", "conversation_id", "sender_id"],
            "unique_customer_bot_conversation",
        )
    if frappe.db.table_exists("Customer Bot Inbound Event"):
        frappe.db.add_unique(
            "Customer Bot Inbound Event",
            ["connection_ref", "provider_event_id"],
            "unique_customer_bot_inbound_event",
        )
