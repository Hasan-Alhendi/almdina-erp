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
from frappe.utils.file_manager import save_file

from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    machine_profile_for_workspace,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import mm_per_min_from_sec
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    ApprovedPlanRef,
    generation_snapshot_is_complete,
)
from almdina_erp.almdina_erp.domain.cnc.operations import CNC_OPERATION_TYPES
from almdina_erp.almdina_erp.domain.cutting.finished_piece_geometry import (
    resolve_finished_geometry_mm,
)
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
    stored_by_instance: dict[str, Mapping[str, Any]] = {}
    for index, sheet in enumerate(snapshot.get("sheets") or [], start=1):
        if not isinstance(sheet, Mapping):
            continue
        sheet_no = cint(sheet.get("sheet_no") or index)
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, Mapping):
                continue
            stored_by_identity[(sheet_no, cint(piece.get("id") or 0))] = piece
            instance = str(
                piece.get("piece_instance_id") or piece.get("label") or ""
            ).strip()
            if instance and instance not in stored_by_instance:
                stored_by_instance[instance] = piece
    views: list[dict[str, Any]] = []
    for piece in plan.placed_pieces or []:
        sheet_no = cint(piece.sheet_no)
        piece_id = cint(piece.piece_id)
        stored = stored_by_identity.get((sheet_no, piece_id))
        if stored is None:
            instance = str(getattr(piece, "piece_instance_id", "") or "").strip()
            label = str(getattr(piece, "piece_label", "") or "").strip()
            stored = stored_by_instance.get(instance) or stored_by_instance.get(label) or {}
        overlays = stored.get("overlays") if isinstance(stored.get("overlays"), list) else []
        view = {
            "piece_instance_id": str(piece.piece_instance_id or ""),
            "sheet_no": sheet_no,
            "piece_id": piece_id,
            "extra_liner": cint(getattr(piece, "extra_liner", 0)),
            "liner_specs_json": getattr(piece, "liner_specs_json", "") or "",
            "liner_reference_side": getattr(piece, "liner_reference_side", "") or "",
            "liner_offset_cm": getattr(piece, "liner_offset_cm", 0),
            "liner_width_cm": getattr(piece, "liner_width_cm", 0),
            "liner_start_cm": getattr(piece, "liner_start_cm", 0),
            "liner_length_cm": getattr(piece, "liner_length_cm", 0),
            "extra_back_groove": cint(getattr(piece, "extra_back_groove", 0)),
            "back_groove_reference_side": getattr(piece, "back_groove_reference_side", "") or "",
            "back_groove_offset_cm": getattr(piece, "back_groove_offset_cm", 0),
            "back_groove_width_cm": getattr(piece, "back_groove_width_cm", 0),
            "back_groove_start_cm": getattr(piece, "back_groove_start_cm", 0),
            "back_groove_length_cm": getattr(piece, "back_groove_length_cm", 0),
            "extra_recessed_handle_cutout": cint(
                getattr(piece, "extra_recessed_handle_cutout", 0)
            ),
            "recessed_handle_reference_side": getattr(piece, "recessed_handle_reference_side", "") or "",
            "recessed_handle_offset_cm": getattr(piece, "recessed_handle_offset_cm", 0),
            "recessed_handle_width_cm": getattr(piece, "recessed_handle_width_cm", 0),
            "recessed_handle_start_cm": getattr(piece, "recessed_handle_start_cm", 0),
            "recessed_handle_length_cm": getattr(piece, "recessed_handle_length_cm", 0),
            "piece_type": getattr(piece, "piece_type", "") or "Regular",
            "original_width_cm": getattr(piece, "original_width_cm", 0),
            "original_length_cm": getattr(piece, "original_length_cm", 0),
            "width_mm": getattr(piece, "width_mm", 0),
            "height_mm": getattr(piece, "height_mm", 0),
            "x_mm": getattr(piece, "x_mm", 0),
            "y_mm": getattr(piece, "y_mm", 0),
            "rotated": cint(getattr(piece, "rotated", 0)),
            "rotation_quarter_turns": cint(
                stored.get("rotation_quarter_turns")
                if stored.get("rotation_quarter_turns") is not None
                else stored.get("corner_rotation_quarter_turns")
                if stored.get("corner_rotation_quarter_turns") is not None
                else (1 if cint(getattr(piece, "rotated", 0)) else 0)
            ),
            "corner_mirrored": cint(
                stored.get("corner_mirrored")
                if stored.get("corner_mirrored") is not None
                else getattr(piece, "corner_mirrored", 0)
            ),
            "clipped_corner_position": getattr(piece, "clipped_corner_position", "") or "",
            "clipped_corner_width_cm": getattr(piece, "clipped_corner_width_cm", 0),
            "clipped_corner_length_cm": getattr(piece, "clipped_corner_length_cm", 0),
            "special_shape_geometry_json": (
                getattr(piece, "special_shape_geometry_json", "")
                or stored.get("special_shape_geometry_json")
                or ""
            ),
            "label": str(stored.get("label") or getattr(piece, "piece_label", "") or ""),
            "overlays": overlays,
        }
        for key in ("glass_host_piece_id", "glass_hole_local_mm", "glass_margin_mm"):
            if stored.get(key) not in (None, "", []):
                view[key] = stored.get(key)
        stored_geometry = (
            stored.get("geometry") if isinstance(stored.get("geometry"), Mapping) else None
        )
        view["geometry"] = resolve_finished_geometry_mm(
            stored_geometry=stored_geometry,
            piece=view,
            stored_piece=stored,
        )
        views.append(view)
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
    from almdina_erp.almdina_erp.domain.cutting.tool_diameters import diameters_for_record

    runtime = dict(parsed)
    runtime.update(diameters_for_record(plan))
    return runtime


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
        file_url = str(document.generated_file or "")
        rows.append(
            {
                "name": document.name,
                "cutting_plan": document.cutting_plan,
                "plan_revision": cint(document.plan_revision),
                "plan_source_type": document.plan_source_type,
                "sheet_no": cint(document.sheet_no),
                "status": document.status,
                "settings_fingerprint": str(document.settings_fingerprint or ""),
                "generation_fingerprint": str((snapshot or {}).get("settings_fingerprint") or ""),
                "generation_snapshot": dict(snapshot or {}),
                "snapshot_complete": generation_snapshot_is_complete(snapshot),
                "generated_file": file_url,
                "file_present": private_generated_file_present(
                    file_url,
                    attached_to_name=str(document.name),
                ),
                "generated_by": document.generated_by,
                "generated_on": document.generated_on,
                "cut_path_early_confirmed": bool(cint(document.cut_path_early_confirmed)),
                "perimeter_join_mode": str(getattr(document, "perimeter_join_mode", None) or "separate"),
                "cut_path_sequence": _sequence_list(getattr(document, "cut_path_sequence", None)),
                "perimeter_cut_early_confirmed": bool(cint(getattr(document, "perimeter_cut_early_confirmed", 0))),
                "cnc_machine": str(getattr(document, "cnc_machine", None) or ""),
                "offset_left_cm": float(getattr(document, "offset_left_cm", 0) or 0),
                "offset_bottom_cm": float(getattr(document, "offset_bottom_cm", 0) or 0),
                "operations": _child_rows(
                    document.operations,
                    ("operation_key", "dxf_layer", "sequence", "tool_preset", "preset_source"),
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
                "machining_profiles": _object_list(getattr(document, "machining_profiles_json", None)),
                "vector_associations": _object_list(getattr(document, "vector_associations_json", None)),
                "toolpath_snapshots": _object_list(getattr(document, "toolpath_snapshots_json", None)),
                "reversed_path_keys": _object_list(getattr(document, "reversed_path_keys", None)),
            }
        )
    return rows


def private_generated_file_present(file_url: str, *, attached_to_name: str) -> bool:
    """True when a private File is attached to this operational-file row."""

    url = str(file_url or "").strip()
    name = str(attached_to_name or "").strip()
    if not url or not name:
        return False
    row = frappe.db.get_value(
        "File",
        {
            "file_url": url,
            "attached_to_doctype": "CNC Operational File",
            "attached_to_name": name,
            "is_private": 1,
        },
        ["name", "is_private"],
        as_dict=True,
    )
    return bool(row and cint(row.is_private))


def _snapshot_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        parsed = json.loads(raw)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _sequence_list(raw: Any) -> list[str]:
    """Read a JSON sequence field as list[str]. Never return nested JSON text."""

    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item or "").strip()]
    if isinstance(raw, tuple):
        return [str(item) for item in raw if str(item or "").strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        parsed = json.loads(text)
        if isinstance(parsed, str):
            # Guard against historically double-encoded payloads.
            parsed = json.loads(parsed) if parsed.strip() else []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item or "").strip()]
        raise frappe.ValidationError("Cut Path Sequence must be a JSON list.")
    raise frappe.ValidationError("Cut Path Sequence must be a JSON list.")


def _object_list(raw: Any) -> list[Any]:
    """Read a JSON object-list field. Missing values stay empty for old files."""

    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        parsed = json.loads(text)
        if isinstance(parsed, str):
            parsed = json.loads(parsed) if parsed.strip() else []
        if isinstance(parsed, list):
            return list(parsed)
    raise frappe.ValidationError("CNC machining JSON must be a list.")


def _object_list_json(raw: Any) -> str:
    return json.dumps(_object_list(raw), ensure_ascii=True, separators=(",", ":"))


def _sequence_json(raw: Any) -> str:
    """Encode a Python sequence as a single JSON list string for a Frappe JSON field."""

    if raw is None or raw == "":
        return "[]"
    if isinstance(raw, str):
        # Accept an already-encoded list; reject other shapes to avoid double encoding.
        return json.dumps(_sequence_list(raw), ensure_ascii=True, separators=(",", ":"))
    if isinstance(raw, (list, tuple)):
        return json.dumps(
            [str(item) for item in raw if str(item or "").strip()],
            ensure_ascii=True,
            separators=(",", ":"),
        )
    raise frappe.ValidationError("Cut Path Sequence is not valid.")


def read_simulation_nc_bytes(
    *,
    operational_file_name: str,
    expected_order: str,
    file_url: str | None = None,
) -> tuple[str, bytes]:
    """Return (filename, content) for a scoped private Simulation NC attachment."""

    document = _without_permission_check(
        lambda: frappe.get_doc("CNC Operational File", operational_file_name)
    )
    if str(document.door_cutting_order or "") != str(expected_order or ""):
        raise frappe.PermissionError("Operational file is outside the authorized order.")
    snapshot = _snapshot_dict(document.generation_snapshot_json)
    current = str(document.generated_file or "").strip()
    previous = str(snapshot.get("previous_generated_file") or "").strip()
    url = str(file_url or current or "").strip()
    if not url:
        raise frappe.ValidationError("No simulation NC file is stored for this sheet.")
    allowed = {value for value in (current, previous) if value}
    if url not in allowed:
        raise frappe.PermissionError("File is not linked to this operational record.")
    file_row = frappe.db.get_value(
        "File",
        {
            "file_url": url,
            "attached_to_doctype": "CNC Operational File",
            "attached_to_name": str(document.name),
            "is_private": 1,
        },
        ["name", "file_name", "is_private"],
        as_dict=True,
    )
    if not file_row:
        raise frappe.ValidationError("The stored simulation NC file could not be found.")
    if not cint(file_row.is_private):
        raise frappe.PermissionError("Public simulation NC downloads are not allowed.")
    file_doc = _without_permission_check(lambda: frappe.get_doc("File", file_row.name))
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode("utf-8")
    return str(file_row.file_name or "sheet.sim.nc"), bytes(content or b"")


def attach_simulation_nc(
    *,
    operational_file_name: str,
    filename: str,
    content: str | bytes,
) -> str:
    """Create a private File attached to the operational-file row. Does not update status."""

    payload = content.encode("utf-8") if isinstance(content, str) else bytes(content or b"")
    file_doc = save_file(
        fname=str(filename),
        content=payload,
        dt="CNC Operational File",
        dn=str(operational_file_name),
        folder=None,
        is_private=1,
        df="generated_file",
    )
    if not cint(getattr(file_doc, "is_private", 0)):
        try:
            file_doc.delete(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="CNC simulation NC public file cleanup failed")
        raise frappe.ValidationError("Simulation NC must stay private.")
    return str(file_doc.file_url)


def discard_orphan_file(file_url: str) -> None:
    """Best-effort cleanup when record update fails after File creation."""

    url = str(file_url or "").strip()
    if not url:
        return
    name = frappe.db.get_value("File", {"file_url": url}, "name")
    if not name:
        return
    try:
        _without_permission_check(lambda: frappe.get_doc("File", name).delete())
    except Exception:
        frappe.log_error(title="CNC simulation NC orphan cleanup failed")


def known_tool_presets() -> dict[str, dict[str, Any]]:
    rows = frappe.get_all(
        "CNC Tool Preset",
        fields=[
            "name",
            "tool_name",
            "tool_number",
            "tool_diameter_mm",
            "spindle_speed_rpm",
            "feed_rate_mm_sec",
            "plunge_rate_mm_sec",
            "stepdown_mm",
            "enabled",
            "tool_type",
            "tool_units",
            "rate_units",
            "notes",
            "final_tool_offset_mm",
            "stepover_size_mm",
            "stepover_percent",
        ],
        limit_page_length=0,
        ignore_permissions=True,
    )
    return {
        str(row.name): {
            "preset_name": row.tool_name,
            "tool_name": row.tool_name,
            "tool_number": row.tool_number,
            "tool_diameter_mm": row.tool_diameter_mm,
            "spindle_speed_rpm": row.spindle_speed_rpm,
            "feed_rate_mm_sec": row.feed_rate_mm_sec,
            "plunge_rate_mm_sec": row.plunge_rate_mm_sec,
            "feed_rate_mm_min": mm_per_min_from_sec(row.feed_rate_mm_sec or 0),
            "plunge_rate_mm_min": mm_per_min_from_sec(row.plunge_rate_mm_sec or 0),
            "stepdown_mm": row.stepdown_mm,
            "pass_depth_mm": None if not row.stepdown_mm else row.stepdown_mm,
            "enabled": bool(cint(row.enabled)),
            "tool_type": row.tool_type or "",
            "tool_units": row.tool_units or "",
            "rate_units": row.rate_units or "",
            "notes": row.notes or "",
            "description": row.tool_name or "",
            "diameter_mm": row.tool_diameter_mm,
            "final_tool_offset_mm": row.final_tool_offset_mm,
            "stepover_size_mm": row.stepover_size_mm,
            "stepover_percent": row.stepover_percent,
        }
        for row in rows
    }


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        if not value.strip():
            return {}
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def machining_profile_catalog() -> list[dict[str, Any]]:
    """ArtCAM profiles managed from operational-file settings, not from a sheet."""

    if not frappe.db.exists("DocType", "CNC Machining Profile"):
        return []
    rows = frappe.get_all(
        "CNC Machining Profile",
        fields=[
            "profile_id",
            "profile_name",
            "tool_preset",
            "tool_values_json",
            "final_depth_mm",
            "safe_z_mm",
            "home_x_mm",
            "home_y_mm",
            "home_z_mm",
            "enabled",
        ],
        order_by="profile_name asc",
        limit_page_length=0,
    )
    return [
        {
            "profile_id": row.profile_id,
            "name": row.profile_name,
            "tool_preset": row.tool_preset,
            "tool_values": _json_object(row.tool_values_json),
            "final_depth_mm": row.final_depth_mm,
            "safe_z_mm": row.safe_z_mm,
            "home_x_mm": row.home_x_mm,
            "home_y_mm": row.home_y_mm,
            "home_z_mm": row.home_z_mm,
            "enabled": bool(cint(row.enabled)),
        }
        for row in rows
    ]


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
    return machine_profile_for_workspace(raw)


def list_cnc_machines(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    """Return CNC machines registered for this factory site."""

    if not frappe.db.exists("DocType", "CNC Machine"):
        return []
    filters: dict[str, Any] = {}
    if enabled_only:
        filters["enabled"] = 1
    rows = frappe.get_all(
        "CNC Machine",
        filters=filters,
        fields=["name", "machine_name", "width_cm", "length_cm", "enabled"],
        order_by="machine_name asc",
        ignore_permissions=True,
    )
    return [
        {
            "name": str(row.name),
            "machine_name": str(row.machine_name or row.name),
            "width_cm": float(row.width_cm or 0),
            "length_cm": float(row.length_cm or 0),
            "enabled": bool(cint(row.enabled)),
        }
        for row in rows
    ]


def get_cnc_machine(name: str) -> dict[str, Any] | None:
    token = str(name or "").strip()
    if not token or not frappe.db.exists("CNC Machine", token):
        return None
    document = _without_permission_check(lambda: frappe.get_doc("CNC Machine", token))
    return {
        "name": str(document.name),
        "machine_name": str(document.machine_name or document.name),
        "width_cm": float(document.width_cm or 0),
        "length_cm": float(document.length_cm or 0),
        "enabled": bool(cint(document.enabled)),
    }


def _dxf_disk_path(file_url: str) -> str | None:
    import os
    from pathlib import Path

    normalized = str(file_url or "").strip().lstrip("/")
    if not normalized or ".." in Path(normalized).parts:
        return None
    for candidate in (
        frappe.get_site_path(normalized),
        frappe.get_site_path("public", normalized),
    ):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def manufacturing_source(order: Any) -> dict[str, Any]:
    """Return how the approved plan should be read. This does not export DXF."""

    plan = approved_plan_for_order(order)
    if plan is None:
        return {"source_type": "", "saw_center_status": "", "dxf_path": None}
    return {
        "source_type": str(getattr(plan, "source_type", "") or ""),
        "saw_center_status": str(getattr(plan, "saw_center_status", "") or "Unknown"),
        "dxf_path": _dxf_disk_path(str(getattr(plan, "dxf_file", "") or "")),
    }


def record_nc_generation(name: str, snapshot: Mapping[str, Any], file_url: str) -> None:
    """Store the generation snapshot only when a private NC file URL is present."""

    url = str(file_url or "").strip()
    if not url:
        raise frappe.ValidationError("Generated status requires a stored simulation NC file.")
    if not generation_snapshot_is_complete(snapshot):
        raise frappe.ValidationError("Generation snapshot is incomplete.")
    if not private_generated_file_present(url, attached_to_name=str(name)):
        raise frappe.ValidationError("Generated status requires a private attached NC file.")
    document = _without_permission_check(lambda: frappe.get_doc("CNC Operational File", name))
    document.generation_snapshot_json = dict(snapshot or {})
    document.generated_file = url
    document.generated_by = frappe.session.user
    document.generated_on = frappe.utils.now_datetime()
    document.status = "Generated"
    document.flags.ignore_permissions = True
    document.save()


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


def update_machining_json(
    name: str,
    *,
    profiles: Sequence[Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    fingerprint: str = "",
    status: str = "",
) -> None:
    """Replace machining JSON without rewriting operations, paths, or NC history."""

    document = _without_permission_check(lambda: frappe.get_doc("CNC Operational File", name))
    document.machining_profiles_json = _object_list_json(list(profiles))
    document.vector_associations_json = _object_list_json(list(associations))
    document.toolpath_snapshots_json = _object_list_json(list(snapshots))
    if fingerprint:
        document.settings_fingerprint = fingerprint
    if status:
        document.status = status
    document.flags.ignore_permissions = True
    document.flags.ignore_links = True
    document.save()


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
        "perimeter_join_mode",
        "perimeter_cut_early_confirmed",
        "cnc_machine",
        "offset_left_cm",
        "offset_bottom_cm",
    ):
        document.set(field, payload.get(field))
    # Frappe JSON fields reject a raw Python list; persist one JSON string.
    document.set("cut_path_sequence", _sequence_json(payload.get("cut_path_sequence")))
    if "reversed_path_keys" in payload:
        document.set("reversed_path_keys", _object_list_json(payload.get("reversed_path_keys")))
    from almdina_erp.almdina_erp.domain.cnc.operational_file import (
        validate_operational_path_rows,
    )

    document.set("operations", [])
    document.set("paths", [])
    for row in payload.get("operations") or []:
        document.append("operations", row)
    for row in validate_operational_path_rows(list(payload.get("paths") or [])):
        document.append(
            "paths",
            {
                "path_key": row.get("path_key"),
                "operation_key": row.get("operation_key"),
                "piece_instance_id": row.get("piece_instance_id") or "",
                "dxf_layer": row.get("dxf_layer"),
                "sequence": row.get("sequence"),
                "tool_preset": row.get("tool_preset") or "",
            },
        )
    for field in (
        "machining_profiles_json",
        "vector_associations_json",
        "toolpath_snapshots_json",
    ):
        if field in payload:
            document.set(field, _object_list_json(payload.get(field)))
    document.generation_snapshot_json = kept_snapshot
    document.generated_file = kept_file
    document.generated_by = kept_by
    document.generated_on = kept_on
    document.flags.ignore_permissions = True
    # Link targets are validated by the service layer's order/plan authorization.
    document.flags.ignore_links = True
    document.save()
    return str(document.name)


__all__ = [
    "approved_plan_ref",
    "approved_plan_snapshot",
    "attach_simulation_nc",
    "discard_orphan_file",
    "factory_operation_defaults",
    "get_cnc_machine",
    "known_tool_presets",
    "list_cnc_machines",
    "machining_profile_catalog",
    "machine_profile_view",
    "manufacturing_source",
    "placed_piece_views",
    "private_generated_file_present",
    "read_simulation_nc_bytes",
    "record_nc_generation",
    "save_sheet",
    "update_machining_json",
    "saved_operational_files",
    "sync_status",
]
