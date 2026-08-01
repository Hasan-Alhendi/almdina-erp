from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    ADMINISTRATION_CAPABILITIES,
    COSTING_CAPABILITIES,
    PRODUCTION_OPERATOR_CAPABILITIES,
    PRODUCTION_SUPERVISOR_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)


_BROAD_ORDER_SCOPE_CAPABILITIES = frozenset(
    {
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.CREATE_ORDER_REVISION,
        Capability.SUBMIT_ORDER,
        Capability.APPROVE_ORDER,
        Capability.CANCEL_ORDER,
    }
    | PRODUCTION_SUPERVISOR_CAPABILITIES
    | COSTING_CAPABILITIES
    | ADMINISTRATION_CAPABILITIES
)


def _has_any(user: str, capabilities: frozenset[str]) -> bool:
    return any(
        doctype_has_capability(capability, user=user)
        for capability in capabilities
    )


def _requires_assigned_scope(user: str) -> bool:
    """Return whether reads must stay inside stages assigned to the user.

    Operational department Roles remain valid assignment eligibility metadata,
    but they never decide data visibility. The scope is derived from Permission
    Types and the actual ``assigned_to`` relationship.
    """

    if user in {"Guest", "Administrator"}:
        return False
    if _has_any(user, _BROAD_ORDER_SCOPE_CAPABILITIES):
        return False
    return _has_any(user, PRODUCTION_OPERATOR_CAPABILITIES)


def door_cutting_order_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if not _requires_assigned_scope(user):
        return ""
    return (
        "`tabDoor Cutting Order`.name in ("
        " select distinct door_cutting_order from `tabProduction Stage`"
        f" where assigned_to = {frappe.db.escape(user)}"
        " and stage_type in ('Sharyoun','Drawing','CNC','Sanding')"
        ")"
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
        " select distinct door_cutting_order from `tabProduction Stage`"
        f" where assigned_to = {frappe.db.escape(user)}"
        " and stage_type in ('Sharyoun','Drawing','CNC','Sanding')"
        ")"
    )


__all__ = [
    "cutting_plan_query",
    "door_cutting_order_query",
    "production_stage_query",
]
