"""Prepare the operational-file workspace from an already approved plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    is_financial_plan_key,
)
from almdina_erp.almdina_erp.domain.cnc.operations import CNC_OPERATIONS_BY_KEY
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    FACTORY_PRESET_SOURCE,
    NOT_GENERATED,
    SHEET_PRESET_SOURCE,
    ApprovedPlanRef,
    OperationalFileError,
    assess_approved_plan,
    assign_sheet_presets,
    catalog_sheet,
    confirmed_operation_order,
    effective_status,
    merge_operation_order,
    operation_preset_choice,
    resolve_operation_order,
    settings_fingerprint,
)


def _sheet_numbers(pieces: Sequence[Mapping[str, Any]]) -> list[int]:
    return sorted({int(piece.get("sheet_no") or 0) for piece in pieces if int(piece.get("sheet_no") or 0) > 0})


def _saved_for(
    saved_files: Sequence[Mapping[str, Any]],
    *,
    plan_name: str,
    revision: int,
    sheet_no: int,
) -> Mapping[str, Any] | None:
    for row in saved_files:
        if (
            str(row.get("cutting_plan") or "") == plan_name
            and int(row.get("plan_revision") or 0) == int(revision)
            and int(row.get("sheet_no") or 0) == int(sheet_no)
        ):
            return row
    return None


_LAYOUT_KEYS = (
    "full_board_width_cm",
    "full_board_length_cm",
    "usable_board_width_cm",
    "usable_board_length_cm",
    "applied_trim_width_cm",
    "applied_trim_length_cm",
    "trim_cm",
    "kerf_cm",
    "method_key",
    "method_label",
    "saw_center_status",
    "sheets",
)


def _strip_financial(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip_financial(item)
            for key, item in value.items()
            if not is_financial_plan_key(key)
        }
    if isinstance(value, list):
        return [_strip_financial(item) for item in value]
    return value


def operational_board_layout(snapshot: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the approved board drawing without financial plan fields.

    Placement coordinates stay the values already stored on the approved
    snapshot. This does not nest, cut, or approve anything.
    """

    if not isinstance(snapshot, Mapping):
        return None
    clean = _strip_financial(snapshot)
    sheets = clean.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        return None
    return {key: clean[key] for key in _LAYOUT_KEYS if key in clean}


def _piece_labels(pieces: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {
        str(piece.get("piece_instance_id") or ""): str(piece.get("label") or "").strip()
        for piece in pieces
        if str(piece.get("piece_instance_id") or "").strip()
    }


def _saved_operation_keys(saved: Mapping[str, Any] | None) -> list[str]:
    rows = list((saved or {}).get("operations") or [])
    rows.sort(key=lambda row: (int(row.get("sequence") or 0), str(row.get("operation_key") or "")))
    return [str(row.get("operation_key") or "") for row in rows]


def _operation_rows(
    catalog,
    presets: Mapping[str, str],
    order: Sequence[str],
    sources: Mapping[str, str] | None = None,
    factory_defaults: Mapping[str, str] | None = None,
    *,
    persist: bool = False,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for path in catalog.paths:
        counts[path.operation_key] = counts.get(path.operation_key, 0) + 1
    source_rows = sources or {}
    defaults = factory_defaults or {}
    rows = []
    for index, key in enumerate(order, start=1):
        operation = CNC_OPERATIONS_BY_KEY[key]
        source = source_rows.get(key, FACTORY_PRESET_SOURCE)
        if persist:
            rows.append(
                {
                    "operation_key": key,
                    "dxf_layer": operation.dxf_layer,
                    "sequence": index,
                    "tool_preset": "" if source == FACTORY_PRESET_SOURCE else presets.get(key, ""),
                    "preset_source": source,
                }
            )
            continue
        public_source = "sheet" if source == SHEET_PRESET_SOURCE else "factory"
        rows.append(
            {
                "operation_key": key,
                "dxf_layer": operation.dxf_layer,
                "sequence": index,
                "tool_preset": presets.get(key, ""),
                "preset_source": public_source,
                "factory_preset": str(defaults.get(key) or "").strip(),
                "path_count": counts.get(key, 0),
            }
        )
    return rows


def _path_rows(
    catalog,
    overrides: Mapping[str, str],
    labels: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    labels = labels or {}
    return [
        {
            "path_key": path.path_key,
            "operation_key": path.operation_key,
            "dxf_layer": path.dxf_layer,
            "piece_instance_id": path.piece_instance_id,
            "piece_label": labels.get(path.piece_instance_id, ""),
            "sequence": path.sequence,
            "tool_preset": overrides.get(path.path_key, ""),
        }
        for path in catalog.paths
    ]


def build_operational_workspace(
    *,
    order_name: str,
    approved_plan: ApprovedPlanRef | None,
    plan_is_current: bool,
    pieces: Sequence[Mapping[str, Any]],
    saved_files: Sequence[Mapping[str, Any]],
    factory_defaults: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, Any]],
    machine_profile: Mapping[str, Any],
    can_prepare: bool,
) -> dict[str, Any]:
    try:
        plan = assess_approved_plan(approved_plan, current=plan_is_current)
    except OperationalFileError as exc:
        return {
            "eligible": False,
            "reason_code": exc.code,
            "order_name": order_name,
            "can_prepare": can_prepare,
            "sheets": [],
            "historical_files": [],
        }

    profile_payload = {
        "production_approved": bool(machine_profile.get("production_approved")),
        "source_note": str(machine_profile.get("source_note") or ""),
        "fingerprint_payload": dict(machine_profile.get("fingerprint_payload") or {}),
    }
    labels = _piece_labels(pieces)
    sheets: list[dict[str, Any]] = []
    for sheet_no in _sheet_numbers(pieces):
        catalog = catalog_sheet(sheet_no, pieces)
        saved = _saved_for(
            saved_files,
            plan_name=plan.name,
            revision=plan.revision,
            sheet_no=sheet_no,
        )
        order = merge_operation_order(catalog.operations, _saved_operation_keys(saved))
        confirmed = bool((saved or {}).get("cut_path_early_confirmed"))
        saved_operations = {
            str(row.get("operation_key") or ""): row
            for row in (saved or {}).get("operations") or []
        }
        proposed: dict[str, str] = {}
        sources: dict[str, str] = {}
        for key in catalog.operations:
            if saved is None:
                proposed[key] = str(factory_defaults.get(key) or "").strip()
                sources[key] = FACTORY_PRESET_SOURCE
                continue
            row = saved_operations.get(key) or {}
            chosen, source = operation_preset_choice(
                row.get("tool_preset"),
                row.get("preset_source"),
                factory_defaults.get(key, ""),
            )
            proposed[key] = chosen
            sources[key] = source
        if saved is None:
            status = NOT_GENERATED
            operational_file = ""
            overrides: dict[str, str] = {}
            fingerprint = ""
        else:
            overrides = {
                str(row.get("path_key") or ""): str(row.get("tool_preset") or "").strip()
                for row in saved.get("paths") or []
                if str(row.get("tool_preset") or "").strip()
            }
            current_fingerprint = settings_fingerprint(
                operation_presets=proposed,
                path_overrides=overrides,
                presets=known_presets,
                machine_profile=profile_payload["fingerprint_payload"],
                operation_order=order,
                cut_path_early_confirmed=confirmed,
            )
            status = effective_status(
                generation_fingerprint=str(saved.get("generation_fingerprint") or ""),
                current_fingerprint=current_fingerprint,
                stored_plan=(str(saved.get("cutting_plan") or ""), int(saved.get("plan_revision") or 0)),
                current_plan=plan.identity,
                generated_file=str(saved.get("generated_file") or ""),
                file_present=saved.get("file_present"),
                snapshot_complete=saved.get("snapshot_complete"),
            )
            operational_file = str(saved.get("name") or "")
            fingerprint = current_fingerprint
        sheets.append(
            {
                "sheet_no": sheet_no,
                "sheet_key": f"sheet:{sheet_no}",
                "operational_file": operational_file,
                "persisted": bool(operational_file),
                "status": status,
                "settings_fingerprint": fingerprint,
                "cut_path_early_confirmed": confirmed,
                "operations": _operation_rows(
                    catalog,
                    proposed,
                    order,
                    sources,
                    factory_defaults,
                ),
                "paths": _path_rows(catalog, overrides if saved is not None else {}, labels),
                "generated_file": str((saved or {}).get("generated_file") or ""),
                "file_present": bool((saved or {}).get("file_present")),
                "can_download_current": bool(
                    (saved or {}).get("file_present")
                    and str((saved or {}).get("generated_file") or "").strip()
                    and status in {"Generated", "Needs Regeneration"}
                ),
                "download_is_previous": status == "Needs Regeneration"
                and bool((saved or {}).get("file_present")),
                "generated_by": str((saved or {}).get("generated_by") or ""),
                "generated_on": (saved or {}).get("generated_on") or None,
                "content_sha256": str(
                    ((saved or {}).get("generation_snapshot") or {}).get("content_sha256") or ""
                ),
            }
        )

    historical = [
        {
            "name": str(row.get("name") or ""),
            "cutting_plan": str(row.get("cutting_plan") or ""),
            "plan_revision": int(row.get("plan_revision") or 0),
            "sheet_no": int(row.get("sheet_no") or 0),
            "status": effective_status(
                generation_fingerprint=str(row.get("generation_fingerprint") or ""),
                current_fingerprint="",
                stored_plan=(str(row.get("cutting_plan") or ""), int(row.get("plan_revision") or 0)),
                current_plan=plan.identity,
                generated_file=str(row.get("generated_file") or ""),
                file_present=row.get("file_present"),
                snapshot_complete=row.get("snapshot_complete"),
            ),
            "generated_file": str(row.get("generated_file") or ""),
            "file_present": bool(row.get("file_present")),
            "can_download": bool(row.get("file_present") and str(row.get("generated_file") or "").strip()),
        }
        for row in saved_files
        if (str(row.get("cutting_plan") or ""), int(row.get("plan_revision") or 0)) != plan.identity
    ]
    return {
        "eligible": True,
        "reason_code": "",
        "order_name": order_name,
        "cutting_plan": plan.name,
        "plan_revision": plan.revision,
        "plan_source_type": plan.source_type,
        "can_prepare": can_prepare,
        "machine_profile_production_approved": profile_payload["production_approved"],
        "machine_profile_source": profile_payload["source_note"],
        "presets": [
            {
                "name": name,
                "preset_name": str(values.get("preset_name") or name),
                "tool_name": str(values.get("tool_name") or ""),
                "tool_number": str(values.get("tool_number") or ""),
                "tool_diameter_mm": values.get("tool_diameter_mm"),
                "final_depth_mm": values.get("final_depth_mm"),
                "spindle_speed_rpm": values.get("spindle_speed_rpm"),
                "feed_rate_mm_min": values.get("feed_rate_mm_min"),
                "plunge_rate_mm_min": values.get("plunge_rate_mm_min"),
                "pass_depth_mm": values.get("pass_depth_mm"),
                "enabled": bool(values.get("enabled", True)),
            }
            for name, values in sorted(known_presets.items())
        ],
        "sheets": sheets,
        "historical_files": historical,
    }


def prepare_sheet_settings(
    *,
    order_name: str,
    approved_plan: ApprovedPlanRef | None,
    plan_is_current: bool,
    pieces: Sequence[Mapping[str, Any]],
    sheet_no: int,
    existing: Mapping[str, Any] | None,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, Any]],
    machine_profile: Mapping[str, Any],
    operation_order: Sequence[str] | None = None,
    cut_path_early_confirmed: bool | None = None,
    operation_sources: Mapping[str, str] | None = None,
    factory_defaults: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    plan = assess_approved_plan(approved_plan, current=plan_is_current)
    if int(sheet_no) not in _sheet_numbers(pieces):
        raise OperationalFileError("sheet_not_in_plan")
    catalog = catalog_sheet(int(sheet_no), pieces)
    if operation_order is None:
        resolved_order = merge_operation_order(
            catalog.operations,
            _saved_operation_keys(existing),
        )
        confirmed = bool((existing or {}).get("cut_path_early_confirmed"))
    else:
        resolved_order = resolve_operation_order(catalog.operations, operation_order)
        confirmed = bool(cut_path_early_confirmed)
    resolved_order, confirmed = confirmed_operation_order(
        resolved_order,
        confirmed=confirmed,
    )
    assigned = assign_sheet_presets(
        catalog=catalog,
        operation_presets=dict(operation_presets),
        path_overrides=dict(path_overrides),
        known_presets=known_presets,
        operation_sources=None if operation_sources is None else dict(operation_sources),
        factory_defaults=dict(factory_defaults or {}),
    )
    profile_payload = dict(machine_profile.get("fingerprint_payload") or {})
    fingerprint = settings_fingerprint(
        operation_presets=assigned.effective_operations,
        path_overrides=assigned.path_overrides,
        presets=known_presets,
        machine_profile=profile_payload,
        operation_order=resolved_order,
        cut_path_early_confirmed=confirmed,
    )
    generation_fingerprint = str((existing or {}).get("generation_fingerprint") or "")
    generated_file = str((existing or {}).get("generated_file") or "")
    status = effective_status(
        generation_fingerprint=generation_fingerprint,
        current_fingerprint=fingerprint,
        stored_plan=plan.identity,
        current_plan=plan.identity,
        generated_file=generated_file,
        file_present=(existing or {}).get("file_present"),
        snapshot_complete=(existing or {}).get("snapshot_complete"),
    )
    return {
        "door_cutting_order": order_name,
        "cutting_plan": plan.name,
        "plan_revision": plan.revision,
        "plan_source_type": plan.source_type,
        "sheet_no": int(sheet_no),
        "sheet_key": f"sheet:{int(sheet_no)}",
        "status": status,
        "settings_fingerprint": fingerprint,
        "cut_path_early_confirmed": confirmed,
        "operations": _operation_rows(
            catalog,
            assigned.stored_operations,
            resolved_order,
            assigned.sources,
            factory_defaults,
            persist=True,
        ),
        "paths": _path_rows(catalog, assigned.path_overrides, _piece_labels(pieces)),
        "keep_generation_snapshot": bool(generation_fingerprint),
        "generated_file": generated_file,
        "generated_by": str((existing or {}).get("generated_by") or ""),
        "generated_on": (existing or {}).get("generated_on"),
    }


__all__ = [
    "build_operational_workspace",
    "operational_board_layout",
    "prepare_sheet_settings",
]
