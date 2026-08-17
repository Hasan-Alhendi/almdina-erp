from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    DRAWING_CAPABILITIES,
    PLANNING_CAPABILITIES,
    PRODUCTION_CAPABILITIES,
    PRODUCTION_OPERATOR_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    PRE_PRODUCTION_ORDER_STATUSES,
    normalize_order_status,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)


_ORDER_AUTHORING_CAPABILITIES = frozenset(
    {
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.CREATE_ORDER_REVISION,
        Capability.SUBMIT_ORDER,
    }
)
# Global order visibility is independent from every operational action grant.
# Supervising, dispatching, reassigning, reporting, or editing must never widen
# an operator's data scope unless this dedicated capability is explicitly set.
_SCOPE_OVERRIDING_CAPABILITIES = frozenset({Capability.VIEW_ALL_ORDERS})
_FLOOR_WORKER_CAPABILITIES = frozenset(
    {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
    }
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
_WORKER_SCOPED_CAPABILITIES = (
    PRODUCTION_OPERATOR_CAPABILITIES | PLANNING_CAPABILITIES | DRAWING_CAPABILITIES
)

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
    if _has_any(user, _SCOPE_OVERRIDING_CAPABILITIES):
        return False
    if _has_any(user, _FLOOR_WORKER_CAPABILITIES | _WORKER_SCOPED_CAPABILITIES):
        return True
    if _has_any(user, _ORDER_AUTHORING_CAPABILITIES):
        return False
    return False


def _pre_production_status_sql() -> str:
    return ", ".join(
        frappe.db.escape(status)
        for status in sorted(PRE_PRODUCTION_ORDER_STATUSES)
    )


def _row_value(row: Any, fieldname: str) -> Any:
    if isinstance(row, dict):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


def _dispatched_order_row(order_name: str) -> Any | None:
    """Return the order only when it already reached the production floor."""

    row = frappe.db.get_value(
        "Door Cutting Order",
        order_name,
        ["status", "current_production_stage"],
        as_dict=True,
    )
    if not row:
        return None
    status = normalize_order_status(_row_value(row, "status"))
    stage = str(_row_value(row, "current_production_stage") or "").strip()
    if status in PRE_PRODUCTION_ORDER_STATUSES and not stage:
        return None
    return row


def _assigned_order_subquery(user: str) -> str:
    return _worker_visible_orders_subquery(user)


def _worker_operational_roles(user: str) -> tuple[str, ...]:
    """Resolve operational roles through the shop-floor authorization gateway."""

    from almdina_erp.almdina_erp.infrastructure.frappe import (
        shop_floor_authorization,
    )

    return shop_floor_authorization.roles_of(user)


def _resolve_stage_operational_role(
    order_name: str,
    stage: Any,
) -> str | None:
    role = str(_row_value(stage, "operational_role") or "").strip()
    if role:
        return role
    stage_type = str(_row_value(stage, "stage_type") or "").strip()
    if not stage_type:
        return None
    production_path = frappe.db.get_value(
        "Door Cutting Order",
        order_name,
        "production_path",
    )
    if not production_path:
        return None
    from almdina_erp.almdina_erp.infrastructure.frappe import (
        production_routing_repository,
    )

    try:
        route = production_routing_repository.get_route(str(production_path))
        return str(route.stage(stage_type).operational_role or "").strip() or None
    except (ValueError, AttributeError):
        return None


def _worker_actionable_orders_subquery(user: str) -> str:
    roles = _worker_operational_roles(user)
    user_sql = frappe.db.escape(user)
    if not roles:
        return " select null as door_cutting_order where 1=0"
    role_sql = ", ".join(frappe.db.escape(role) for role in roles)
    pre_production_sql = _pre_production_status_sql()
    return (
        " select distinct ps.door_cutting_order"
        " from `tabProduction Stage` ps"
        " inner join `tabDoor Cutting Order` dco on dco.name = ps.door_cutting_order"
        f" where ps.name = dco.current_production_stage"
        f" and ifnull(dco.current_production_stage, '') != ''"
        f" and dco.status not in ({pre_production_sql})"
        f" and ps.assigned_to = {user_sql}"
        f" and ps.operational_role in ({role_sql})"
    )


def _worker_completed_orders_subquery(user: str) -> str:
    user_sql = frappe.db.escape(user)
    pre_production_sql = _pre_production_status_sql()
    return (
        " select distinct ps.door_cutting_order"
        " from `tabProduction Stage` ps"
        " inner join `tabDoor Cutting Order` dco on dco.name = ps.door_cutting_order"
        f" where ps.assigned_to = {user_sql}"
        " and ps.status = 'Completed'"
        " and ifnull(ps.piece_label, '') = ''"
        f" and dco.status not in ({pre_production_sql})"
    )


def _worker_visible_orders_subquery(user: str) -> str:
    return (
        _worker_actionable_orders_subquery(user)
        + " union "
        + _worker_completed_orders_subquery(user)
    )


def worker_can_view_order(user: str, order_name: str | None) -> bool:
    """Workers may read only orders that need their stage work or they finished."""

    if not order_name:
        return False
    if not _requires_assigned_scope(user):
        return True

    order = _dispatched_order_row(order_name)
    if not order:
        return False

    if frappe.db.exists(
        "Production Stage",
        {
            "door_cutting_order": order_name,
            "assigned_to": user,
            "status": "Completed",
            "piece_label": ["is", "not set"],
        },
    ):
        return True

    current_stage_name = str(
        _row_value(order, "current_production_stage") or ""
    ).strip()
    if not current_stage_name:
        return False

    stage = frappe.db.get_value(
        "Production Stage",
        current_stage_name,
        ["assigned_to", "operational_role", "stage_type"],
        as_dict=True,
    )
    if not stage or _row_value(stage, "assigned_to") != user:
        return False

    role = _resolve_stage_operational_role(order_name, stage)
    if not role:
        return False
    return role in set(_worker_operational_roles(user))


def _assigned_order_exists(user: str, order_name: str | None) -> bool:
    return worker_can_view_order(user, order_name)


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
    "worker_can_view_order",
]
