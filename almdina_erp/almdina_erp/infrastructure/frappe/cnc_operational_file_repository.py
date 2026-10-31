"""Frappe persistence for CNC operational files.

Reads the approved Cutting Plan that the order already points at. It does
not approve, recalculate, or reinterpret nesting.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    MachineProfileError,
    normalize_machine_profile,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import ApprovedPlanRef
from almdina_erp.almdina_erp.domain.cnc.operations import CNC_OPERATION_TYPES
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    approved_plan_for_order,
)


def _child_rows(rows: Sequence[Any] | None, fields: Sequence[str]) -> list[dict[str, Any]]:
    payload = []
    for row in rows or []:
        payload.append({field: row.get(field) for field in fields})
    return payload


def approved_plan_ref(order: Any) -> ApprovedPlanRef | None:
    plan = approved_plan_for_order(order)
    if plan is None:
        return None
    return ApprovedPlanRef(
        name=str(plan.name),
        revision=cint(plan.revision),
        source_type=str(plan.source_type or ""),
        status=str(plan.status or ""),
    )


def placed_piece_views(order: Any) -> list[dict[str, Any]]:
    plan = approved_plan_for_order(order)
    if plan is None:
        return []
    snapshot: dict[str, Any] = {}
    raw_snapshot = plan.snapshot_json or ""
    if str(raw_snapshot).strip():
        parsed = json.loads(raw_snapshot)
        if not isinstance(parsed, dict):
            raise frappe.ValidationError("Approved plan snapshot is not an object.")
        snapshot = parsed
    stored_by_identity: dict[tuple[int, int], Mapping[str, Any]] = {}
    for index, sheet in enumerate(snapshot.get("sheets") or [], start=1):
        if not isinstance(sheet, Mapping):
            continue
        sheet_no = cint(sheet.get("sheet_no") or index)
        for piece in sheet.get("pieces") or []:
            if isinstance(piece, Mapping):
                stored_by_identity[(sheet_no, cint(piece.get("id") or 0))] = piece
    views: list[dict[str, Any]] = []
    for piece in plan.placed_pieces or []:
        sheet_no = cint(piece.sheet_no)
        stored = stored_by_identity.get((sheet_no, cint(piece.piece_id)), {})
        geometry = stored.get("geometry") if isinstance(stored.get("geometry"), Mapping) else None
        overlays = stored.get("overlays") if isinstance(stored.get("overlays"), list) else []
        views.append(
            {
                "piece_instance_id": str(piece.piece_instance_id or ""),
                "sheet_no": sheet_no,
                "piece_id": cint(piece.piece_id),
                "extra_liner": cint(getattr(piece, "extra_liner", 0)),
                "liner_specs_json": getattr(piece, "liner_specs_json", "") or "",
                "liner_reference_side": getattr(piece, "liner_reference_side", "") or "",
                "liner_offset_cm": getattr(piece, "liner_offset_cm", 0),
                "liner_width_cm": getattr(piece, "liner_width_cm", 0),
                "liner_start_cm": getattr(piece, "liner_start_cm", 0),
                "liner_length_cm": getattr(piece, "liner_length_cm", 0),
                "extra_back_groove": cint(getattr(piece, "extra_back_groove", 0)),
                "extra_recessed_handle_cutout": cint(
                    getattr(piece, "extra_recessed_handle_cutout", 0)
                ),
                "label": str(stored.get("label") or ""),
                "label": str(stored.get("label") or ""),
                "geometry": geometry,
                "overlays": overlays,
            }
        )
    return views


def approved_plan_snapshot(order: Any) -> dict[str, Any] | None:
    plan = approved_plan_for_order(order)
    if plan is None:
        return None
    raw_snapshot = plan.snapshot_json or ""
    if not str(raw_snapshot).strip():
        return None
    parsed = json.loads(raw_snapshot)
    if not isinstance(parsed, dict):
        raise frappe.ValidationError("Approved plan snapshot is not an object.")
    return parsed


def approved_plan_snapshot(order: Any) -> dict[str, Any] | None:
    plan = approved_plan_for_order(order)
    if plan is None:
        return None
    raw_snapshot = plan.snapshot_json or ""
    if not str(raw_snapshot).strip():
        return None
    parsed = json.loads(raw_snapshot)
    if not isinstance(parsed, dict):
        raise frappe.ValidationError("Approved plan snapshot is not an object.")
    return parsed


def _without_permission_check(callback):
    """Repository reads run only after the service authorized the parent order."""

    previous = bool(getattr(frappe.flags, "ignore_permissions", False))
    frappe.flags.ignore_permissions = True
    try:
        return callback()
    finally:
        frappe.flags.ignore_permissions = previous


def saved_operational_files(order_name: str) -> list[dict[str, Any]]:
    names = frappe.get_all(
        "CNC Operational File",
        filters={"door_cutting_order": order_name},
        pluck="name",
        order_by="creation asc",
        ignore_permissions=True,
    )
    rows = []
    for name in names:
        document = _without_permission_check(lambda: frappe.get_doc("CNC Operational File", name))
        snapshot = document.generation_snapshot_json or {}
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot) if snapshot else {}
        rows.append(
            {
                "name": document.name,
                "cutting_plan": document.cutting_plan,
                "plan_revision": cint(document.plan_revision),
                "plan_source_type": document.plan_source_type,
                "sheet_no": cint(document.sheet_no),
                "status": document.status,
                "generation_fingerprint": str((snapshot or {}).get("settings_fingerprint") or ""),
                "generated_file": document.generated_file,
                "generated_by": document.generated_by,
                "generated_on": document.generated_on,
                "cut_path_early_confirmed": bool(cint(document.cut_path_early_confirmed)),
                "operations": _child_rows(
                    document.operations,
                    ("operation_key", "dxf_layer", "sequence", "tool_preset"),
                ),
                "paths": _child_rows(
                    document.paths,
                    (
                        "path_key",
                        "operation_key",
                        "piece_instance_id",
                        "dxf_layer",
                        "sequence",
                        "tool_preset",
                    ),
                ),
            }
        )
    return rows


def known_tool_presets() -> dict[str, dict[str, Any]]:
    rows = frappe.get_all(
        "CNC Tool Preset",
        fields=[
            "name",
            "preset_name",
            "tool_name",
            "tool_number",
            "tool_diameter_mm",
            "final_depth_mm",
            "spindle_speed_rpm",
            "feed_rate_mm_min",
            "plunge_rate_mm_min",
            "pass_depth_mm",
            "enabled",
        ],
        limit_page_length=0,
        ignore_permissions=True,
    )
    return {
        str(row.name): {
            "preset_name": row.preset_name,
            "tool_name": row.tool_name,
            "tool_number": row.tool_number,
            "tool_diameter_mm": row.tool_diameter_mm,
            "final_depth_mm": row.final_depth_mm,
            "spindle_speed_rpm": row.spindle_speed_rpm,
            "feed_rate_mm_min": row.feed_rate_mm_min,
            "plunge_rate_mm_min": row.plunge_rate_mm_min,
            "pass_depth_mm": row.pass_depth_mm,
            "enabled": bool(cint(row.enabled)),
        }
        for row in rows
    }


def factory_operation_defaults() -> dict[str, str]:
    return {
        operation.key: str(
            frappe.db.get_single_value("Almdina ERP Settings", operation.default_preset_field) or ""
        ).strip()
        for operation in CNC_OPERATION_TYPES
    }


def machine_profile_view() -> dict[str, Any]:
    raw = {
        field: frappe.db.get_single_value("Almdina ERP Settings", field)
        for field in (
            "cnc_machine_tool_number",
            "cnc_machine_spindle_speed_rpm",
            "cnc_machine_cutting_feed_mm_min",
            "cnc_machine_plunge_feed_mm_min",
            "cnc_machine_retract_z_mm",
            "cnc_machine_distance_mode",
            "cnc_machine_work_offset",
            "cnc_machine_example_depth_a_mm",
            "cnc_machine_example_depth_b_mm",
            "cnc_machine_profile_production_approved",
            "cnc_machine_profile_source",
        )
    }
    try:
        profile = normalize_machine_profile(raw)
    except MachineProfileError:
        return {
            "production_approved": False,
            "source_note": str(raw.get("cnc_machine_profile_source") or ""),
            "fingerprint_payload": {},
        }
    return {
        "production_approved": profile.production_approved,
        "source_note": profile.source_note,
        "fingerprint_payload": profile.fingerprint_payload(),
    }


def sync_status(name: str, status: str) -> None:
    current = frappe.db.get_value("CNC Operational File", name, "status")
    if current == status:
        return
    frappe.db.set_value(
        "CNC Operational File",
        name,
        "status",
        status,
        update_modified=False,
    )


def save_sheet(existing_name: str, payload: Mapping[str, Any]) -> str:
    if existing_name:
        document = _without_permission_check(
            lambda: frappe.get_doc("CNC Operational File", existing_name)
        )
    else:
        document = frappe.new_doc("CNC Operational File")
    kept_snapshot = document.get("generation_snapshot_json") if existing_name else None
    kept_file = document.get("generated_file") if existing_name else None
    kept_by = document.get("generated_by") if existing_name else None
    kept_on = document.get("generated_on") if existing_name else None
    for field in (
        "door_cutting_order",
        "cutting_plan",
        "plan_revision",
        "plan_source_type",
        "sheet_no",
        "sheet_key",
        "status",
        "settings_fingerprint",
        "cut_path_early_confirmed",
    ):
        document.set(field, payload.get(field))
    document.set("operations", [])
    document.set("paths", [])
    for row in payload.get("operations") or []:
        document.append("operations", row)
    for row in payload.get("paths") or []:
        document.append("paths", row)
    document.generation_snapshot_json = kept_snapshot
    document.generated_file = kept_file
    document.generated_by = kept_by
    document.generated_on = kept_on
    document.flags.ignore_permissions = True
    document.save()
    return str(document.name)


__all__ = [
    "approved_plan_ref",
    "approved_plan_snapshot",
    "factory_operation_defaults",
    "known_tool_presets",
    "machine_profile_view",
    "placed_piece_views",
    "save_sheet",
    "saved_operational_files",
    "sync_status",
]
