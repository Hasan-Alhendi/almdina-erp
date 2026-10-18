"""Guards for customer-bot records that must not be edited through generic CRUD."""

from __future__ import annotations

import frappe
from frappe import _


SERVICE_WRITE_FLAG = "customer_bot_service_write"
PHONE_ACCESS_DOCTYPE = "Customer Bot Phone Access"
PHONE_REQUEST_DOCTYPE = "Customer Bot Phone Request"
_MUTATION_TYPES = frozenset(
    {"create", "write", "delete", "submit", "cancel", "amend", "import"}
)


def reject_direct_customer_bot_mutation(document: object) -> None:
    flags = getattr(document, "flags", None)
    if getattr(flags, SERVICE_WRITE_FLAG, False):
        return
    if getattr(frappe.flags, SERVICE_WRITE_FLAG, False):
        return
    frappe.throw(
        _("Customer bot access records are service-managed."),
        frappe.PermissionError,
    )


def service_write_enabled() -> bool:
    return bool(getattr(frappe.flags, SERVICE_WRITE_FLAG, False))


__all__ = [
    "PHONE_ACCESS_DOCTYPE",
    "PHONE_REQUEST_DOCTYPE",
    "SERVICE_WRITE_FLAG",
    "_MUTATION_TYPES",
    "reject_direct_customer_bot_mutation",
    "service_write_enabled",
]
