from __future__ import annotations

from typing import Any

import frappe


STAGE_DEFAULTS: dict[str, tuple[str, str]] = {
    "Sharyoun": ("شريون", "عامل شريون"),
    "Drawing": ("رسم", "عامل رسم"),
    "CNC": ("CNC", "عامل CNC"),
    "Sanding": ("تقشيط", "عامل تقشيط"),
    "Cutting": ("قص", "Cutting Operator"),
    "Edge Banding": ("قشاط", "Edge Operator"),
    "Review / Preparation": ("مراجعة وتجهيز", "Production Manager"),
    "Drilling": ("تثقيب", "Production Manager"),
    "Assembly": ("تجميع", "Production Manager"),
    "Quality Check": ("فحص الجودة", "Production Manager"),
    "Packing": ("تغليف", "Production Manager"),
}

LEGACY_ROUTES: dict[str, tuple[str, ...]] = {
    "Sharyoun": ("Sharyoun", "Sanding"),
    "Drawing": ("Drawing", "CNC", "Sanding"),
}


def _default(stage_type: str) -> tuple[str, str]:
    resolved = str(stage_type or "").strip()
    return STAGE_DEFAULTS.get(resolved, (resolved, "Production Manager"))


def _ensure_role(role: str) -> None:
    if frappe.db.exists("Role", role):
        return
    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": role,
            "desk_access": 1,
        }
    ).insert(ignore_permissions=True)


def _append_stage(route: Any, stage_type: str, sequence: int) -> None:
    label, role = _default(stage_type)
    _ensure_role(role)
    route.append(
        "stages",
        {
            "sequence": sequence,
            "stage_type": stage_type,
            "department_label": label,
            "operational_role": role,
            "required": 1,
            "auto_complete_if_not_applicable": 0,
        },
    )


def _ensure_legacy_routes() -> None:
    for route_name, stage_types in LEGACY_ROUTES.items():
        if frappe.db.exists("Production Routing", route_name):
            continue
        route = frappe.new_doc("Production Routing")
        route.routing_name = route_name
        route.disabled = 0
        for index, stage_type in enumerate(stage_types, start=1):
            _append_stage(route, stage_type, index * 10)
        route.insert(ignore_permissions=True)


def _backfill_route_stages() -> None:
    rows = frappe.get_all(
        "Production Routing Stage",
        fields=["name", "stage_type", "department_label", "operational_role"],
    )
    for row in rows:
        label, role = _default(str(row.stage_type or ""))
        _ensure_role(role)
        values: dict[str, Any] = {}
        if not str(row.department_label or "").strip():
            values["department_label"] = label
        if not str(row.operational_role or "").strip():
            values["operational_role"] = role
        if values:
            frappe.db.set_value(
                "Production Routing Stage",
                row.name,
                values,
                update_modified=False,
            )


def _backfill_production_stages() -> None:
    rows = frappe.get_all(
        "Production Stage",
        fields=["name", "stage_type", "department_label", "operational_role"],
    )
    for row in rows:
        label, role = _default(str(row.stage_type or ""))
        _ensure_role(role)
        values: dict[str, Any] = {}
        if not str(row.department_label or "").strip():
            values["department_label"] = label
        if not str(row.operational_role or "").strip():
            values["operational_role"] = role
        if values:
            frappe.db.set_value(
                "Production Stage",
                row.name,
                values,
                update_modified=False,
            )


def execute() -> None:
    """Activate UI-managed routes while preserving every in-flight legacy order."""

    if not frappe.db.exists("DocType", "Production Routing"):
        return
    for _, role in STAGE_DEFAULTS.values():
        _ensure_role(role)
    _ensure_legacy_routes()
    _backfill_route_stages()
    _backfill_production_stages()


__all__ = ["execute"]
