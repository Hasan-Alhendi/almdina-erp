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
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
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


def _definition(doctype: str) -> dict[str, str]:
    try:
        return _MASTER_DEFINITIONS[str(doctype or "")]
    except KeyError:
        frappe.throw(
            _("نوع البيانات الأساسية المطلوب غير مدعوم في إدارة المعمل."),
            frappe.ValidationError,
        )
    raise AssertionError("frappe.throw must interrupt execution")


def _permission_flags() -> dict[str, bool]:
    granted = granted_capabilities()
    return {
        capability: capability in granted
        for definition in _MASTER_DEFINITIONS.values()
        for capability in definition.values()
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_operational_roles(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict[str, Any] | None = None,
) -> list[list[str]]:
    """Role link query for routing editors without general role administration."""

    del doctype, searchfield, filters
    require_doctype_capability(
        Capability.VIEW_PRODUCTION_ROUTINGS,
        message=_("لا تملك صلاحية عرض مسارات الإنتاج."),
    )
    role_filters: list[list[Any]] = [
        ["Role", "name", "like", f"%{txt or ''}%"],
        ["Role", "name", "not in", sorted(PROTECTED_SYSTEM_ROLES)],
    ]
    role_meta = frappe.get_meta("Role")
    if role_meta.has_field("disabled"):
        role_filters.append(["Role", "disabled", "=", 0])
    rows = frappe.get_all(
        "Role",
        filters=role_filters,
        fields=["name"],
        order_by="name asc",
        limit_start=max(0, cint(start)),
        limit_page_length=max(1, min(cint(page_len or 20), 100)),
    )
    return [[str(row.name), str(row.name)] for row in rows]


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
                "operational_role",
                "required",
                "auto_complete_if_not_applicable",
            ],
            order_by="sequence asc, idx asc",
        )
        result.append(
            {
                "name": str(row.name),
                "label": row.routing_name or row.name,
                "disabled": bool(row.disabled),
                "modified": row.modified,
                "modified_by": row.modified_by,
                "stages": [dict(stage) for stage in stages],
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
        frappe.throw(
            _("لا تملك صلاحية عرض البيانات الأساسية للمعمل."),
            frappe.PermissionError,
        )

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
        message=_("لا تملك صلاحية تعديل هذا النوع من البيانات الأساسية."),
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
        message=_("لا تملك صلاحية حذف هذا النوع من البيانات الأساسية."),
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
    "get_master_data_console",
    "search_operational_roles",
    "set_master_data_disabled",
]
