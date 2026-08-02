from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
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
_READ_PERMISSION_TYPES = frozenset({None, "read", "select"})


def _resolved_permission_type(
    ptype: str | None,
    permission_type: str | None,
) -> str | None:
    """Accept Frappe v16's ``ptype`` and the historical local test keyword."""

    return ptype if ptype is not None else permission_type


def _has_any(user: str, capabilities: frozenset[str]) -> bool:
    return any(
        doctype_has_capability(capability, user=user)
        for capability in capabilities
    )


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
        " and stage_type in ('Sharyoun','Drawing','CNC','Sanding')"
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
                "stage_type": ["in", ["Sharyoun", "Drawing", "CNC", "Sanding"]],
            },
        )
    )


def _assigned_read_decision(
    *,
    user: str,
    permission_type: str | None,
    order_name: str | None,
) -> bool:
    # Frappe v16 requires has_permission hooks to return an explicit boolean.
    # Standard DocPerm checks run separately, so non-read actions only need this
    # hook to avoid adding an extra restriction.
    if permission_type not in _READ_PERMISSION_TYPES:
        return True
    if user == "Guest":
        return False
    if not _requires_assigned_scope(user):
        return True
    return _assigned_order_exists(user, order_name)


def door_cutting_order_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not _requires_assigned_scope(user):
        return ""
    return (
        "`tabDoor Cutting Order`.name in ("
        + _assigned_order_subquery(user)
        + ")"
    )


def production_stage_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not _requires_assigned_scope(user):
        return ""
    return f"`tabProduction Stage`.assigned_to = {frappe.db.escape(user)}"


def cutting_plan_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not _requires_assigned_scope(user):
        return ""
    return (
        "`tabCutting Plan`.door_cutting_order in ("
        + _assigned_order_subquery(user)
        + ")"
    )


def replacement_piece_query(user: str | None = None) -> str:
    user = user or frappe.session.user
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
    return _assigned_read_decision(
        user=resolved_user,
        permission_type=_resolved_permission_type(ptype, permission_type),
        order_name=getattr(doc, "name", None),
    )


def production_stage_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    resolved_type = _resolved_permission_type(ptype, permission_type)
    if resolved_type not in _READ_PERMISSION_TYPES:
        return True
    if resolved_user == "Guest":
        return False
    if not _requires_assigned_scope(resolved_user):
        return True
    return bool(getattr(doc, "assigned_to", None) == resolved_user)


def cutting_plan_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    return _assigned_read_decision(
        user=resolved_user,
        permission_type=_resolved_permission_type(ptype, permission_type),
        order_name=getattr(doc, "door_cutting_order", None),
    )


def replacement_piece_has_permission(
    doc: Any,
    user: str | None = None,
    ptype: str | None = None,
    permission_type: str | None = None,
) -> bool:
    resolved_user = user or frappe.session.user
    return _assigned_read_decision(
        user=resolved_user,
        permission_type=_resolved_permission_type(ptype, permission_type),
        order_name=getattr(doc, "door_cutting_order", None),
    )


__all__ = [
    "cutting_plan_has_permission",
    "cutting_plan_query",
    "door_cutting_order_has_permission",
    "door_cutting_order_query",
    "production_stage_has_permission",
    "production_stage_query",
    "replacement_piece_has_permission",
    "replacement_piece_query",
]
