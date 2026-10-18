"""Native read limits for customer-bot records.

Mutations stay closed here. Approval and revocation go through the use cases.
The hook can only narrow a grant; it does not create one.
"""

from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_records import (
    _MUTATION_TYPES,
)
from almdina_erp.resource_permissions import customer_has_permission


def customer_bot_phone_access_query(user: str | None = None) -> str:
    return _query(user)


def customer_bot_phone_request_query(user: str | None = None) -> str:
    return _query(user)


def customer_bot_phone_access_has_permission(
    doc: Any = None,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    return _has_permission(doc, user, ptype, permission_type, "customer")


def customer_bot_phone_request_has_permission(
    doc: Any = None,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    return _has_permission(doc, user, ptype, permission_type, "proposed_customer")


def _query(user: str | None) -> str:
    resolved = user or frappe.session.user
    if resolved == "Administrator":
        return ""
    if not _can_read(resolved, None):
        return "1=0"
    return ""


def _has_permission(
    doc: Any,
    user: str | None,
    ptype: str | None,
    permission_type: str | None,
    customer_field: str,
) -> bool:
    resolved = user or frappe.session.user
    resolved_type = ptype if ptype is not None else permission_type
    if resolved_type in _MUTATION_TYPES:
        return False
    customer_id = ""
    if doc is not None and not isinstance(doc, str):
        customer_id = str(getattr(doc, customer_field, "") or "")
    return _can_read(resolved, customer_id or None)


def _can_read(user: str, customer_id: str | None) -> bool:
    if user == "Administrator":
        return True
    if not doctype_has_capability(Capability.MANAGE_CUSTOMER_BOT_ACCESS, user=user):
        return False
    return bool(customer_has_permission(customer_id, user=user, ptype="read"))


__all__ = [
    "customer_bot_phone_access_has_permission",
    "customer_bot_phone_access_query",
    "customer_bot_phone_request_has_permission",
    "customer_bot_phone_request_query",
]
