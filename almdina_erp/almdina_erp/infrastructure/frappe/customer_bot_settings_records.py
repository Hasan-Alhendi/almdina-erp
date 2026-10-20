"""Keep Customer Bot Settings closed to desk writes and generic CRUD."""

from __future__ import annotations

import frappe
from frappe import _


SERVICE_FLAG = "customer_bot_settings_service"


def reject_direct_customer_bot_settings_mutation(document: object) -> None:
    if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_patch", False):
        return
    if getattr(frappe.flags, SERVICE_FLAG, False):
        return
    flags = getattr(document, "flags", None)
    if getattr(flags, SERVICE_FLAG, False):
        return
    frappe.throw(
        _("Customer bot settings are service-managed."),
        frappe.PermissionError,
    )


def customer_bot_settings_has_permission(doc=None, user=None, ptype=None) -> bool:
    return False


def customer_bot_settings_query(user=None) -> str:
    return "1=0"


__all__ = [
    "SERVICE_FLAG",
    "customer_bot_settings_has_permission",
    "customer_bot_settings_query",
    "reject_direct_customer_bot_settings_mutation",
]
