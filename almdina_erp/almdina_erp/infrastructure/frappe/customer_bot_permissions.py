"""Closed access for retired customer-bot phone records.

The DocTypes remain for migration compatibility. No product grant, including
``manage_customer_bot_access``, opens them. Mutations stay closed.
"""

from __future__ import annotations

from typing import Any


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
    del user
    return "1=0"


def _has_permission(
    doc: Any,
    user: str | None,
    ptype: str | None,
    permission_type: str | None,
    customer_field: str,
) -> bool:
    del doc, user, ptype, permission_type, customer_field
    return False


__all__ = [
    "customer_bot_phone_access_has_permission",
    "customer_bot_phone_access_query",
    "customer_bot_phone_request_has_permission",
    "customer_bot_phone_request_query",
]
