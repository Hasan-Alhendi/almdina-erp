from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)


_READ_LIKE_TYPES = frozenset({None, "read", "select", "report", "export", "print", "email"})


def _resolved_permission_type(
    ptype: str | None,
    permission_type: str | None,
) -> str | None:
    return ptype if ptype is not None else permission_type


def _query_for(capability: str, user: str | None = None) -> str:
    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return ""
    return "" if doctype_has_capability(capability, user=resolved_user) else "1=0"


def _has_permission(
    *,
    user: str | None,
    ptype: str | None,
    permission_type: str | None,
    view: str,
    create: str | None = None,
    write: str | None = None,
    delete: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    if resolved_user == "Administrator":
        return True

    resolved_type = _resolved_permission_type(ptype, permission_type)
    if resolved_type in _READ_LIKE_TYPES:
        return doctype_has_capability(view, user=resolved_user)

    capability = {
        "create": create,
        "write": write,
        "delete": delete,
    }.get(str(resolved_type or ""))
    if capability:
        return doctype_has_capability(capability, user=resolved_user)
    return False


def customer_query(user: str | None = None) -> str:
    return _query_for(Capability.VIEW_CUSTOMERS, user)


def customer_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    del doc
    return _has_permission(
        user=user,
        ptype=ptype,
        permission_type=permission_type,
        view=Capability.VIEW_CUSTOMERS,
    )


def edge_banding_type_query(user: str | None = None) -> str:
    return _query_for(Capability.VIEW_EDGE_BANDING_TYPES, user)


def edge_banding_type_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    del doc
    return _has_permission(
        user=user,
        ptype=ptype,
        permission_type=permission_type,
        view=Capability.VIEW_EDGE_BANDING_TYPES,
        create=Capability.CREATE_EDGE_BANDING_TYPES,
        write=Capability.EDIT_EDGE_BANDING_TYPES,
        delete=Capability.DELETE_EDGE_BANDING_TYPES,
    )


def production_routing_query(user: str | None = None) -> str:
    return _query_for(Capability.VIEW_PRODUCTION_ROUTINGS, user)


def production_routing_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    del doc
    return _has_permission(
        user=user,
        ptype=ptype,
        permission_type=permission_type,
        view=Capability.VIEW_PRODUCTION_ROUTINGS,
        create=Capability.CREATE_PRODUCTION_ROUTINGS,
        write=Capability.EDIT_PRODUCTION_ROUTINGS,
        delete=Capability.DELETE_PRODUCTION_ROUTINGS,
    )


def factory_settings_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    del doc
    # Direct Desk writes are deliberately denied. Granular settings mutations
    # must go through the protected application service, which validates fields
    # against the corresponding edit capability.
    return _has_permission(
        user=user,
        ptype=ptype,
        permission_type=permission_type,
        view=Capability.VIEW_FACTORY_SETTINGS,
    )


__all__ = [
    "customer_has_permission",
    "customer_query",
    "edge_banding_type_has_permission",
    "edge_banding_type_query",
    "factory_settings_has_permission",
    "production_routing_has_permission",
    "production_routing_query",
]
