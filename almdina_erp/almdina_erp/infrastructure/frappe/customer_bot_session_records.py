"""Keep customer-bot session rows closed to desk writes and generic CRUD."""

from __future__ import annotations

import frappe
from frappe import _


CONVERSATION_DOCTYPE = "Customer Bot Conversation"
EVENT_DOCTYPE = "Customer Bot Inbound Event"


def reject_direct_customer_bot_session_mutation(document: object) -> None:
    if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_patch", False):
        return
    frappe.throw(
        _("Customer bot session records are service-managed."),
        frappe.PermissionError,
    )


def customer_bot_conversation_has_permission(doc=None, user=None, ptype=None) -> bool:
    return False


def customer_bot_inbound_event_has_permission(doc=None, user=None, ptype=None) -> bool:
    return False


def customer_bot_conversation_query(user=None) -> str:
    return "1=0"


def customer_bot_inbound_event_query(user=None) -> str:
    return "1=0"


__all__ = [
    "CONVERSATION_DOCTYPE",
    "EVENT_DOCTYPE",
    "customer_bot_conversation_has_permission",
    "customer_bot_conversation_query",
    "customer_bot_inbound_event_has_permission",
    "customer_bot_inbound_event_query",
    "reject_direct_customer_bot_session_mutation",
]
