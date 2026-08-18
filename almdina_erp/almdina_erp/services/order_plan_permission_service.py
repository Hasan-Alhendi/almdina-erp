from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import (
    require_stage_operational_access,
)


_OPTIMIZER_FIELDS = (
    "packing_mode",
    "cutting_machine_type",
    "kerf_mm",
    "trim_margin_mm",
    "optimization_time_limit_sec",
)
_OPTIMIZER_DEFAULTS = {
    "packing_mode": "default_packing_mode",
    "cutting_machine_type": "default_cutting_machine_type",
    "kerf_mm": "default_kerf_mm",
    "trim_margin_mm": "default_trim_margin_mm",
    "optimization_time_limit_sec": "default_optimization_time_limit_sec",
}
_NUMERIC_PLAN_INPUT_FIELDS = frozenset(
    {"kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"}
)


def _capability_allowed(doc: Any, capability: str) -> bool:
    if capability == Capability.EDIT_OPTIMIZER_SETTINGS:
        return cutting_plan_capability_allowed(
            doc,
            capability,
            allow_new_order=True,
        )
    if getattr(doc, "is_new", lambda: False)():
        return doctype_has_capability(capability)
    return document_has_capability(doc, capability)


def _same_value(fieldname: str, left: Any, right: Any) -> bool:
    if fieldname in _NUMERIC_PLAN_INPUT_FIELDS:
        return abs(flt(left) - flt(right)) < 0.000001
    return str(left or "").strip() == str(right or "").strip()


def _optimizer_changes(doc: Any, old: Any | None) -> list[str]:
    if old:
        return [
            fieldname
            for fieldname in _OPTIMIZER_FIELDS
            if not _same_value(fieldname, doc.get(fieldname), old.get(fieldname))
        ]

    settings = frappe.get_single("Almdina ERP Settings")
    changes: list[str] = []
    for fieldname, default_field in _OPTIMIZER_DEFAULTS.items():
        current = doc.get(fieldname)
        if current in (None, ""):
            continue
        if not _same_value(fieldname, current, settings.get(default_field)):
            changes.append(fieldname)
    return changes


def _piece_key(row: Any, index: int) -> str:
    return str(row.get("name") or f"idx:{index}")


def _drawing_snapshot(row: Any | None) -> tuple[str, str, str]:
    if not row:
        return ("", "", "")
    drawing = str(row.get("special_shape_drawing_json") or "")
    geometry = str(row.get("special_shape_geometry_json") or "")
    raw_status = str(row.get("special_shape_status") or "")
    status = raw_status if drawing or geometry or raw_status == "Documented" else ""
    return (drawing, geometry, status)


def _drawing_changed(doc: Any, old: Any | None) -> bool:
    current_rows = list(doc.get("pieces") or [])
    old_rows = list(old.get("pieces") or []) if old else []
    old_by_key = {
        _piece_key(row, index): row
        for index, row in enumerate(old_rows, start=1)
    }
    current_keys: set[str] = set()

    for index, row in enumerate(current_rows, start=1):
        key = _piece_key(row, index)
        current_keys.add(key)
        previous = old_by_key.get(key)
        if _drawing_snapshot(row) != _drawing_snapshot(previous):
            return True

    for index, row in enumerate(old_rows, start=1):
        key = _piece_key(row, index)
        if key not in current_keys and any(_drawing_snapshot(row)):
            return True
    return False


def enforce_plan_and_drawing_permissions(doc: Any, method: str | None = None) -> None:
    """Protect legacy DCO projections without making them Plan authority."""

    del method
    old = None if doc.is_new() else doc.get_doc_before_save()

    optimizer_changed = False
    if not _capability_allowed(doc, Capability.EDIT_OPTIMIZER_SETTINGS):
        changed = _optimizer_changes(doc, old)
        if changed:
            frappe.throw(
                _(
                    "لا تملك صلاحية تعديل إعدادات محسن خطة القص. الحقول المحمية: {0}."
                ).format(", ".join(changed)),
                frappe.PermissionError,
            )
    else:
        optimizer_changed = bool(_optimizer_changes(doc, old))

    drawing_changed = False
    if not _capability_allowed(doc, Capability.EDIT_SPECIAL_DRAWING):
        if _drawing_changed(doc, old):
            frappe.throw(
                _("لا تملك صلاحية تعديل رسومات الدرف الخاصة."),
                frappe.PermissionError,
            )
    else:
        drawing_changed = _drawing_changed(doc, old)

    if (optimizer_changed or drawing_changed) and (
        getattr(doc, "current_production_stage", None)
        or getattr(doc, "production_path", None)
    ):
        require_stage_operational_access(doc)


def _requested_optimizer_updates(
    *,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if packing_mode is not None:
        updates["packing_mode"] = str(packing_mode).strip()
    if cutting_machine_type is not None:
        updates["cutting_machine_type"] = str(cutting_machine_type).strip()
    if kerf_mm is not None:
        updates["kerf_mm"] = flt(kerf_mm)
    if trim_margin_mm is not None:
        updates["trim_margin_mm"] = flt(trim_margin_mm)
    if optimization_time_limit_sec is not None:
        updates["optimization_time_limit_sec"] = flt(optimization_time_limit_sec)
    return updates


def _recalculation_result(doc: Any) -> dict[str, Any]:
    """Legacy preview response; active Plan workspace reads canonical snapshots."""

    cutting_plan = getattr(doc, "cutting_plan_json", None) or ""
    system_plan = getattr(doc, "system_plan_json", None) or cutting_plan
    return {
        "name": doc.name,
        "required_boards": doc.required_boards,
        "waste_area_m2": doc.waste_area_m2,
        "waste_percent": doc.waste_percent,
        "packing_method": doc.packing_method,
        "packing_score": doc.packing_score,
        "total_area_m2": doc.total_area_m2,
        "total_edge_meters": doc.total_edge_meters,
        "packing_mode": doc.packing_mode,
        "cutting_machine_type": doc.cutting_machine_type,
        "kerf_mm": doc.kerf_mm,
        "trim_margin_mm": doc.trim_margin_mm,
        "optimization_time_limit_sec": doc.optimization_time_limit_sec,
        "plan_needs_recalculation": doc.plan_needs_recalculation,
        "cutting_plan_json": sanitize_plan_snapshot_json(cutting_plan),
        "system_plan_json": sanitize_plan_snapshot_json(system_plan),
        "approved_plan": doc.approved_plan,
        "approved_plan_source": doc.approved_plan_source,
    }


@frappe.whitelist()
def recalculate_order(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
        recalculate_order_plan,
    )

    return recalculate_order_plan(
        order_name=order_name,
        packing_mode=packing_mode,
        cutting_machine_type=cutting_machine_type,
        kerf_mm=kerf_mm,
        trim_margin_mm=trim_margin_mm,
        optimization_time_limit_sec=optimization_time_limit_sec,
    )


@frappe.whitelist()
def simulate_optimizer_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Legacy, non-persisting optimizer comparison endpoint."""

    name = str(order_name or "").strip()
    stored = frappe.get_doc("Door Cutting Order", name)
    stored.check_permission("read")
    require_cutting_plan_capability(
        stored,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        message=_("لا تملك صلاحية تجربة خوارزمية القص على هذا الطلب."),
    )

    preview = frappe.copy_doc(stored)
    preview.name = stored.name
    for fieldname, value in _requested_optimizer_updates(
        packing_mode=packing_mode,
        cutting_machine_type=cutting_machine_type,
        kerf_mm=kerf_mm,
        trim_margin_mm=trim_margin_mm,
        optimization_time_limit_sec=optimization_time_limit_sec,
    ).items():
        preview.set(fieldname, value)

    settings = preview._get_settings()
    preview._calculate_piece_rows()
    preview._calculate_cutting_plan(
        settings,
        preview._plan_input_fingerprint(settings),
    )

    result = _recalculation_result(preview)
    result["is_preview"] = True
    return result


__all__ = [
    "enforce_plan_and_drawing_permissions",
    "recalculate_order",
    "simulate_optimizer_plan",
]
