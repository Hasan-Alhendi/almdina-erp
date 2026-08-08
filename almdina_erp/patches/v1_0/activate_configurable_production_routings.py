from __future__ import annotations

from typing import Any

import frappe


# These values exist only to translate historical production rows. They are not
# defaults for a new factory and must never seed roles/routes on a clean site.
LEGACY_STAGE_DEFAULTS: dict[str, tuple[str, str]] = {
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
    return LEGACY_STAGE_DEFAULTS.get(resolved, (resolved, "Production Manager"))


def _has_legacy_production_data() -> bool:
    """Return true only when this site has state that predates configurable routes."""

    if frappe.db.count("Production Stage"):
        return True
    if frappe.db.exists(
        "Door Cutting Order",
        {"production_path": ["in", sorted(LEGACY_ROUTES)]},
    ):
        return True
    if frappe.db.exists("Production Routing", {"name": ["in", sorted(LEGACY_ROUTES)]}):
        return True
    return False


def _ensure_legacy_role(role: str) -> None:
    """Create a historical role only while migrating an existing legacy site."""

    if frappe.db.exists("Role", role):
        return
    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": role,
            "desk_access": 1,
        }
    ).insert(ignore_permissions=True)


def _append_legacy_stage(route: Any, stage_type: str, sequence: int) -> None:
    label, role = _default(stage_type)
    _ensure_legacy_role(role)
    route.append(
        "stages",
        {
            "sequence": sequence,
            "stage_type": stage_type,
            "department_label": label,
            "operational_role": role,
            "required": 1,
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
            _append_legacy_stage(route, stage_type, index * 10)
        route.insert(ignore_permissions=True)


def _backfill_route_stages() -> None:
    rows = frappe.get_all(
        "Production Routing Stage",
        fields=["name", "stage_type", "department_label", "operational_role"],
    )
    for row in rows:
        label, role = _default(str(row.stage_type or ""))
        values: dict[str, Any] = {}
        if not str(row.department_label or "").strip():
            values["department_label"] = label
        if not str(row.operational_role or "").strip():
            _ensure_legacy_role(role)
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
        values: dict[str, Any] = {}
        if not str(row.department_label or "").strip():
            values["department_label"] = label
        if not str(row.operational_role or "").strip():
            _ensure_legacy_role(role)
            values["operational_role"] = role
        if values:
            frappe.db.set_value(
                "Production Stage",
                row.name,
                values,
                update_modified=False,
            )


def execute() -> None:
    """Migrate legacy production only; a clean site stays completely unseeded."""

    if not frappe.db.exists("DocType", "Production Routing"):
        return
    if not _has_legacy_production_data():
        return
    _ensure_legacy_routes()
    _backfill_route_stages()
    _backfill_production_stages()


__all__ = ["execute"]
