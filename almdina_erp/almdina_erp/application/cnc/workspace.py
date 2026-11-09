"""Prepare the operational-file workspace from an already approved plan."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.application.cnc.machining_setup import public_sheet_machining
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
    validate_operational_path_rows,
)
from almdina_erp.almdina_erp.domain.cnc.placement import (
    PlacementError,
    build_sheet_placement,
    normalize_cnc_machine,
    placement_fingerprint_payload,
)


def _sheet_numbers(pieces: Sequence[Mapping[str, Any]]) -> list[int]:
    return sorted({int(piece.get("sheet_no") or 0) for piece in pieces if int(piece.get("sheet_no") or 0) > 0})


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _positive(value: Any) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def approved_sheet_size_cm(
    snapshot: Mapping[str, Any] | None,
    *,
    sheet_no: int,
) -> tuple[float, float]:
    """Return approved full-board sheet width/length in centimetres (X, Y)."""

    plan = dict(snapshot or {})
    sheets = plan.get("sheets") if isinstance(plan.get("sheets"), list) else []
    sheet: Mapping[str, Any] = {}
    for index, row in enumerate(sheets, start=1):
        if isinstance(row, Mapping) and int(row.get("sheet_no") or index) == int(sheet_no):
            sheet = row
            break
    width = _positive(sheet.get("full_width_cm")) or _positive(plan.get("full_board_width_cm"))
    length = _positive(sheet.get("full_length_cm")) or _positive(plan.get("full_board_length_cm"))
    if width is None or length is None:
        raise OperationalFileError("sheet_frame_unknown")
    return width, length


def resolve_sheet_placement(
    *,
    machine: Mapping[str, Any] | None,
    sheet_width_cm: float,
    sheet_length_cm: float,
    offset_left_cm: Any,
    offset_bottom_cm: Any,
    require_machine: bool = False,
):
    """Validate optional/required placement against approved sheet size."""

    machine_name = str((machine or {}).get("name") or (machine or {}).get("machine_name") or "").strip()
    if not machine_name:
        if require_machine:
            raise PlacementError("cnc_machine_required")
        return None
    if not bool((machine or {}).get("enabled", True)):
        raise PlacementError("cnc_machine_disabled")
    try:
        return build_sheet_placement(
            machine=normalize_cnc_machine(
                machine_name=machine_name,
                width_cm=(machine or {}).get("width_cm"),
                length_cm=(machine or {}).get("length_cm"),
            ),
            sheet_width_cm=sheet_width_cm,
            sheet_length_cm=sheet_length_cm,
            offset_left_cm=0 if offset_left_cm in (None, "") else offset_left_cm,
            offset_bottom_cm=0 if offset_bottom_cm in (None, "") else offset_bottom_cm,
        )
    except PlacementError:
        raise


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
        factory_preset = str(defaults.get(key) or "").strip()
        if key == "sheet_perimeter" and not factory_preset:
            factory_preset = str(defaults.get("cut_path") or "").strip()
        rows.append(
            {
                "operation_key": key,
                "dxf_layer": operation.dxf_layer,
                "sequence": index,
                "tool_preset": presets.get(key, ""),
                "preset_source": public_source,
                "factory_preset": factory_preset,
                "path_count": counts.get(key, 0),
            }
        )
    return rows


def _path_rows(
    catalog,
    overrides: Mapping[str, str],
    labels: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY

    labels = labels or {}
    return [
        {
            "path_key": path.path_key,
            "operation_key": path.operation_key,
            "dxf_layer": path.dxf_layer,
            "piece_instance_id": path.piece_instance_id,
            "piece_label": (
                ""
                if path.path_key == SHEET_PERIMETER_PATH_KEY
                else labels.get(path.piece_instance_id, "")
            ),
            "is_sheet_perimeter": path.path_key == SHEET_PERIMETER_PATH_KEY,
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
    cnc_machines: Sequence[Mapping[str, Any]] | None = None,
    plan_snapshot: Mapping[str, Any] | None = None,
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
    from almdina_erp.almdina_erp.domain.cnc.operational_file import (
        apply_legacy_cut_path_sequence_to_order,
        derive_legacy_cut_path_sequence,
        sheet_perimeter_precedes_milling,
    )
    from almdina_erp.almdina_erp.domain.cnc.operations import SHEET_PERIMETER_OPERATION_KEY
    from almdina_erp.almdina_erp.domain.cnc.perimeter import (
        PERIMETER_JOIN_CONNECTED,
        normalize_perimeter_join_mode,
    )

    for sheet_no in _sheet_numbers(pieces):
        saved = _saved_for(
            saved_files,
            plan_name=plan.name,
            revision=plan.revision,
            sheet_no=sheet_no,
        )
        join_mode = normalize_perimeter_join_mode((saved or {}).get("perimeter_join_mode"))
        catalog = catalog_sheet(
            sheet_no,
            pieces,
            include_sheet_perimeter=join_mode == PERIMETER_JOIN_CONNECTED,
        )
        order = merge_operation_order(catalog.operations, _saved_operation_keys(saved))
        if join_mode == PERIMETER_JOIN_CONNECTED and saved is not None:
            # Only apply legacy sequence when the saved rows never listed the
            # independent operation (pre-promotion documents).
            saved_keys = set(_saved_operation_keys(saved))
            if SHEET_PERIMETER_OPERATION_KEY not in saved_keys:
                order = apply_legacy_cut_path_sequence_to_order(
                    order,
                    (saved or {}).get("cut_path_sequence"),
                    join_mode=join_mode,
                )
        confirmed = bool((saved or {}).get("cut_path_early_confirmed"))
        perimeter_early = bool((saved or {}).get("perimeter_cut_early_confirmed"))
        sequence = (
            derive_legacy_cut_path_sequence(order)
            if join_mode == PERIMETER_JOIN_CONNECTED
            else ()
        )
        if join_mode == PERIMETER_JOIN_CONNECTED and not sheet_perimeter_precedes_milling(order):
            perimeter_early = False
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
        if (
            SHEET_PERIMETER_OPERATION_KEY in proposed
            and sources.get(SHEET_PERIMETER_OPERATION_KEY) == FACTORY_PRESET_SOURCE
            and not str(factory_defaults.get(SHEET_PERIMETER_OPERATION_KEY) or "").strip()
        ):
            inherited = str(proposed.get("cut_path") or "").strip()
            if inherited:
                proposed[SHEET_PERIMETER_OPERATION_KEY] = inherited
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
            machine_name = str((saved or {}).get("cnc_machine") or "").strip()
            machine_row = next(
                (
                    row
                    for row in (cnc_machines or ())
                    if str(row.get("name") or "") == machine_name
                ),
                None,
            )
            placement_fp: dict[str, Any] = {}
            if machine_row is not None:
                try:
                    sheet_w, sheet_l = approved_sheet_size_cm(plan_snapshot, sheet_no=sheet_no)
                    placement = resolve_sheet_placement(
                        machine=machine_row,
                        sheet_width_cm=sheet_w,
                        sheet_length_cm=sheet_l,
                        offset_left_cm=(saved or {}).get("offset_left_cm"),
                        offset_bottom_cm=(saved or {}).get("offset_bottom_cm"),
                    )
                    placement_fp = placement_fingerprint_payload(placement)
                except (OperationalFileError, PlacementError):
                    placement_fp = {
                        "cnc_machine": machine_name,
                        "offset_left_cm": (saved or {}).get("offset_left_cm"),
                        "offset_bottom_cm": (saved or {}).get("offset_bottom_cm"),
                        "machine_missing_or_invalid": True,
                    }
            elif machine_name:
                placement_fp = {
                    "cnc_machine": machine_name,
                    "offset_left_cm": (saved or {}).get("offset_left_cm"),
                    "offset_bottom_cm": (saved or {}).get("offset_bottom_cm"),
                    "machine_missing_or_invalid": True,
                }
            current_fingerprint = settings_fingerprint(
                operation_presets=proposed,
                path_overrides=overrides,
                presets=known_presets,
                machine_profile=profile_payload["fingerprint_payload"],
                operation_order=order,
                cut_path_early_confirmed=confirmed,
                perimeter_join_mode=join_mode,
                cut_path_sequence=sequence,
                perimeter_cut_early_confirmed=perimeter_early,
                sheet_placement=placement_fp,
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
        sheet_width_cm = None
        sheet_length_cm = None
        try:
            sheet_width_cm, sheet_length_cm = approved_sheet_size_cm(
                plan_snapshot, sheet_no=sheet_no
            )
        except OperationalFileError:
            sheet_width_cm = None
            sheet_length_cm = None
        sheets.append(
            {
                "sheet_no": sheet_no,
                "sheet_key": f"sheet:{sheet_no}",
                "operational_file": operational_file,
                "persisted": bool(operational_file),
                "status": status,
                "settings_fingerprint": fingerprint,
                "cut_path_early_confirmed": confirmed,
                "perimeter_join_mode": join_mode,
                "cut_path_sequence": list(sequence),
                "perimeter_cut_early_confirmed": perimeter_early,
                "cnc_machine": str((saved or {}).get("cnc_machine") or ""),
                "offset_left_cm": float((saved or {}).get("offset_left_cm") or 0),
                "offset_bottom_cm": float((saved or {}).get("offset_bottom_cm") or 0),
                "sheet_width_cm": sheet_width_cm,
                "sheet_length_cm": sheet_length_cm,
                "operations": _operation_rows(
                    catalog,
                    proposed,
                    order,
                    sources,
                    factory_defaults,
                ),
                "paths": _path_rows(catalog, overrides if saved is not None else {}, labels),
                "machining": public_sheet_machining(
                    paths=_path_rows(catalog, overrides if saved is not None else {}, labels),
                    profiles=(saved or {}).get("machining_profiles"),
                    associations=(saved or {}).get("vector_associations"),
                    snapshots=(saved or {}).get("toolpath_snapshots"),
                ),
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
        "cnc_machines": [
            {
                "name": str(row.get("name") or ""),
                "machine_name": str(row.get("machine_name") or row.get("name") or ""),
                "width_cm": float(row.get("width_cm") or 0),
                "length_cm": float(row.get("length_cm") or 0),
                "enabled": bool(row.get("enabled", True)),
            }
            for row in (cnc_machines or ())
        ],
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
                "tool_type": str(values.get("tool_type") or ""),
                "tool_units": str(values.get("tool_units") or ""),
                "rate_units": str(values.get("rate_units") or ""),
                "notes": str(values.get("notes") or ""),
                "description": str(values.get("description") or values.get("tool_name") or ""),
                "diameter_mm": values.get("diameter_mm", values.get("tool_diameter_mm")),
                "stepdown_mm": values.get("stepdown_mm"),
                "final_tool_offset_mm": values.get("final_tool_offset_mm"),
                "stepover_size_mm": values.get("stepover_size_mm"),
                "stepover_percent": values.get("stepover_percent"),
                "feed_rate_mm_sec": values.get("feed_rate_mm_sec"),
                "plunge_rate_mm_sec": values.get("plunge_rate_mm_sec"),
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
    perimeter_join_mode: str | None = None,
    cut_path_sequence: Sequence[str] | None = None,
    perimeter_cut_early_confirmed: bool | None = None,
    cnc_machine: str | None = None,
    offset_left_cm: Any = None,
    offset_bottom_cm: Any = None,
    machine_catalog: Sequence[Mapping[str, Any]] | None = None,
    plan_snapshot: Mapping[str, Any] | None = None,
    require_cnc_machine: bool = False,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.domain.cnc.operational_file import (
        apply_legacy_cut_path_sequence_to_order,
        confirmed_perimeter_operation_order,
        derive_legacy_cut_path_sequence,
    )
    from almdina_erp.almdina_erp.domain.cnc.operations import SHEET_PERIMETER_OPERATION_KEY
    from almdina_erp.almdina_erp.domain.cnc.perimeter import (
        PERIMETER_JOIN_CONNECTED,
        PERIMETER_JOIN_SEPARATE,
        normalize_perimeter_join_mode,
    )

    plan = assess_approved_plan(approved_plan, current=plan_is_current)
    if int(sheet_no) not in _sheet_numbers(pieces):
        raise OperationalFileError("sheet_not_in_plan")
    if perimeter_join_mode is None:
        join_mode = normalize_perimeter_join_mode((existing or {}).get("perimeter_join_mode"))
    else:
        join_mode = normalize_perimeter_join_mode(perimeter_join_mode)
    catalog = catalog_sheet(
        int(sheet_no),
        pieces,
        include_sheet_perimeter=join_mode == PERIMETER_JOIN_CONNECTED,
    )
    if operation_order is None:
        resolved_order = merge_operation_order(
            catalog.operations,
            _saved_operation_keys(existing),
        )
        if join_mode == PERIMETER_JOIN_CONNECTED and existing is not None:
            saved_keys = set(_saved_operation_keys(existing))
            if SHEET_PERIMETER_OPERATION_KEY not in saved_keys:
                resolved_order = apply_legacy_cut_path_sequence_to_order(
                    resolved_order,
                    existing.get("cut_path_sequence")
                    if cut_path_sequence is None
                    else cut_path_sequence,
                    join_mode=join_mode,
                )
        confirmed = bool((existing or {}).get("cut_path_early_confirmed"))
    else:
        resolved_order = resolve_operation_order(catalog.operations, operation_order)
        confirmed = bool(cut_path_early_confirmed)
    resolved_order, confirmed = confirmed_operation_order(
        resolved_order,
        confirmed=confirmed,
    )
    if perimeter_cut_early_confirmed is None:
        perimeter_early = bool((existing or {}).get("perimeter_cut_early_confirmed"))
    else:
        perimeter_early = bool(perimeter_cut_early_confirmed)
    if join_mode == PERIMETER_JOIN_CONNECTED:
        resolved_order, perimeter_early = confirmed_perimeter_operation_order(
            resolved_order,
            perimeter_early_confirmed=perimeter_early,
        )
        sequence = derive_legacy_cut_path_sequence(resolved_order)
    else:
        sequence = ()
        perimeter_early = False
    assigned = assign_sheet_presets(
        catalog=catalog,
        operation_presets=dict(operation_presets),
        path_overrides=dict(path_overrides),
        known_presets=known_presets,
        operation_sources=None if operation_sources is None else dict(operation_sources),
        factory_defaults=dict(factory_defaults or {}),
    )
    if cnc_machine is None:
        machine_name = str((existing or {}).get("cnc_machine") or "").strip()
    else:
        machine_name = str(cnc_machine or "").strip()
    if offset_left_cm is None:
        left_cm = (existing or {}).get("offset_left_cm")
    else:
        left_cm = offset_left_cm
    if offset_bottom_cm is None:
        bottom_cm = (existing or {}).get("offset_bottom_cm")
    else:
        bottom_cm = offset_bottom_cm
    machine_row = next(
        (
            row
            for row in (machine_catalog or ())
            if str(row.get("name") or "") == machine_name
        ),
        None,
    )
    placement = None
    if require_cnc_machine and not machine_name:
        raise PlacementError("cnc_machine_required")
    if machine_name:
        if machine_row is None:
            raise PlacementError("cnc_machine_not_found")
        sheet_w, sheet_l = approved_sheet_size_cm(plan_snapshot, sheet_no=int(sheet_no))
        placement = resolve_sheet_placement(
            machine=machine_row,
            sheet_width_cm=sheet_w,
            sheet_length_cm=sheet_l,
            offset_left_cm=left_cm,
            offset_bottom_cm=bottom_cm,
            require_machine=True,
        )
    profile_payload = dict(machine_profile.get("fingerprint_payload") or {})
    placement_fp = placement_fingerprint_payload(placement)
    fingerprint = settings_fingerprint(
        operation_presets=assigned.effective_operations,
        path_overrides=assigned.path_overrides,
        presets=known_presets,
        machine_profile=profile_payload,
        operation_order=resolved_order,
        cut_path_early_confirmed=confirmed,
        perimeter_join_mode=join_mode,
        cut_path_sequence=sequence,
        perimeter_cut_early_confirmed=perimeter_early,
        sheet_placement=placement_fp,
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
        "perimeter_join_mode": join_mode if join_mode == PERIMETER_JOIN_CONNECTED else PERIMETER_JOIN_SEPARATE,
        "cut_path_sequence": list(sequence),
        "perimeter_cut_early_confirmed": perimeter_early,
        "cnc_machine": placement.machine_name if placement else "",
        "offset_left_cm": placement.offset_left_cm if placement else 0.0,
        "offset_bottom_cm": placement.offset_bottom_cm if placement else 0.0,
        "sheet_placement": placement_fp,
        "operations": _operation_rows(
            catalog,
            assigned.stored_operations,
            resolved_order,
            assigned.sources,
            factory_defaults,
            persist=True,
        ),
        "paths": validate_operational_path_rows(
            _path_rows(catalog, assigned.path_overrides, _piece_labels(pieces))
        ),
        "keep_generation_snapshot": bool(generation_fingerprint),
        "generated_file": generated_file,
        "generated_by": str((existing or {}).get("generated_by") or ""),
        "generated_on": (existing or {}).get("generated_on"),
    }


__all__ = [
    "approved_sheet_size_cm",
    "build_operational_workspace",
    "operational_board_layout",
    "prepare_sheet_settings",
    "resolve_sheet_placement",
]
