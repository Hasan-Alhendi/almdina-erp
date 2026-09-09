from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.application.factory.production_routing_management import (
    ProductionRoutingManagementConflict,
    ProductionRoutingManagementError,
    SaveProductionRoutingCommand,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)
from almdina_erp.almdina_erp.infrastructure.frappe.production_workflow_stage_repository import (
    ensure_workflow_stage,
    workflow_stage_name,
)


def _workflow_stage_definitions(names: set[str]) -> dict[str, Any]:
    resolved = sorted(name for name in names if name)
    if not resolved:
        return {}
    rows = frappe.get_all(
        "Production Workflow Stage",
        filters={"name": ["in", resolved]},
        fields=["name", "stage_code", "stage_label", "kanban_order", "disabled"],
    )
    return {str(row.name): row for row in rows}


def _stage_payload(row: Any, definitions: Mapping[str, Any]) -> dict[str, Any]:
    workflow_stage = str(row.workflow_stage or "").strip()
    definition = definitions.get(workflow_stage)
    stage_code = str(getattr(definition, "stage_code", None) or row.stage_type or workflow_stage)
    stage_label = str(getattr(definition, "stage_label", None) or row.department_label or stage_code)
    return {
        "sequence": cint(row.sequence),
        "workflow_stage": workflow_stage,
        "stage_type": stage_code,
        "department_label": stage_label,
        "operational_role": str(row.operational_role or ""),
        "required": bool(cint(row.required)),
        "is_planning_stage": bool(cint(row.is_planning_stage)),
    }


def list_workflow_stages() -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "Production Workflow Stage",
        filters={"disabled": 0},
        fields=["name", "stage_code", "stage_label", "kanban_order", "disabled"],
        order_by="kanban_order asc, stage_label asc, name asc",
    )
    return [
        {
            "workflow_stage": str(row.name),
            "stage_type": str(row.stage_code or ""),
            "stage_code": str(row.stage_code or ""),
            "label": str(row.stage_label or row.stage_code or row.name),
            "stage_label": str(row.stage_label or row.stage_code or row.name),
            "kanban_order": cint(row.kanban_order),
            "disabled": bool(cint(row.disabled)),
        }
        for row in rows
    ]


def list_production_routings() -> list[dict[str, Any]]:
    """Return the routing console projection without one query per route or stage."""

    rows = frappe.get_all(
        "Production Routing",
        fields=["name", "routing_name", "disabled", "modified", "modified_by"],
        order_by="disabled asc, routing_name asc",
    )
    names = [str(row.name) for row in rows]
    raw_stages: list[Any] = []
    if names:
        raw_stages = frappe.get_all(
            "Production Routing Stage",
            filters={
                "parent": ["in", names],
                "parenttype": "Production Routing",
            },
            fields=[
                "parent",
                "sequence",
                "workflow_stage",
                "stage_type",
                "department_label",
                "operational_role",
                "required",
                "is_planning_stage",
            ],
            order_by="parent asc, sequence asc, idx asc",
        )
    definitions = _workflow_stage_definitions(
        {str(stage.workflow_stage or "").strip() for stage in raw_stages}
    )
    stages_by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for stage in raw_stages:
        stages_by_route[str(stage.parent)].append(_stage_payload(stage, definitions))

    in_flight_counts: dict[str, int] = {}
    if names:
        active_rows = frappe.get_all(
            "Door Cutting Order",
            filters={
                "production_path": ["in", names],
                "current_production_stage": ["is", "set"],
                "status": ["not in", ["Delivered", "Cancelled"]],
            },
            fields=[
                "production_path",
                {"COUNT": "name", "as": "order_count"},
            ],
            group_by="production_path",
        )
        in_flight_counts = {
            str(row.production_path): cint(row.order_count) for row in active_rows
        }

    return [
        {
            "name": str(row.name),
            "label": str(row.routing_name or row.name),
            "disabled": bool(cint(row.disabled)),
            "modified": row.modified,
            "modified_by": str(row.modified_by or ""),
            "in_flight_orders": in_flight_counts.get(str(row.name), 0),
            "stages": stages_by_route.get(str(row.name), []),
        }
        for row in rows
    ]


def list_operational_roles() -> list[str]:
    filters: list[list[Any]] = [
        ["Role", "name", "not in", sorted(PROTECTED_SYSTEM_ROLES)],
    ]
    role_meta = frappe.get_meta("Role")
    if role_meta.has_field("disabled"):
        filters.append(["Role", "disabled", "=", 0])
    rows = frappe.get_all(
        "Role",
        filters=filters,
        fields=["name"],
        order_by="name asc",
        limit_page_length=500,
    )
    return [str(row.name) for row in rows]


def _locked_route(name: str) -> Mapping[str, Any]:
    rows = frappe.db.sql(
        "select name, modified from `tabProduction Routing` where name = %s for update",
        (name,),
        as_dict=True,
    )
    if not rows:
        raise ProductionRoutingManagementError(
            "مسار الإنتاج المطلوب غير موجود أو تم حذفه."
        )
    return rows[0]


def _assert_version(snapshot: Mapping[str, Any], expected_modified: str) -> None:
    current = str(snapshot.get("modified") or "")
    if current != str(expected_modified or ""):
        raise ProductionRoutingManagementConflict(
            "تم تعديل المسار بواسطة مستخدم آخر. حدّث الصفحة وراجع التغييرات قبل الحفظ."
        )


def _document_payload(document: Any) -> dict[str, Any]:
    ordered = sorted(
        document.stages or (),
        key=lambda item: (cint(item.sequence), cint(item.idx)),
    )
    definitions = _workflow_stage_definitions(
        {str(row.workflow_stage or "").strip() for row in ordered}
    )
    return {
        "name": str(document.name),
        "label": str(document.routing_name or document.name),
        "disabled": bool(cint(document.disabled)),
        "modified": document.modified,
        "modified_by": str(document.modified_by or ""),
        "stages": [_stage_payload(row, definitions) for row in ordered],
    }


class FrappeProductionRoutingManagementRepository:
    def save_routing(
        self,
        command: SaveProductionRoutingCommand,
    ) -> Mapping[str, Any]:
        if command.name:
            snapshot = _locked_route(command.name)
            _assert_version(snapshot, command.expected_modified or "")
            document = frappe.get_doc("Production Routing", command.name)
        else:
            if frappe.db.exists("Production Routing", command.routing_name):
                raise ProductionRoutingManagementError(
                    "يوجد مسار إنتاج بهذا الاسم. اختر اسمًا مختلفًا."
                )
            document = frappe.new_doc("Production Routing")

        resolved_stages: list[tuple[Any, str]] = []
        for stage in command.stages:
            workflow_stage = workflow_stage_name(stage.workflow_stage)
            if not workflow_stage and stage.legacy_stage_label is not None:
                workflow_stage = ensure_workflow_stage(
                    stage.workflow_stage,
                    stage.legacy_stage_label,
                    kanban_order=stage.sequence,
                )
            resolved_stages.append((stage, workflow_stage or stage.workflow_stage))

        document.routing_name = command.routing_name
        document.disabled = int(command.disabled)
        document.set("stages", [])
        for stage, workflow_stage in resolved_stages:
            document.append(
                "stages",
                {
                    "sequence": stage.sequence,
                    "workflow_stage": workflow_stage,
                    "operational_role": stage.operational_role,
                    "required": 1,
                    "is_planning_stage": int(stage.is_planning_stage),
                },
            )

        if command.name:
            document.save(ignore_permissions=True)
        else:
            document.insert(ignore_permissions=True)
        return _document_payload(document)

    def set_routing_disabled(
        self,
        name: str,
        *,
        disabled: bool,
        expected_modified: str,
    ) -> Mapping[str, Any]:
        snapshot = _locked_route(name)
        _assert_version(snapshot, expected_modified)
        document = frappe.get_doc("Production Routing", name)
        document.disabled = int(disabled)
        document.save(ignore_permissions=True)
        return _document_payload(document)

    def delete_routing(self, name: str, *, expected_modified: str) -> None:
        snapshot = _locked_route(name)
        _assert_version(snapshot, expected_modified)
        frappe.delete_doc("Production Routing", name, ignore_permissions=True)


__all__ = [
    "FrappeProductionRoutingManagementRepository",
    "list_operational_roles",
    "list_production_routings",
    "list_workflow_stages",
]
