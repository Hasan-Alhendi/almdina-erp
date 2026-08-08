from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    PRODUCTION_CAPABILITIES,
    PRODUCTION_OPERATOR_CAPABILITIES,
    PRODUCTION_SUPERVISOR_CAPABILITIES,
    REPORTING_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)


_CONTROL_CENTER_BROAD_CAPABILITIES = frozenset(
    {
        Capability.APPROVE_ORDER,
        Capability.REJECT_ORDER,
        Capability.ARCHIVE_APPROVED_PLAN,
        Capability.CREATE_REPLACEMENT,
        Capability.APPROVE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
    }
)
_COST_BROAD_CAPABILITIES = frozenset(
    {
        Capability.VIEW_COSTS,
        Capability.EDIT_COST_SETTINGS,
        Capability.EDIT_SPECIAL_PRICE,
        Capability.APPROVE_SPECIAL_PRICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
    }
)
_BROAD_ORDER_SCOPE_CAPABILITIES = frozenset(
    {
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.CREATE_ORDER_REVISION,
        Capability.SUBMIT_ORDER,
        Capability.APPROVE_ORDER,
        Capability.REJECT_ORDER,
        Capability.CANCEL_ORDER,
    }
    | _CONTROL_CENTER_BROAD_CAPABILITIES
    | _COST_BROAD_CAPABILITIES
    | PRODUCTION_SUPERVISOR_CAPABILITIES
    | REPORTING_CAPABILITIES
)
_STAGE_READ_CAPABILITIES = frozenset(PRODUCTION_CAPABILITIES) | frozenset(
    {
        Capability.RECORD_INCIDENT,
        Capability.CREATE_REPLACEMENT,
        Capability.VIEW_OPERATIONAL_REPORTS,
        Capability.VIEW_FINANCIAL_REPORTS,
    }
)
_READ_PERMISSION_TYPES = frozenset({None, "read", "select"})
_MUTATING_PERMISSION_TYPES = frozenset({"create", "write", "delete"})

_DCO_PERMISSION_CAPABILITIES = {
    definition.permission_type: capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.applies_to == "Door Cutting Order"
}
_REPLACEMENT_PERMISSION_CAPABILITIES = {
    definition.permission_type: capability
    for capability, definition in CAPABILITY_CATALOG.items()
    if definition.applies_to == "Replacement Piece"
}


def _resolved_permission_type(
    ptype: str | None,
    permission_type: str | None,
) -> str | None:
    """Accept Frappe v16's ``ptype`` and the historical local test keyword."""

    return ptype if ptype is not None else permission_type


def _has(user: str, capability: str) -> bool:
    return doctype_has_capability(capability, user=user)


def _has_any(user: str, capabilities: frozenset[str]) -> bool:
    return any(_has(user, capability) for capability in capabilities)


def _requires_assigned_scope(user: str) -> bool:
    """Return whether reads must stay inside stages assigned to the user."""

    if user in {"Guest", "Administrator"}:
        return False
    if _has_any(user, _BROAD_ORDER_SCOPE_CAPABILITIES):
        return False
    return _has_any(user, PRODUCTION_OPERATOR_CAPABILITIES)


def _assigned_order_subquery(user: str) -> str:
    return (
        " select distinct door_cutting_order from `tabProduction Stage`"
        f" where assigned_to = {frappe.db.escape(user)}"
    )


def _assigned_order_exists(user: str, order_name: str | None) -> bool:
    if not order_name:
        return False
    return bool(
        frappe.db.exists(
            "Production Stage",
            {
                "door_cutting_order": order_name,
                "assigned_to": user,
            },
        )
    )


def _scoped_read_decision(
    *,
    user: str,
    required_capability: str,
    order_name: str | None,
) -> bool:
    if user == "Administrator":
        return True
    if user == "Guest" or not _has(user, required_capability):
        return False
    if not _requires_assigned_scope(user):
        return True
    return _assigned_order_exists(user, order_name)


def door_cutting_order_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    if not _has(user, Capability.VIEW_ORDERS):
        return "1=0"
    if not _requires_assigned_scope(user):
        return ""
    return (
        "`tabDoor Cutting Order`.name in ("
        + _assigned_order_subquery(user)
        + ")"
    )


def production_stage_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    if not _has_any(user, _STAGE_READ_CAPABILITIES):
        return "1=0"
    if not _requires_assigned_scope(user):
        return ""
    return f"`tabProduction Stage`.assigned_to = {frappe.db.escape(user)}"


def production_incident_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    return "" if _has(user, Capability.VIEW_PRODUCTION_INCIDENTS) else "1=0"


def cutting_plan_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    if not _has(user, Capability.VIEW_CUTTING_PLAN):
        return "1=0"
    if not _requires_assigned_scope(user):
        return ""
    return (
        "`tabCutting Plan`.door_cutting_order in ("
        + _assigned_order_subquery(user)
        + ")"
    )


def replacement_piece_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    if not _has(user, Capability.VIEW_REPLACEMENTS):
        return "1=0"
    if not _requires_assigned_scope(user):
        return ""
    return (
        "`tabReplacement Piece`.door_cutting_order in ("
        + _assigned_order_subquery(user)
        + ")"
    )


def door_cutting_order_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    resolved_type = _resolved_permission_type(ptype, permission_type)

    if resolved_user == "Administrator":
        return True
    if resolved_type in _READ_PERMISSION_TYPES:
        return _scoped_read_decision(
            user=resolved_user,
            required_capability=Capability.VIEW_ORDERS,
            order_name=getattr(doc, "name", None),
        )
    if resolved_type == "delete":
        return False

    required = _DCO_PERMISSION_CAPABILITIES.get(str(resolved_type or ""))
    if required:
        return _has(resolved_user, required)
    return resolved_type not in _MUTATING_PERMISSION_TYPES


def production_stage_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    resolved_type = _resolved_permission_type(ptype, permission_type)

    if resolved_user == "Administrator":
        return True
    if resolved_type in _READ_PERMISSION_TYPES:
        if not _has_any(resolved_user, _STAGE_READ_CAPABILITIES):
            return False
        if not _requires_assigned_scope(resolved_user):
            return True
        return bool(getattr(doc, "assigned_to", None) == resolved_user)
    if resolved_type in _MUTATING_PERMISSION_TYPES:
        return False
    return True


def production_incident_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    del doc
    resolved_user = user or frappe.session.user
    resolved_type = _resolved_permission_type(ptype, permission_type)
    if resolved_user == "Administrator":
        return True
    if resolved_type in _READ_PERMISSION_TYPES:
        return _has(resolved_user, Capability.VIEW_PRODUCTION_INCIDENTS)
    if resolved_type in _MUTATING_PERMISSION_TYPES:
        # Production incidents are created/updated through protected commands,
        # never through unrestricted Desk CRUD.
        return False
    return True


def cutting_plan_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    resolved_type = _resolved_permission_type(ptype, permission_type)

    if resolved_user == "Administrator":
        return True
    if resolved_type in _READ_PERMISSION_TYPES:
        return _scoped_read_decision(
            user=resolved_user,
            required_capability=Capability.VIEW_CUTTING_PLAN,
            order_name=getattr(doc, "door_cutting_order", None),
        )
    if resolved_type in _MUTATING_PERMISSION_TYPES:
        return False
    return True


def replacement_piece_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    resolved_type = _resolved_permission_type(ptype, permission_type)

    if resolved_user == "Administrator":
        return True
    if resolved_type in _READ_PERMISSION_TYPES:
        return _scoped_read_decision(
            user=resolved_user,
            required_capability=Capability.VIEW_REPLACEMENTS,
            order_name=getattr(doc, "door_cutting_order", None),
        )
    if resolved_type in _MUTATING_PERMISSION_TYPES:
        return False

    required = _REPLACEMENT_PERMISSION_CAPABILITIES.get(str(resolved_type or ""))
    if required:
        return _has(resolved_user, required)
    return True


__all__ = [
    "cutting_plan_has_permission",
    "cutting_plan_query",
    "door_cutting_order_has_permission",
    "door_cutting_order_query",
    "production_incident_has_permission",
    "production_incident_query",
    "production_stage_has_permission",
    "production_stage_query",
    "replacement_piece_has_permission",
    "replacement_piece_query",
]
