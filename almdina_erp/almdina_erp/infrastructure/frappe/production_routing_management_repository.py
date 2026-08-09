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


def _stage_payload(row: Any) -> dict[str, Any]:
    return {
        "sequence": cint(row.sequence),
        "stage_type": str(row.stage_type or ""),
        "department_label": str(row.department_label or ""),
        "operational_role": str(row.operational_role or ""),
        "required": bool(cint(row.required)),
        "is_planning_stage": bool(cint(row.is_planning_stage)),
    }


def list_production_routings() -> list[dict[str, Any]]:
    """Return the routing console projection without one query per route."""

    rows = frappe.get_all(
        "Production Routing",
        fields=["name", "routing_name", "disabled", "modified", "modified_by"],
        order_by="disabled asc, routing_name asc",
    )
    names = [str(row.name) for row in rows]
    stages_by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if names:
        stage_rows = frappe.get_all(
            "Production Routing Stage",
            filters={
                "parent": ["in", names],
                "parenttype": "Production Routing",
            },
            fields=[
                "parent",
                "sequence",
                "stage_type",
                "department_label",
                "operational_role",
                "required",
                "is_planning_stage",
            ],
            order_by="parent asc, sequence asc, idx asc",
        )
        for stage in stage_rows:
            stages_by_route[str(stage.parent)].append(_stage_payload(stage))

    in_flight_counts: dict[str, int] = {}
    if names:
        active_rows = frappe.get_all(
            "Door Cutting Order",
            filters={
                "production_path": ["in", names],
                "current_production_stage": ["is", "set"],
                "status": ["not in", ["Delivered", "Cancelled"]],
            },
            fields=["production_path", "count(name) as order_count"],
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
    return {
        "name": str(document.name),
        "label": str(document.routing_name or document.name),
        "disabled": bool(cint(document.disabled)),
        "modified": document.modified,
        "modified_by": str(document.modified_by or ""),
        "stages": [
            _stage_payload(row)
            for row in sorted(
                document.stages or (),
                key=lambda item: (cint(item.sequence), cint(item.idx)),
            )
        ],
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

        document.routing_name = command.routing_name
        document.disabled = int(command.disabled)
        document.set("stages", [])
        for stage in command.stages:
            document.append(
                "stages",
                {
                    "sequence": stage.sequence,
                    "stage_type": stage.stage_type,
                    "department_label": stage.department_label,
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
]
