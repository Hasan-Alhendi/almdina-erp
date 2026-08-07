from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    granted_capabilities,
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.role_repository import (
    FrappeRoleRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
)


_MASTER_DEFINITIONS = {
    "Production Routing": {
        "view": Capability.VIEW_PRODUCTION_ROUTINGS,
        "create": Capability.CREATE_PRODUCTION_ROUTINGS,
        "edit": Capability.EDIT_PRODUCTION_ROUTINGS,
        "delete": Capability.DELETE_PRODUCTION_ROUTINGS,
    },
    "Edge Banding Type": {
        "view": Capability.VIEW_EDGE_BANDING_TYPES,
        "create": Capability.CREATE_EDGE_BANDING_TYPES,
        "edit": Capability.EDIT_EDGE_BANDING_TYPES,
        "delete": Capability.DELETE_EDGE_BANDING_TYPES,
    },
}
_role_repository = FrappeRoleRepository()


def _definition(doctype: str) -> dict[str, str]:
    try:
        return _MASTER_DEFINITIONS[str(doctype or "")]
    except KeyError:
        frappe.throw(_("Unsupported factory master data type."), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def _permission_flags() -> dict[str, bool]:
    granted = granted_capabilities()
    return {
        capability: capability in granted
        for definition in _MASTER_DEFINITIONS.values()
        for capability in definition.values()
    }


def _eligible_role_rows(search: str = "", limit: int = 100) -> list[dict[str, Any]]:
    roles = _role_repository.list_roles(
        search=str(search or "").strip(),
        enabled=True,
        limit=max(1, min(cint(limit or 100), 200)),
    )
    return [
        {
            "name": str(role["name"]),
            "description": str(role.get("description") or ""),
            "assigned_users": cint(role.get("assigned_users")),
        }
        for role in roles
        if role.get("desk_access") and role.get("is_almdina_role")
    ]


@frappe.whitelist()
def get_eligible_routing_roles(search: str = "") -> list[dict[str, Any]]:
    """Return enabled, Desk-capable roles managed by Almdina."""

    require_doctype_capability(Capability.VIEW_PRODUCTION_ROUTINGS)
    return _eligible_role_rows(search)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_eligible_roles(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None = None,
) -> list[list[str]]:
    """Link query for dynamic routing roles without general role access."""

    del doctype, searchfield, filters
    require_doctype_capability(Capability.VIEW_PRODUCTION_ROUTINGS)
    rows = _eligible_role_rows(
        txt,
        limit=max(1, min(cint(page_len or 20) + cint(start), 200)),
    )
    sliced = rows[cint(start) : cint(start) + max(1, cint(page_len or 20))]
    return [[row["name"], row["description"] or row["name"]] for row in sliced]


# Compatibility alias used by older form assets. It now has the same strict,
# dynamic filtering and contains no role catalog or stage defaults.
search_operational_roles = search_eligible_roles


def _routing_rows() -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "Production Routing",
        fields=["name", "routing_name", "disabled", "modified", "modified_by"],
        order_by="disabled asc, routing_name asc",
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        stages = frappe.get_all(
            "Production Routing Stage",
            filters={"parent": row.name, "parenttype": "Production Routing"},
            fields=[
                "sequence",
                "stage_type",
                "department_label",
                "eligible_roles_json",
                "eligible_roles_display",
                "operational_role",
                "required",
                "auto_complete_if_not_applicable",
            ],
            order_by="sequence asc, idx asc",
        )
        stage_payload: list[dict[str, Any]] = []
        for stage in stages:
            try:
                roles = decode_eligible_roles(
                    stage.eligible_roles_json,
                    legacy_role=stage.operational_role,
                )
            except ValueError:
                roles = ()
            stage_payload.append(
                {
                    **dict(stage),
                    "eligible_roles": list(roles),
                    "operational_role": roles[0] if roles else "",
                }
            )
        result.append(
            {
                "name": str(row.name),
                "label": row.routing_name or row.name,
                "disabled": bool(row.disabled),
                "modified": row.modified,
                "modified_by": row.modified_by,
                "stages": stage_payload,
            }
        )
    return result


def _edge_rows() -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "Edge Banding Type",
        fields=[
            "name",
            "edge_type_name",
            "english_name",
            "width_cm",
            "thickness_mm",
            "edge_color",
            "finish_type",
            "application_method",
            "rate_usd_per_meter",
            "disabled",
            "modified",
            "modified_by",
        ],
        order_by="disabled asc, edge_type_name asc",
    )
    return [
        {
            "name": str(row.name),
            "label": row.edge_type_name or row.name,
            "english_name": row.english_name or "",
            "width_cm": flt(row.width_cm),
            "thickness_mm": flt(row.thickness_mm, 3),
            "edge_color": row.edge_color or "",
            "finish_type": row.finish_type or "",
            "application_method": row.application_method or "",
            "rate_usd_per_meter": flt(row.rate_usd_per_meter),
            "disabled": bool(row.disabled),
            "modified": row.modified,
            "modified_by": row.modified_by,
        }
        for row in rows
    ]


def _audit_rows(allowed_doctypes: list[str], limit: int = 40) -> list[dict[str, Any]]:
    if not allowed_doctypes:
        return []
    rows = frappe.get_all(
        "Almdina Master Data Audit",
        filters={"target_doctype": ["in", allowed_doctypes]},
        fields=[
            "name",
            "target_doctype",
            "target_name",
            "action",
            "changed_by",
            "changed_on",
            "changed_fields",
            "source",
        ],
        order_by="changed_on desc",
        limit_page_length=max(1, min(cint(limit or 40), 100)),
    )
    return [dict(row) for row in rows]


@frappe.whitelist()
def get_master_data_console() -> dict[str, Any]:
    permissions = _permission_flags()
    can_view_routings = permissions[Capability.VIEW_PRODUCTION_ROUTINGS]
    can_view_edges = permissions[Capability.VIEW_EDGE_BANDING_TYPES]
    if not can_view_routings and not can_view_edges:
        frappe.throw(_("You do not have permission to view factory master data."), frappe.PermissionError)

    allowed_doctypes = []
    if can_view_routings:
        allowed_doctypes.append("Production Routing")
    if can_view_edges:
        allowed_doctypes.append("Edge Banding Type")
    return {
        "permissions": permissions,
        "routings": _routing_rows() if can_view_routings else [],
        "edge_types": _edge_rows() if can_view_edges else [],
        "audit": _audit_rows(allowed_doctypes),
        "summary": {
            "routings": frappe.db.count("Production Routing") if can_view_routings else 0,
            "active_routings": frappe.db.count("Production Routing", {"disabled": 0}) if can_view_routings else 0,
            "edge_types": frappe.db.count("Edge Banding Type") if can_view_edges else 0,
            "active_edge_types": frappe.db.count("Edge Banding Type", {"disabled": 0}) if can_view_edges else 0,
        },
    }


@frappe.whitelist()
def set_master_data_disabled(doctype: str, name: str, disabled: int | bool) -> dict[str, Any]:
    definition = _definition(doctype)
    require_doctype_capability(
        definition["edit"],
        message=_("You do not have permission to modify this master data."),
    )
    target_name = str(name or "").strip()
    frappe.db.sql(
        f"select name from `tab{doctype}` where name = %s for update",
        (target_name,),
    )
    document = frappe.get_doc(doctype, target_name)
    document.disabled = cint(disabled) and 1 or 0
    document.save()
    return {"doctype": doctype, "name": target_name, "disabled": int(document.disabled or 0)}


@frappe.whitelist()
def delete_master_data_record(doctype: str, name: str) -> dict[str, Any]:
    definition = _definition(doctype)
    require_doctype_capability(
        definition["delete"],
        message=_("You do not have permission to delete this master data."),
    )
    target_name = str(name or "").strip()
    frappe.delete_doc(doctype, target_name, ignore_permissions=False)
    return {"doctype": doctype, "name": target_name, "deleted": True}


@frappe.whitelist()
def can_open_master_data(doctype: str) -> bool:
    definition = _definition(doctype)
    return doctype_has_capability(definition["view"])


__all__ = [
    "can_open_master_data",
    "delete_master_data_record",
    "get_eligible_routing_roles",
    "get_master_data_console",
    "search_eligible_roles",
    "search_operational_roles",
    "set_master_data_disabled",
]
