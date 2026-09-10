from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.factory.production_routing_management import (
    ProductionRoutingManagementConflict,
    ProductionRoutingManagementError,
    ProductionRoutingManagementPermissionDenied,
    delete_production_routing as delete_routing_use_case,
    save_production_routing as save_routing_use_case,
    set_production_routing_disabled as set_routing_disabled_use_case,
)
from almdina_erp.almdina_erp.application.factory.production_stage_definition_management import (
    ProductionStageDefinitionConflict,
    ProductionStageDefinitionError,
    ProductionStageDefinitionPermissionDenied,
    delete_production_stage_definition as delete_stage_definition_use_case,
    save_production_stage_definition as save_stage_definition_use_case,
    set_production_stage_definition_disabled as set_stage_definition_disabled_use_case,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    granted_capabilities,
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.production_routing_management_repository import (
    FrappeProductionRoutingManagementRepository,
    list_operational_roles,
    list_production_routings,
)
from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_definition_repository import (
    FrappeProductionStageDefinitionRepository,
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
    "Customer": {
        "view": Capability.VIEW_CUSTOMERS,
        "create": Capability.CREATE_CUSTOMERS,
        "edit": Capability.EDIT_CUSTOMERS,
        "delete": Capability.DELETE_CUSTOMERS,
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
    return list_production_routings()


def _routing_permissions() -> dict[str, bool]:
    granted = granted_capabilities()
    return {
        capability: capability in granted
        for capability in _MASTER_DEFINITIONS["Production Routing"].values()
    }


def _routing_summary(routings: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "routings": len(routings),
        "active_routings": sum(not row["disabled"] for row in routings),
        "total_stages": sum(
            sum(bool(stage.get("required", True)) for stage in row["stages"])
            for row in routings
        ),
        "in_flight_orders": sum(
            int(row.get("in_flight_orders") or 0) for row in routings
        ),
    }


def _management_payload(value: Any, *, subject: str = "البيانات") -> Mapping[str, Any]:
    resolved = frappe.parse_json(value) if isinstance(value, str) else value
    if not isinstance(resolved, Mapping):
        frappe.throw(f"{subject} غير صالحة.", frappe.ValidationError)
    return resolved


def _raise_management_error(error: Exception) -> NoReturn:
    if isinstance(
        error,
        (
            ProductionRoutingManagementPermissionDenied,
            ProductionStageDefinitionPermissionDenied,
        ),
    ):
        frappe.throw(str(error), frappe.PermissionError)
    if isinstance(
        error,
        (
            ProductionRoutingManagementConflict,
            ProductionStageDefinitionConflict,
        ),
    ):
        frappe.throw(str(error), frappe.TimestampMismatchError)
    frappe.throw(str(error), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def _stage_catalog() -> list[dict[str, Any]]:
    repository = FrappeProductionStageDefinitionRepository()
    return [
        {
            "name": definition.name,
            "stage_definition": definition.name,
            "stage_type": definition.stage_code,
            "stage_code": definition.stage_code,
            "label": definition.stage_label,
            "stage_label": definition.stage_label,
            "description": definition.description,
            "planning": definition.is_planning_default,
            "is_planning_default": definition.is_planning_default,
            "disabled": definition.disabled,
            "modified": definition.modified,
        }
        for definition in repository.list_definitions()
    ]


def _stage_mutation_response(result: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"stage_catalog": _stage_catalog()}
    if result is not None:
        payload["stage"] = {
            "name": result.name,
            "stage_definition": result.name,
            "stage_type": result.stage_code,
            "stage_code": result.stage_code,
            "label": result.stage_label,
            "stage_label": result.stage_label,
            "description": result.description,
            "planning": result.is_planning_default,
            "is_planning_default": result.is_planning_default,
            "disabled": result.disabled,
            "modified": result.modified,
        }
    return payload


def _edge_rows() -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "Edge Banding Type",
        fields=[
            "name",
            "edge_type_name",
            "english_name",
            "width_cm",
            "thickness_mm",
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
            "routings": frappe.db.count("Production Routing")
            if can_view_routings
            else 0,
            "active_routings": frappe.db.count(
                "Production Routing", {"disabled": 0}
            )
            if can_view_routings
            else 0,
            "edge_types": frappe.db.count("Edge Banding Type")
            if can_view_edges
            else 0,
            "active_edge_types": frappe.db.count(
                "Edge Banding Type", {"disabled": 0}
            )
            if can_view_edges
            else 0,
        },
    }


@frappe.whitelist()
def get_production_routing_console() -> dict[str, Any]:
    permissions = _routing_permissions()
    if not permissions[Capability.VIEW_PRODUCTION_ROUTINGS]:
        frappe.throw(
            _("لا تملك صلاحية عرض مسارات الإنتاج."),
            frappe.PermissionError,
        )
    routings = _routing_rows()
    can_manage = (
        permissions[Capability.CREATE_PRODUCTION_ROUTINGS]
        or permissions[Capability.EDIT_PRODUCTION_ROUTINGS]
    )
    return {
        "permissions": permissions,
        "routings": routings,
        "operational_roles": list_operational_roles() if can_manage else [],
        "stage_catalog": _stage_catalog(),
        "audit": _audit_rows(["Production Routing"], limit=60),
        "summary": _routing_summary(routings),
    }


@frappe.whitelist()
def save_production_routing(payload: Any) -> dict[str, Any]:
    try:
        stage_repository = FrappeProductionStageDefinitionRepository()
        result = save_routing_use_case(
            FrappeProductionRoutingManagementRepository(),
            stage_repository,
            frozenset(granted_capabilities()),
            _management_payload(payload, subject="بيانات مسار الإنتاج"),
        )
    except (
        ProductionRoutingManagementError,
        ProductionRoutingManagementPermissionDenied,
        ProductionStageDefinitionError,
    ) as error:
        _raise_management_error(error)
    return dict(result)


@frappe.whitelist()
def set_production_routing_disabled(
    name: str,
    disabled: int | bool,
    expected_modified: str,
) -> dict[str, Any]:
    try:
        result = set_routing_disabled_use_case(
            FrappeProductionRoutingManagementRepository(),
            frozenset(granted_capabilities()),
            name=name,
            disabled=disabled,
            expected_modified=expected_modified,
        )
    except (
        ProductionRoutingManagementError,
        ProductionRoutingManagementPermissionDenied,
    ) as error:
        _raise_management_error(error)
    return dict(result)


@frappe.whitelist()
def delete_production_routing(name: str, expected_modified: str) -> dict[str, Any]:
    try:
        delete_routing_use_case(
            FrappeProductionRoutingManagementRepository(),
            frozenset(granted_capabilities()),
            name=name,
            expected_modified=expected_modified,
        )
    except (
        ProductionRoutingManagementError,
        ProductionRoutingManagementPermissionDenied,
    ) as error:
        _raise_management_error(error)
    return {"name": str(name or "").strip(), "deleted": True}


@frappe.whitelist()
def save_production_stage_definition(payload: Any) -> dict[str, Any]:
    try:
        result = save_stage_definition_use_case(
            FrappeProductionStageDefinitionRepository(),
            frozenset(granted_capabilities()),
            _management_payload(payload, subject="بيانات المرحلة"),
        )
    except (
        ProductionStageDefinitionError,
        ProductionStageDefinitionPermissionDenied,
    ) as error:
        _raise_management_error(error)
    return _stage_mutation_response(result)


@frappe.whitelist()
def set_production_stage_definition_disabled(
    name: str,
    disabled: int | bool,
    expected_modified: str,
) -> dict[str, Any]:
    try:
        result = set_stage_definition_disabled_use_case(
            FrappeProductionStageDefinitionRepository(),
            frozenset(granted_capabilities()),
            name=name,
            disabled=disabled,
            expected_modified=expected_modified,
        )
    except (
        ProductionStageDefinitionError,
        ProductionStageDefinitionPermissionDenied,
    ) as error:
        _raise_management_error(error)
    return _stage_mutation_response(result)


@frappe.whitelist()
def delete_production_stage_definition(
    name: str,
    expected_modified: str,
) -> dict[str, Any]:
    try:
        delete_stage_definition_use_case(
            FrappeProductionStageDefinitionRepository(),
            frozenset(granted_capabilities()),
            name=name,
            expected_modified=expected_modified,
        )
    except (
        ProductionStageDefinitionError,
        ProductionStageDefinitionPermissionDenied,
    ) as error:
        _raise_management_error(error)
    return {
        "name": str(name or "").strip(),
        "deleted": True,
        "stage_catalog": _stage_catalog(),
    }


@frappe.whitelist()
def set_master_data_disabled(
    doctype: str,
    name: str,
    disabled: int | bool,
) -> dict[str, Any]:
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
    return {
        "doctype": doctype,
        "name": target_name,
        "disabled": int(document.disabled or 0),
    }


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
    "delete_production_routing",
    "delete_production_stage_definition",
    "get_master_data_console",
    "get_production_routing_console",
    "save_production_routing",
    "save_production_stage_definition",
    "search_operational_roles",
    "set_master_data_disabled",
    "set_production_routing_disabled",
    "set_production_stage_definition_disabled",
]
