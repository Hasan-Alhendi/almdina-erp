"""Thin RPC boundary for CNC operational files.

Authorization and the current approved plan are resolved here. Machining
rules stay in the domain. NC text is generated on demand through the existing
post processor and is never treated as a workshop controller approval.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.cnc.machining_setup import (
    accept_sheet_machining,
    calculation_preset_injection,
    freeze_calculated_toolpath,
    remember_toolpath_on_association,
    sheet_profiles_with_catalog,
)
from almdina_erp.almdina_erp.application.cnc.nc_export import build_post_processed_nc
from almdina_erp.almdina_erp.application.cnc.program import _kerf_mm, compile_sheet_program
from almdina_erp.almdina_erp.application.cnc.simulation_nc import (
    nc_content_sha256,
    nc_download_payload,
    nc_export_filename,
)
from almdina_erp.almdina_erp.application.cnc.workspace import (
    approved_sheet_size_cm,
    build_operational_workspace,
    operational_board_layout,
    prepare_sheet_settings,
    resolve_sheet_placement,
)
from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    MachiningSetupError,
    archive_association,
    catalog_rows_from_program,
    clear_reversed_direction_conflicts,
    drop_resurrected_associations,
    effective_operational_program,
    reversed_direction_block,
    toggle_reversed_path,
    unreversed_operational_program,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    OperationalFileError,
    assert_viewed_plan_token,
    operation_preset_choice,
)
from almdina_erp.almdina_erp.domain.cnc.placement import PlacementError
from almdina_erp.almdina_erp.domain.cnc.post_processor import PostProcessorError
from almdina_erp.almdina_erp.domain.cnc.tool_preset import ToolPresetError
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
    doctype_has_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.cutting.cnc_dxf_source import read_operational_dxf
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import DxfReadError
from almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository import (
    approved_plan_ref,
    approved_plan_snapshot,
    factory_operation_defaults,
    get_cnc_machine,
    known_tool_presets,
    list_cnc_machines,
    machining_profile_catalog,
    machine_profile_view,
    manufacturing_source,
    placed_piece_views,
    record_nc_generation,
    save_sheet,
    saved_operational_files,
    update_machining_json,
)


_NO_APPROVED_PLAN = (
    "This order has no approved cutting plan. Operational files can be prepared "
    "only from the current approved plan, whether the system calculated it or "
    "it was uploaded and then approved."
)
_MESSAGES = {
    "no_approved_plan": _NO_APPROVED_PLAN,
    "draft_plan": _NO_APPROVED_PLAN,
    "plan_not_current": _NO_APPROVED_PLAN,
    "unsupported_plan_source": "This approved plan source cannot be used for operational files.",
    "missing_piece_instance_id": "The approved plan is missing a stable piece identity.",
    "liner_specs_invalid": "The approved plan liner setup cannot be read.",
    "sheet_not_in_plan": "That sheet is not part of the approved cutting plan.",
    "unknown_operation": "That machining operation is not on this sheet.",
    "unknown_path": "That machining path is not on this sheet.",
    "preset_not_found": "The selected CNC tool preset does not exist.",
    "preset_disabled": "The selected CNC tool preset is disabled.",
    "tool_identity_conflict": "One board file must keep the same physical tool number.",
    "mill_group_diameter_conflict": "The same milling group cannot use different tool diameters.",
    "tool_type_invalid": "Choose a tool type.",
    "tool_type_unsupported": "Only a Ball Nose tool can be created here.",
    "tool_units_invalid": "Tool units must be mm.",
    "rate_units_invalid": "Rate units must be mm/sec.",
    "description_required": "Enter the tool description.",
    "notes_invalid": "The tool notes are too long.",
    "stepdown_invalid": "Stepdown must be a positive number of millimetres within the supported range.",
    "final_tool_offset_invalid": "Final tool offset must be zero or a positive number of millimetres within the supported range.",
    "stepover_invalid": "Stepover size must be positive and no greater than the tool diameter.",
    "profile_name_required": "Enter a profile name.",
    "profile_invalid": "The profile is not valid.",
    "profile_duplicate": "Each profile needs its own name.",
    "profile_id_invalid": "The profile identity is not valid.",
    "profile_not_found": "The selected profile does not exist.",
        "tool_preset_required": "Choose a tool for this profile.",
    "safe_z_invalid": "Safe Z must be zero or a positive number of millimetres within the supported range.",
    "home_x_invalid": "Home X must be a finite number of millimetres.",
    "home_y_invalid": "Home Y must be a finite number of millimetres.",
    "home_z_invalid": "Home Z must be zero or a positive number of millimetres within the supported range.",
    "association_invalid": "The vector association is not valid.",
    "association_duplicate": "Each vector association needs its own identity.",
    "association_id_invalid": "The vector association identity is not valid.",
    "association_not_found": "The vector association does not exist.",
    "selection_invalid": "Choose a layer, selected vectors, or the sheet perimeter.",
    "vector_not_machinable": "That vector is not a machinable path on this sheet.",
    "vector_already_assigned": "That vector or layer is already assigned.",
    "sheet_perimeter_already_assigned": "The sheet perimeter already belongs to {0}. Edit that association and release the sheet perimeter before assigning it on its own.",
    "layer_not_machinable": "That layer has no machinable vectors on this sheet.",
    "selected_vectors_pending": "Selected Vectors needs a direct selection on the board before this association can be calculated.",
    "sheet_perimeter_unavailable": "Sheet Perimeter is available only while Connected Perimeter is enabled.",
    "toolpath_name_required": "Enter a toolpath name.",
    "toolpath_name_duplicate": "A calculated toolpath already uses that name.",
    "vector_identity_ambiguous": "That path key matches more than one vector. Select the vector on the board again.",
    "association_stale": "The sheet changed in another window. Reload it before repeating this action.",
    "toolpath_duplicate": "That calculated toolpath already exists.",
    "toolpath_id_invalid": "The toolpath identity is not valid.",
    "tool_number_invalid": "Tool Number must be a positive whole number.",
    "tool_diameter_invalid": "Tool diameter must be a positive number of millimetres within the supported range.",
    "final_depth_invalid": "Final depth must be a positive number of millimetres within the supported range.",
    "spindle_speed_invalid": "Spindle speed must be a positive whole number of RPM within the supported range.",
    "feed_rate_invalid": "Feed rate must be a positive number of millimetres per minute within the supported range.",
    "plunge_rate_invalid": "Plunge rate must be a positive number of millimetres per minute within the supported range.",
    "pass_depth_invalid": "Pass depth must be a positive number of millimetres within the supported range.",
    "pass_depth_exceeds_final_depth": "Pass depth cannot be deeper than the final depth.",
    "operation_order_incomplete": "The operation order does not include every operation on this sheet.",
    "cut_path_early_unconfirmed": "Confirm the warning before saving a cut that comes before the internal operations.",
    "preset_source_invalid": "The layer preset source is not valid.",
    "units_unknown": "The drawing units are not millimetres, so the path was not prepared.",
    "units_unspecified": "The drawing does not state its units, so millimetres were not assumed and the path was not prepared.",
    "sheet_frame_unknown": "The sheet frame could not be established, so the path was not prepared.",
    "path_sheet_affiliation_ambiguous": "A machining path overlaps more than one sheet, so it was not assigned.",
    "path_outside_sheet": "A machining path is outside the approved sheet outlines.",
    "kerf_unknown": "The kerf is missing, so cutter centers were not calculated.",
    "finished_geometry_missing": "The approved plan has no finished geometry for this piece.",
    "geometry_invalid": "This path geometry cannot be used.",
    "region_not_supported": "This closed region is not a cutter path, and the approved plan does not include the mill settings needed to calculate one.",
    "tool_diameter_kerf_mismatch": "The {0} tool diameter does not match the approved cutting plan.",
    "tool_diameter_plan_mismatch": "The {0} tool diameter does not match the approved cutting plan.",
    "tool_property_locked": "The tool property {0} cannot be changed here. Choose another tool to replace the protected tool properties.",
    "stepover_inconsistent": "Stepover size and stepover percent must describe the same fraction of the tool diameter.",
    "mill_path_unverified": "This milling path is not a verified cutter center for the selected tool.",
    "mill_placement_unknown": "The approved plan does not record where this piece sits, so the milling path was not calculated.",
    "mill_parameters_missing": "The approved plan does not include the side, offset, and width needed to calculate this milling path.",
    "mill_diameter_required": "This milling path needs the layer tool diameter before its cutter center can be calculated.",
    "liner_narrower_than_cutter": "The selected tool is wider than this milling band, so the path was not calculated.",
    "side_unavailable": "This piece shape has no supported side for this milling operation.",
    "merged_mill_preset_ambiguous": "Overlapping milling cannot use a different preset for each path.",
    "mill_upload_mismatch": "The uploaded milling path does not match the approved milling geometry.",
    "geometry_not_ready": "The machining geometry is not ready, so an NC file was not created.",
    "nc_verification_failed": "The generated NC file does not match the intermediate program.",
    "production_controller_not_confirmed": "A production controller is not confirmed for this factory profile.",
    "coordinate_space_unsupported": "This coordinate space cannot be posted to NC.",
    "distance_mode_unsupported": "Only absolute distance mode G90 is supported.",
    "preset_incomplete": "The selected tool preset is missing spindle or feed values needed for NC.",
    "motion_unsupported": "This intermediate motion cannot be posted to NC.",
    "program_invalid": "The intermediate program is not valid.",
    "machine_profile_value_invalid": "The machine profile values are not valid for NC generation.",
    "cut_path_is_piece_boundary": "This cut is the piece boundary, not a cutter center.",
    "compensation_unverified": "The cutter compensation for this path is not verified.",
    "cut_side_unknown": "The cut side of this closed path is not known.",
    "preset_missing": "This path has no tool preset.",
    "shared_cut_preset_ambiguous": "A shared cut cannot use a different preset for each piece.",
    "toolpath_missing": "The approved drawing does not contain this machining path.",
    "cut_path_does_not_match_approved_centers": "The uploaded cut does not match the approved cutter centers.",
    "dxf_unreadable": "The operational drawing could not be read.",
    "stored_nc_unavailable": "Stored NC files are no longer available. Generate NC to download the current file.",
    "path_reverse_unsupported": "This path cannot be reversed safely, so the NC file was not created.",
    "path_reverse_stale": "A saved path direction belongs to an older geometry, so the NC file was not created.",
    "path_reverse_missing": "A saved path direction no longer matches a path on this sheet, so the NC file was not created.",
    "path_reverse_ambiguous": "A saved path direction matches more than one path, so the NC file was not created. Restore the direction, then set it again on the path you want.",
    "sheet_settings_required": "Save the sheet settings before reversing a machining path.",
    "perimeter_join_mode_invalid": "The sheet perimeter join mode is not valid.",
    "perimeter_unavailable": "A connected sheet perimeter could not be formed from the approved cut network.",
    "perimeter_not_closed": "The outer cut network is not a closed perimeter.",
    "perimeter_geometry_ambiguous": "The outer cut network has branches that prevent one safe perimeter.",
    "perimeter_components_disconnected": "The outer cut network has more than one separate component.",
    "perimeter_geometry_invalid": "The connected perimeter would change the approved cut geometry.",
    "cut_path_sequence_invalid": "The CUT_PATH execution order is not valid for this sheet.",
    "perimeter_cut_early_unconfirmed": "Confirm the warning before cutting the sheet perimeter before liner, recessed handle, or rear groove.",
    "missing_piece_instance_id": "Piece-bound CNC paths must keep a piece instance id.",
    "sheet_perimeter_piece_forbidden": "The sheet perimeter path must not be tied to a piece instance.",
    "sheet_perimeter_duplicate": "A sheet may keep only one connected perimeter path.",
    "cnc_machine_required": "Choose a CNC machine before generating the NC file.",
    "cnc_machine_not_found": "The selected CNC machine was not found.",
    "cnc_machine_disabled": "The selected CNC machine is disabled.",
    "cnc_machine_name_required": "CNC machine name is required.",
    "cnc_machine_width_invalid": "CNC machine width must be a positive number of centimetres.",
    "cnc_machine_length_invalid": "CNC machine length must be a positive number of centimetres.",
    "offset_left_invalid": "The left stop must be zero or a positive number of centimetres.",
    "offset_right_invalid": "The right stop must be zero or a positive number of centimetres.",
    "offset_bottom_invalid": "The bottom stop must be zero or a positive number of centimetres.",
    "offset_top_invalid": "The top stop must be zero or a positive number of centimetres.",
    "cnc_machine_stops_unconfigured": (
        "Set the two stops for this work zero on the CNC machine. "
        "A stop from another edge is not copied across."
    ),
    "cnc_machine_stop_sides_required": (
        "Choose the width stop side and the length stop side on the CNC machine before generating a new file."
    ),
    "work_zero_invalid": "The selected work zero is not supported.",
    "work_zero_center_retired": (
        "This CNC machine still uses Center as its work zero. "
        "Choose Bottom Left, Bottom Right, Top Left, or Top Right before generating a new file."
    ),
    "sheet_width_invalid": "The approved sheet width is not valid.",
    "sheet_length_invalid": "The approved sheet length is not valid.",
    "sheet_exceeds_machine_width": "The board is larger than the machine width. NC cannot be generated.",
    "sheet_exceeds_machine_length": "The board is larger than the machine length. NC cannot be generated.",
    "placement_incomplete": "Sheet placement on the CNC machine is incomplete.",
    "post_processor_required": "Choose a post processor before generating the NC file.",
    "post_processor_unsupported": "The selected post processor is not supported.",
    "cnc_machine_post_processor_unconfigured": (
        "Complete the CNC machine settings. Choose the post processor on the machine before generating a new NC file."
    ),
    "post_processor_machine_mismatch": (
        "The post processor is set on the CNC machine and cannot be overridden for this sheet."
    ),
    "machine_parking_outside_limits": "The IMA-WH parking move is outside the selected machine.",
    "machine_parking_unverified": "The selected machine travel is not known, so the IMA-WH parking move was not posted.",
    "profile_home_missing": "The last machining profile has no home position.",
    "profile_home_outside_machine": "The profile home is outside the selected machine.",
    "profile_home_unsafe": "The profile home is not high enough for a safe move.",
    "home_move_unsafe": "The move to profile home would travel at cutting depth.",
    "tool_number_invalid": "The tool number cannot be posted.",
    "feed_rate_inconsistent": "The feed rate and plunge rate do not match their per-minute values.",
    "tool_identity_conflict": "This sheet uses more than one tool number, so the NC file was not created.",
    "line_number_overflow": "The NC program is too long for the selected post processor.",
    "nc_not_ascii": "The NC program contains a character this post processor cannot write.",
}


def _message(code: str) -> str:
    return _(_MESSAGES.get(code, _NO_APPROVED_PLAN))


_DIAMETER_ISSUE_CODES = frozenset({"tool_diameter_kerf_mismatch", "tool_diameter_plan_mismatch"})
_LAYER_NAMES = {
    "cut_path": "CUT_PATH",
    "sheet_perimeter": "Sheet Perimeter",
    "liner": "Liner",
    "recessed_handle_cutout": "Handle Recess",
    "back_groove": "Rear Groove",
}


def _layer_name(operation_key: str) -> str:
    return _(_LAYER_NAMES.get(str(operation_key or ""), str(operation_key or "")))


def _diameter_dialog_parts(operation_key: str, approved: str, selected: str) -> tuple[str, str, str]:
    layer = _layer_name(operation_key)
    problem = _("The {0} tool diameter does not match the approved cutting plan.").format(layer)
    where = _("{0} — approved diameter {1} mm, selected diameter {2} mm.").format(layer, approved, selected)
    action = _("Choose a tool whose diameter is {0} mm, the diameter used to create the approved paths.").format(approved)
    return problem, where, action


def _diameter_dialog_message(detail: str) -> str:
    operation_key, approved, selected = (detail.split("|") + ["", "", ""])[:3]
    problem, where, action = _diameter_dialog_parts(operation_key, approved, selected)
    return "\n".join((problem, where, action))


def _diameter_program_message(program: Mapping[str, Any]) -> str:
    """The first diameter mismatch, in the same three sentences the popup shows."""

    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping):
                continue
            for detail in path.get("issue_details") or ():
                if not isinstance(detail, Mapping):
                    continue
                if str(detail.get("code") or "") not in _DIAMETER_ISSUE_CODES:
                    continue
                return _diameter_dialog_message("|".join((
                    str(detail.get("operation_key") or ""),
                    _plain_diameter(detail.get("approved_diameter_mm")),
                    _plain_diameter(detail.get("selected_diameter_mm")),
                )))
    return ""


def _failure_message(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "")
    detail = str(getattr(exc, "detail", "") or "")
    if code in _DIAMETER_ISSUE_CODES and detail.count("|") >= 2:
        return _diameter_dialog_message(detail)
    template = _MESSAGES.get(code, "")
    if template and "{0}" in template:
        return _(template).format(detail or "—")
    if code in {"path_reverse_unsupported", "path_reverse_stale", "path_reverse_missing", "path_reverse_ambiguous"}:
        return _issue_message(code, detail)
    return _message(code)


def _issue_message(code: str, path_key: str = "", detail: dict[str, Any] | None = None) -> str:
    if code in _DIAMETER_ISSUE_CODES and isinstance(detail, dict) and detail.get("approved_diameter_mm") is not None:
        problem, _where, _action = _diameter_dialog_parts(
            str(detail.get("operation_key") or ""),
            _plain_diameter(detail.get("approved_diameter_mm")),
            _plain_diameter(detail.get("selected_diameter_mm")),
        )
        return problem
    if code == "tool_diameter_kerf_mismatch":
        return _(
            "CUT_PATH {0} was calculated for the approved kerf and does not match the selected tool diameter."
        ).format(path_key or _("the shared cut"))
    if code in {
        "path_reverse_unsupported",
        "path_reverse_stale",
        "path_reverse_missing",
        "path_reverse_ambiguous",
    } and path_key:
        return f"{_message(code)} ({path_key})"
    return _message(code)


def _authorized_order(order_name: str, capability: str) -> Any:
    name = str(order_name or "").strip()
    if not name or not frappe.db.exists("Door Cutting Order", name):
        frappe.throw(
            _("Door Cutting Order {0} was not found.").format(name or "—"),
            frappe.DoesNotExistError,
        )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_document_capability(
        order,
        capability,
        message=_("You do not have permission to use operational files for this order."),
    )
    return order


def _workspace_for(order: Any, *, can_prepare: bool) -> dict[str, Any]:
    plan = approved_plan_ref(order)
    try:
        pieces = placed_piece_views(order) if plan is not None else []
        snapshot = approved_plan_snapshot(order) if plan is not None else None
        workspace = build_operational_workspace(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=plan is not None,
            pieces=pieces,
            saved_files=saved_operational_files(str(order.name)),
            factory_defaults=factory_operation_defaults(),
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            can_prepare=can_prepare,
            cnc_machines=list_cnc_machines(),
            plan_snapshot=snapshot,
        )
    except (
        OperationalFileError,
        ToolPresetError,
        PlacementError,
        MachiningSetupError,
        PostProcessorError,
    ) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc
    workspace["message"] = _message(workspace["reason_code"]) if workspace["reason_code"] else ""
    workspace["can_edit_factory_cnc"] = doctype_has_capability(Capability.EDIT_FACTORY_CNC_DEFAULTS)
    workspace["machining_profile_catalog"] = machining_profile_catalog()
    try:
        workspace["layout"] = (
            operational_board_layout(approved_plan_snapshot(order))
            if workspace["eligible"]
            else None
        )
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc
    for sheet in workspace["sheets"]:
        try:
            width_cm, length_cm = approved_sheet_size_cm(
                approved_plan_snapshot(order) if plan is not None else None,
                sheet_no=int(sheet.get("sheet_no") or 0),
            )
            sheet["sheet_width_cm"] = width_cm
            sheet["sheet_length_cm"] = length_cm
        except (OperationalFileError, json.JSONDecodeError):
            sheet["sheet_width_cm"] = None
            sheet["sheet_length_cm"] = None
    return workspace


@frappe.whitelist()
def get_cnc_operational_workspace(order_name: str) -> dict[str, Any]:
    order = _authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)
    can_prepare = document_has_capability(
        order,
        Capability.PREPARE_CNC_OPERATIONAL_FILES,
    )
    return _workspace_for(order, can_prepare=can_prepare)


def _revision(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _reject_stale_sheet(saved: Mapping[str, Any] | None, base_revision: Any) -> None:
    expected = _revision(base_revision)
    if not saved:
        if expected not in (-1, 0):
            frappe.throw(_message("association_stale"), frappe.ValidationError)
        return
    current = max(1, _revision(saved.get("settings_revision")))
    if expected != current:
        frappe.throw(_message("association_stale"), frappe.ValidationError)


def _snapshot_for_request(snapshots: Any, request_id: str, association_id: str) -> bool:
    for snapshot in snapshots or ():
        if not isinstance(snapshot, Mapping):
            continue
        if str(snapshot.get("request_id") or "") == request_id and str(snapshot.get("association_id") or "") == association_id:
            return True
    return False


def _json_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    parsed = frappe.parse_json(raw) if isinstance(raw, str) else raw
    if isinstance(parsed, str):
        parsed = frappe.parse_json(parsed) if parsed.strip() else []
    if not isinstance(parsed, list):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    return list(parsed)


def _parse_optional_sequence(raw: str | list[Any] | None) -> list[str] | None:
    """None/empty mean 'use default'. A non-empty list is an explicit custom order."""

    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    parsed = frappe.parse_json(raw) if isinstance(raw, str) else list(raw)
    if not isinstance(parsed, list):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    items = [str(item) for item in parsed if str(item or "").strip()]
    return items or None


@frappe.whitelist()
def save_cnc_operational_sheet(
    order_name: str,
    sheet_no: int | str,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    viewed_plan_token: str | None = None,
    operation_sources: str | dict[str, Any] | None = None,
    perimeter_join_mode: str | None = None,
    cut_path_sequence: str | list[Any] | None = None,
    perimeter_cut_early_confirmed: int | str | bool | None = None,
    cnc_machine: str | None = None,
    offset_left_cm: float | int | str | None = None,
    offset_bottom_cm: float | int | str | None = None,
    post_processor: str | None = None,
    machining_profiles: str | list[Any] | None = None,
    vector_associations: str | list[Any] | None = None,
    base_revision: int | str | None = None,
) -> dict[str, Any]:
    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    existing = _existing_sheet(str(order.name), plan, cint(sheet_no))
    _reject_stale_sheet(existing, base_revision)
    parsed_operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
    if path_overrides is None and existing is not None:
        parsed_paths = {
            str(row.get("path_key") or ""): row.get("tool_preset")
            for row in existing.get("paths") or []
            if str(row.get("tool_preset") or "").strip()
        }
    else:
        parsed_paths = frappe.parse_json(path_overrides) if isinstance(path_overrides, str) else dict(path_overrides or {})
    if operation_order is None:
        parsed_order = None
    else:
        parsed_order = frappe.parse_json(operation_order) if isinstance(operation_order, str) else list(operation_order)
    if operation_sources is None:
        parsed_sources = None
    else:
        parsed_sources = frappe.parse_json(operation_sources) if isinstance(operation_sources, str) else dict(operation_sources)
    parsed_sequence = _parse_optional_sequence(cut_path_sequence)
    if not isinstance(parsed_operations, dict) or not isinstance(parsed_paths, dict) or (
        parsed_order is not None and not isinstance(parsed_order, list)
    ) or (parsed_sources is not None and not isinstance(parsed_sources, dict)):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    direction_snapshots = list((existing or {}).get("toolpath_snapshots") or [])
    direction_associations = list((existing or {}).get("vector_associations") or [])
    stored_profiles: list[dict[str, Any]] | None = None
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        sheet_arguments = {
            "order_name": str(order.name),
            "approved_plan": plan,
            "plan_is_current": plan is not None,
            "pieces": placed_piece_views(order),
            "sheet_no": cint(sheet_no),
            "existing": existing,
            "operation_presets": {str(key): value for key, value in parsed_operations.items()},
            "path_overrides": {str(key): value for key, value in parsed_paths.items()},
            "known_presets": known_tool_presets(),
            "machine_profile": machine_profile_view(),
            "operation_order": None if parsed_order is None else [str(item) for item in parsed_order],
            "cut_path_early_confirmed": (
                None if parsed_order is None else bool(cint(cut_path_early_confirmed))
            ),
            "operation_sources": None if parsed_sources is None else {
                str(key): value for key, value in parsed_sources.items()
            },
            "factory_defaults": factory_operation_defaults(),
            "perimeter_join_mode": perimeter_join_mode,
            "cut_path_sequence": parsed_sequence,
            "perimeter_cut_early_confirmed": (
                None
                if perimeter_cut_early_confirmed is None
                else bool(cint(perimeter_cut_early_confirmed))
            ),
            "cnc_machine": cnc_machine,
            "offset_left_cm": offset_left_cm,
            "offset_bottom_cm": offset_bottom_cm,
            "post_processor": post_processor,
            "machine_catalog": list_cnc_machines(),
            "plan_snapshot": approved_plan_snapshot(order),
            "require_cnc_machine": False,
        }
        prepared = prepare_sheet_settings(**sheet_arguments)
        if machining_profiles is not None or vector_associations is not None:
            snapshots = list((existing or {}).get("toolpath_snapshots") or [])
            incoming_associations = (
                _json_list(vector_associations)
                if vector_associations is not None
                else list((existing or {}).get("vector_associations") or [])
            )
            incoming_associations = drop_resurrected_associations(
                list((existing or {}).get("vector_associations") or []),
                incoming_associations,
                snapshots,
            )
            source_operations = {
                str(row.get("operation_key") or ""): row.get("tool_preset")
                for row in prepared.get("operations") or []
                if str(row.get("operation_key") or "")
            }
            source_paths = {
                str(row.get("path_key") or ""): row.get("tool_preset")
                for row in prepared.get("paths") or []
                if str(row.get("path_key") or "") and str(row.get("tool_preset") or "").strip()
            }
            source_order = [
                str(row.get("operation_key") or "")
                for row in prepared.get("operations") or []
                if str(row.get("operation_key") or "")
            ]
            base_known = known_tool_presets()
            _plan, source_program, _presets = _compile_authorized_program(
                order,
                sheet_no=cint(sheet_no),
                operation_presets=source_operations,
                path_overrides=source_paths,
                operation_order=source_order,
                cut_path_early_confirmed=bool(prepared.get("cut_path_early_confirmed")),
                viewed_plan_token=viewed_plan_token,
                perimeter_join_mode=str(prepared.get("perimeter_join_mode") or "separate"),
                cut_path_sequence=list(prepared.get("cut_path_sequence") or []),
                perimeter_cut_early_confirmed=bool(prepared.get("perimeter_cut_early_confirmed")),
                known_presets=base_known,
            )
            source_catalog = catalog_rows_from_program(source_program)
            profiles, associations = accept_sheet_machining(
                paths=source_catalog,
                stored_profiles=_trusted_machining_profiles(existing),
                profiles=sheet_profiles_with_catalog(
                    _json_list(machining_profiles)
                    if machining_profiles is not None
                    else list((existing or {}).get("machining_profiles") or []),
                    incoming_associations,
                    machining_profile_catalog(),
                ),
                associations=incoming_associations,
                known_tools=base_known,
                snapshots=snapshots,
            )
            direction_snapshots = snapshots
            direction_associations = associations
            stored_profiles = profiles
            prepared = prepare_sheet_settings(
                **sheet_arguments,
                toolpath_snapshots=snapshots,
                vector_associations=associations,
            )
        direction_records = _reconciled_direction_records(
            order,
            sheet_no=cint(sheet_no),
            prepared=prepared,
            saved=existing,
            viewed_plan_token=viewed_plan_token,
            snapshots=direction_snapshots,
            associations=direction_associations,
        )
        prepared = prepare_sheet_settings(
            **sheet_arguments,
            toolpath_snapshots=direction_snapshots,
            vector_associations=direction_associations,
            reversed_path_keys=direction_records,
        )
        if stored_profiles is not None:
            prepared["machining_profiles_json"] = stored_profiles
            prepared["vector_associations_json"] = direction_associations
    except (OperationalFileError, ToolPresetError, PlacementError, MachiningSetupError, PostProcessorError) as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    existing_name = str((existing or {}).get("name") or "")
    try:
        save_sheet(existing_name, prepared, expected_revision=_revision(base_revision))
    except OperationalFileError as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    return _workspace_for(order, can_prepare=True)


@frappe.whitelist()
def calculate_cnc_association_toolpath(
    order_name: str,
    sheet_no: int | str,
    association_id: str,
    toolpath_name: str,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    viewed_plan_token: str | None = None,
    operation_sources: str | dict[str, Any] | None = None,
    perimeter_join_mode: str | None = None,
    cut_path_sequence: str | list[Any] | None = None,
    perimeter_cut_early_confirmed: int | str | bool | None = None,
    cnc_machine: str | None = None,
    offset_left_cm: float | int | str | None = None,
    offset_bottom_cm: float | int | str | None = None,
    machining_profiles: str | list[Any] | None = None,
    vector_associations: str | list[Any] | None = None,
    calculation_request_id: str | None = None,
    base_revision: int | str | None = None,
    post_processor: str | None = None,
) -> dict[str, Any]:
    """Validate, calculate, and save one association in a single request.

    Nothing is written until the toolpath snapshot is complete. A repeated
    request id returns the workspace that the first successful call saved.
    """

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    request_id = str(calculation_request_id or "").strip()
    target_id = str(association_id or "").strip()
    if saved and request_id and _snapshot_for_request(saved.get("toolpath_snapshots"), request_id, target_id):
        return _workspace_for(order, can_prepare=True)
    _reject_stale_sheet(saved, base_revision)
    incoming = drop_resurrected_associations(
        list((saved or {}).get("vector_associations") or []),
        _json_list(vector_associations) if vector_associations is not None else list((saved or {}).get("vector_associations") or []),
        list((saved or {}).get("toolpath_snapshots") or []),
    )
    provisional = next(
        (row for row in incoming if str(row.get("association_id") or "") == target_id),
        None,
    )
    if provisional is None:
        frappe.throw(_message("association_not_found"), frappe.ValidationError)
    if saved:
        (
            operations,
            paths,
            order_keys,
            confirmed,
            _sources,
            join_mode,
            sequence,
            perimeter_early,
        ) = _settings_from_saved(saved, factory_operation_defaults())
    else:
        operations, paths, order_keys = {}, {}, []
        confirmed = False
        join_mode, sequence, perimeter_early = "separate", None, False
    if operation_presets is not None:
        operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
    if path_overrides is not None:
        paths = frappe.parse_json(path_overrides) if isinstance(path_overrides, str) else dict(path_overrides or {})
    if operation_order is not None:
        order_keys = frappe.parse_json(operation_order) if isinstance(operation_order, str) else list(operation_order or [])
    if cut_path_early_confirmed is not None:
        confirmed = bool(cint(cut_path_early_confirmed))
    if perimeter_join_mode is not None:
        join_mode = str(perimeter_join_mode or "separate")
    if cut_path_sequence is not None:
        sequence = _parse_optional_sequence(cut_path_sequence)
    if perimeter_cut_early_confirmed is not None:
        perimeter_early = bool(cint(perimeter_cut_early_confirmed))
    try:
        base_known = known_tool_presets()
        _plan, source_program, _presets = _compile_authorized_program(
            order,
            sheet_no=cint(sheet_no),
            operation_presets=operations if isinstance(operations, dict) else {},
            path_overrides=paths if isinstance(paths, dict) else {},
            operation_order=order_keys if isinstance(order_keys, list) else [],
            cut_path_early_confirmed=confirmed,
            viewed_plan_token=viewed_plan_token,
            perimeter_join_mode=join_mode,
            cut_path_sequence=sequence,
            perimeter_cut_early_confirmed=perimeter_early,
            known_presets=base_known,
        )
        source_catalog = catalog_rows_from_program(source_program)
        profiles, associations = accept_sheet_machining(
            paths=source_catalog,
            stored_profiles=_trusted_machining_profiles(saved),
            profiles=sheet_profiles_with_catalog(
                _json_list(machining_profiles) if machining_profiles is not None else list((saved or {}).get("machining_profiles") or []),
                incoming,
                machining_profile_catalog(),
            ),
            associations=incoming,
            known_tools=base_known,
            snapshots=list((saved or {}).get("toolpath_snapshots") or []),
        )
        association = next(
            (row for row in associations if str(row.get("association_id") or "") == target_id),
            None,
        )
        if association is None:
            frappe.throw(_message("association_not_found"), frappe.ValidationError)
        if association.get("conflict") or not association.get("vector_ids"):
            raise MachiningSetupError(str(association.get("conflict") or "vector_not_machinable"))
        known, overrides = calculation_preset_injection(
            association,
            base_known,
            catalog=source_catalog,
        )
        _plan, program, _presets = _compile_authorized_program(
            order,
            sheet_no=cint(sheet_no),
            operation_presets=operations if isinstance(operations, dict) else {},
            path_overrides=paths if isinstance(paths, dict) else {},
            operation_order=order_keys if isinstance(order_keys, list) else [],
            cut_path_early_confirmed=confirmed,
            viewed_plan_token=viewed_plan_token,
            perimeter_join_mode=join_mode,
            cut_path_sequence=sequence,
            perimeter_cut_early_confirmed=perimeter_early,
            known_presets=known,
            extra_path_overrides=overrides,
        )
        prior_snapshots = list((saved or {}).get("toolpath_snapshots") or [])
        snapshots = freeze_calculated_toolpath(
            association=association,
            toolpath_name=toolpath_name,
            program=program,
            snapshots=prior_snapshots,
            live_association_ids=[str(row.get("association_id") or "") for row in associations],
            request_id=request_id,
        )
        stored_associations = remember_toolpath_on_association(
            associations,
            snapshots,
            target_id,
        )
        restamped = prepare_sheet_settings(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=True,
            pieces=placed_piece_views(order),
            sheet_no=cint(sheet_no),
            existing=saved,
            operation_presets=operations if isinstance(operations, dict) else {},
            path_overrides=paths if isinstance(paths, dict) else {},
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            operation_order=order_keys if isinstance(order_keys, list) else None,
            cut_path_early_confirmed=confirmed,
            factory_defaults=factory_operation_defaults(),
            perimeter_join_mode=join_mode,
            cut_path_sequence=sequence,
            perimeter_cut_early_confirmed=perimeter_early,
            cnc_machine=(saved or {}).get("cnc_machine") if cnc_machine is None else cnc_machine,
            offset_left_cm=(saved or {}).get("offset_left_cm") if offset_left_cm is None else offset_left_cm,
            offset_bottom_cm=(saved or {}).get("offset_bottom_cm") if offset_bottom_cm is None else offset_bottom_cm,
            machine_catalog=list_cnc_machines(),
            plan_snapshot=approved_plan_snapshot(order),
            toolpath_snapshots=snapshots,
            vector_associations=stored_associations,
            post_processor=post_processor,
        )
        restamped["machining_profiles_json"] = profiles
        restamped["vector_associations_json"] = stored_associations
        restamped["toolpath_snapshots_json"] = snapshots
    except (
        OperationalFileError,
        ToolPresetError,
        PlacementError,
        MachiningSetupError,
        PostProcessorError,
    ) as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    try:
        save_sheet(
            str((saved or {}).get("name") or ""),
            restamped,
            expected_revision=_revision(base_revision),
        )
    except OperationalFileError as exc:
        latest = _existing_sheet(str(order.name), plan, cint(sheet_no))
        if (
            exc.code == "association_stale"
            and request_id
            and _snapshot_for_request(
                (latest or {}).get("toolpath_snapshots"),
                request_id,
                target_id,
            )
        ):
            return _workspace_for(order, can_prepare=True)
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    return _workspace_for(order, can_prepare=True)


@frappe.whitelist()
def delete_cnc_association(
    order_name: str,
    sheet_no: int | str,
    association_id: str,
    viewed_plan_token: str | None = None,
    base_revision: int | str | None = None,
) -> dict[str, Any]:
    """Remove one association by its id and archive its snapshots."""

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    if not saved or not saved.get("name"):
        return _workspace_for(order, can_prepare=True)
    _reject_stale_sheet(saved, base_revision)
    target = str(association_id or "").strip()
    current = list(saved.get("vector_associations") or [])
    if not any(str(row.get("association_id") or "") == target for row in current):
        return _workspace_for(order, can_prepare=True)
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        kept, snapshots = archive_association(current, list(saved.get("toolpath_snapshots") or []), target)
        (
            operations,
            paths,
            order_keys,
            confirmed,
            _sources,
            join_mode,
            sequence,
            perimeter_early,
        ) = _settings_from_saved(saved, factory_operation_defaults())
        restamped = prepare_sheet_settings(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=True,
            pieces=placed_piece_views(order),
            sheet_no=cint(sheet_no),
            existing=saved,
            operation_presets=operations,
            path_overrides=paths,
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            operation_order=order_keys,
            cut_path_early_confirmed=confirmed,
            factory_defaults=factory_operation_defaults(),
            perimeter_join_mode=join_mode,
            cut_path_sequence=sequence,
            perimeter_cut_early_confirmed=perimeter_early,
            cnc_machine=saved.get("cnc_machine"),
            offset_left_cm=saved.get("offset_left_cm"),
            offset_bottom_cm=saved.get("offset_bottom_cm"),
            machine_catalog=list_cnc_machines(),
            plan_snapshot=approved_plan_snapshot(order),
            toolpath_snapshots=snapshots,
            vector_associations=kept,
        )
        restamped["machining_profiles_json"] = list(saved.get("machining_profiles") or [])
        restamped["vector_associations_json"] = kept
        restamped["toolpath_snapshots_json"] = snapshots
    except (
        OperationalFileError,
        ToolPresetError,
        PlacementError,
        MachiningSetupError,
        PostProcessorError,
    ) as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    try:
        save_sheet(
            str(saved.get("name") or ""),
            restamped,
            expected_revision=_revision(base_revision),
        )
    except OperationalFileError as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    return _workspace_for(order, can_prepare=True)


def _trusted_machining_profiles(saved: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Sheet copies win over the catalog. Both are trusted snapshots, not the live tool."""

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = (
        list((saved or {}).get("machining_profiles") or []),
        list(machining_profile_catalog() or []),
    )
    for source in sources:
        for row in source:
            if not isinstance(row, dict):
                continue
            profile_id = str(row.get("profile_id") or "")
            if not profile_id or profile_id in seen:
                continue
            seen.add(profile_id)
            rows.append(row)
    return rows


def _plain_diameter(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _issue_context(code: str, detail: dict[str, Any] | None) -> dict[str, str]:
    if code not in _DIAMETER_ISSUE_CODES or not isinstance(detail, dict):
        return {}
    problem, where, action = _diameter_dialog_parts(
        str(detail.get("operation_key") or ""),
        _plain_diameter(detail.get("approved_diameter_mm")),
        _plain_diameter(detail.get("selected_diameter_mm")),
    )
    return {"problem": problem, "target": where, "action": action}


def _describe_program(payload: dict[str, Any]) -> dict[str, Any]:
    for issue in payload.get("issues") or []:
        code = str(issue.get("code") or "")
        issue["message"] = _issue_message(code, str(issue.get("path_key") or ""), issue if issue.get("approved_diameter_mm") is not None else None)
        context = _issue_context(code, issue if issue.get("approved_diameter_mm") is not None else None)
        if context:
            issue["target_message"] = context["target"]
            issue["action_message"] = context["action"]
    for operation in payload.get("operations") or []:
        for path in operation.get("toolpaths") or []:
            path_key = str(path.get("path_key") or "")
            details = {
                str(item.get("code") or ""): item
                for item in path.get("issue_details") or []
                if isinstance(item, dict)
            }
            path["issue_messages"] = [
                _issue_message(str(code), path_key, details.get(str(code)))
                for code in path.get("issues") or []
            ]
            path["issue_context"] = {
                code: _issue_context(code, detail)
                for code, detail in details.items()
                if _issue_context(code, detail)
            }
    return payload


def _boundary_allowance_mm(order: Any) -> float:
    """Approved cutter radius. Paths may leave the sheet edge by this much."""

    snapshot = approved_plan_snapshot(order) or {}
    kerf = _kerf_mm(snapshot)
    if isinstance(kerf, bool) or not isinstance(kerf, (int, float)) or kerf <= 0:
        return 0.0
    return float(kerf) / 2.0


def _manufacturing_inputs(order: Any, sheet_no: int) -> tuple[str, dict[str, Any] | None]:
    source = manufacturing_source(order)
    status = source["saw_center_status"]
    if source["source_type"] != "Uploaded DXF" or status == "Absent":
        return "generated", None
    mode = {
        "Present": "uploaded_present",
        "Legacy": "uploaded_legacy",
    }.get(status, "uploaded_unknown")
    path = source["dxf_path"]
    if not path:
        return mode, {
            "unreadable": True,
            "origin": None,
            "units": "mm",
            "cut_segments": [],
            "overlays": [],
            "read_error": "dxf_unreadable",
        }
    try:
        return mode, read_operational_dxf(
            path,
            sheet_no=sheet_no,
            boundary_allowance_mm=_boundary_allowance_mm(order),
        )
    except DxfReadError:
        return mode, {
            "unreadable": True,
            "origin": None,
            "units": "mm",
            "cut_segments": [],
            "overlays": [],
            "read_error": "dxf_unreadable",
        }


def _effective_sheet_program(program: dict[str, Any], saved: dict[str, Any] | None) -> dict[str, Any]:
    """Preview, reverse validation, and NC all consume this program."""

    saved_row = saved or {}
    return effective_operational_program(
        program,
        snapshots=list(saved_row.get("toolpath_snapshots") or []),
        associations=list(saved_row.get("vector_associations") or []),
        reversed_path_keys=list(saved_row.get("reversed_path_keys") or []),
    )


def _reconciled_direction_records(
    order: Any,
    *,
    sheet_no: int,
    prepared: Mapping[str, Any],
    saved: Mapping[str, Any] | None,
    viewed_plan_token: str | None,
    snapshots: Sequence[Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Resolve saved directions against the exact settings being persisted."""

    operations = {
        str(row.get("operation_key") or ""): row.get("tool_preset")
        for row in prepared.get("operations") or ()
        if str(row.get("operation_key") or "")
    }
    paths = {
        str(row.get("path_key") or ""): row.get("tool_preset")
        for row in prepared.get("paths") or ()
        if str(row.get("path_key") or "") and str(row.get("tool_preset") or "").strip()
    }
    operation_order = [
        str(row.get("operation_key") or "")
        for row in prepared.get("operations") or ()
        if str(row.get("operation_key") or "")
    ]
    _plan, program, _presets = _compile_authorized_program(
        order,
        sheet_no=sheet_no,
        operation_presets=operations,
        path_overrides=paths,
        operation_order=operation_order,
        cut_path_early_confirmed=bool(prepared.get("cut_path_early_confirmed")),
        viewed_plan_token=viewed_plan_token,
        perimeter_join_mode=str(prepared.get("perimeter_join_mode") or "separate"),
        cut_path_sequence=list(prepared.get("cut_path_sequence") or ()),
        perimeter_cut_early_confirmed=bool(prepared.get("perimeter_cut_early_confirmed")),
    )
    direction_program = unreversed_operational_program(
        program,
        snapshots=snapshots,
        associations=associations,
    )
    return clear_reversed_direction_conflicts(
        direction_program,
        (saved or {}).get("reversed_path_keys"),
    )


@frappe.whitelist()
def get_cnc_sheet_program(
    order_name: str,
    sheet_no: int | str,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    viewed_plan_token: str | None = None,
    perimeter_join_mode: str | None = None,
    cut_path_sequence: str | list[Any] | None = None,
    perimeter_cut_early_confirmed: int | str | bool = 0,
    machining_profiles: str | list[Any] | None = None,
    vector_associations: str | list[Any] | None = None,
) -> dict[str, Any]:
    """Return a computed motion program. This does not save or write NC text."""

    order = _authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    if plan is None:
        frappe.throw(_message("no_approved_plan"), frappe.ValidationError)
    parsed_operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
    parsed_paths = frappe.parse_json(path_overrides) if isinstance(path_overrides, str) else dict(path_overrides or {})
    parsed_order = frappe.parse_json(operation_order) if isinstance(operation_order, str) else list(operation_order or [])
    parsed_sequence = _parse_optional_sequence(cut_path_sequence)
    incoming_profiles = None if machining_profiles is None else _json_list(machining_profiles)
    incoming_associations = None if vector_associations is None else _json_list(vector_associations)
    if not isinstance(parsed_operations, dict) or not isinstance(parsed_paths, dict) or not isinstance(parsed_order, list):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        mode, uploaded = _manufacturing_inputs(order, cint(sheet_no))
        compile_args = {
            "sheet_no": cint(sheet_no),
            "pieces": placed_piece_views(order),
            "snapshot": approved_plan_snapshot(order),
            "operation_presets": {str(key): value for key, value in parsed_operations.items()},
            "path_overrides": {str(key): value for key, value in parsed_paths.items()},
            "operation_order": [str(item) for item in parsed_order],
            "known_presets": known_tool_presets(),
            "cut_path_early_confirmed": bool(cint(cut_path_early_confirmed)),
            "manufacturing_mode": mode,
            "uploaded": uploaded,
            "perimeter_join_mode": str(perimeter_join_mode or "separate"),
            "cut_path_sequence": parsed_sequence,
            "perimeter_cut_early_confirmed": bool(cint(perimeter_cut_early_confirmed)),
        }
        saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
        effective_associations = None
        if incoming_associations is not None:
            base_known = known_tool_presets()
            source_payload = compile_sheet_program(**compile_args)
            source_catalog = catalog_rows_from_program(source_payload)
            profiles, effective_associations = accept_sheet_machining(
                paths=source_catalog,
                stored_profiles=_trusted_machining_profiles(saved),
                profiles=sheet_profiles_with_catalog(
                    incoming_profiles
                    if incoming_profiles is not None
                    else list((saved or {}).get("machining_profiles") or []),
                    incoming_associations,
                    machining_profile_catalog(),
                ),
                associations=incoming_associations,
                known_tools=base_known,
                snapshots=list((saved or {}).get("toolpath_snapshots") or []),
            )
            known = dict(base_known)
            overrides: dict[str, str] = {}
            for association in effective_associations:
                injected, association_overrides = calculation_preset_injection(
                    association,
                    base_known,
                    catalog=source_catalog,
                )
                known.update(injected)
                overrides.update(association_overrides)
            final_compile_args = dict(compile_args)
            final_compile_args["known_presets"] = known
            final_compile_args["path_overrides"] = {
                **compile_args["path_overrides"],
                **overrides,
            }
            payload = compile_sheet_program(**final_compile_args)
        else:
            payload = compile_sheet_program(**compile_args)
    except (OperationalFileError, ToolPresetError, PlacementError, MachiningSetupError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc
    if effective_associations is not None:
        saved = dict(saved or {})
        saved["vector_associations"] = effective_associations
    payload = _effective_sheet_program(payload, saved)
    return _describe_program(payload)


@frappe.whitelist()
def set_cnc_path_direction(
    order_name: str,
    sheet_no: int | str,
    path_key: str,
    shape_id: str | None = None,
    clear_saved: int | str | bool = 0,
    viewed_plan_token: str | None = None,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    perimeter_join_mode: str | None = None,
    cut_path_sequence: str | list[Any] | None = None,
    perimeter_cut_early_confirmed: int | str | bool = 0,
    cnc_machine: str | None = None,
    offset_left_cm: float | int | str | None = None,
    offset_bottom_cm: float | int | str | None = None,
    post_processor: str | None = None,
    base_revision: int | str | None = None,
) -> dict[str, Any]:
    """Toggle one path direction and persist the exact geometry settings used."""

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    if not saved or not saved.get("name"):
        frappe.throw(_message("sheet_settings_required"), frappe.ValidationError)
    _reject_stale_sheet(saved, base_revision)
    key = str(path_key or "").strip()
    if not key:
        frappe.throw(_message("path_reverse_unsupported"), frappe.ValidationError)
    (
        operations,
        paths,
        order_keys,
        confirmed,
        sources,
        join_mode,
        sequence,
        perimeter_early,
    ) = _settings_from_saved(saved, factory_operation_defaults())
    probe_operations = operations
    probe_paths = paths
    probe_order = order_keys
    probe_confirmed = confirmed
    probe_sources = dict(sources)
    probe_join = join_mode
    probe_sequence = sequence
    probe_early = perimeter_early
    if operation_presets is not None:
        parsed_operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
        if isinstance(parsed_operations, dict):
            probe_operations = {str(item): value for item, value in parsed_operations.items()}
            for item, value in probe_operations.items():
                if str(value or "").strip() != str(operations.get(item) or "").strip():
                    probe_sources[item] = "sheet"
    if path_overrides is not None:
        parsed_paths = frappe.parse_json(path_overrides) if isinstance(path_overrides, str) else dict(path_overrides or {})
        if isinstance(parsed_paths, dict):
            probe_paths = {str(item): value for item, value in parsed_paths.items()}
    if operation_order is not None:
        parsed_order = frappe.parse_json(operation_order) if isinstance(operation_order, str) else list(operation_order or [])
        if isinstance(parsed_order, list):
            probe_order = [str(item) for item in parsed_order]
    if perimeter_join_mode is not None:
        probe_join = str(perimeter_join_mode or join_mode)
        probe_sequence = _parse_optional_sequence(cut_path_sequence)
        probe_early = bool(cint(perimeter_cut_early_confirmed))
        probe_confirmed = bool(cint(cut_path_early_confirmed))
    try:
        _plan, program, _presets = _compile_authorized_program(
            order,
            sheet_no=cint(sheet_no),
            operation_presets=probe_operations,
            path_overrides=probe_paths,
            operation_order=probe_order,
            cut_path_early_confirmed=probe_confirmed,
            viewed_plan_token=viewed_plan_token,
            perimeter_join_mode=probe_join,
            cut_path_sequence=probe_sequence,
            perimeter_cut_early_confirmed=probe_early,
        )
    except OperationalFileError as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    try:
        direction_program = unreversed_operational_program(
            program,
            snapshots=list(saved.get("toolpath_snapshots") or []),
            associations=list(saved.get("vector_associations") or []),
        )
        current_records = clear_reversed_direction_conflicts(
            direction_program,
            saved.get("reversed_path_keys"),
        )
        records = toggle_reversed_path(
            current_records,
            direction_program,
            key,
            str(shape_id or ""),
            clear=bool(cint(clear_saved)),
        )
    except MachiningSetupError as exc:
        detail = exc.detail or key
        frappe.throw(_issue_message(exc.code, detail), frappe.ValidationError)
    try:
        prepared = prepare_sheet_settings(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=True,
            pieces=placed_piece_views(order),
            sheet_no=cint(sheet_no),
            existing=saved,
            operation_presets=probe_operations,
            path_overrides=probe_paths,
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            operation_order=probe_order,
            cut_path_early_confirmed=probe_confirmed,
            operation_sources={
                item: source
                for item, source in probe_sources.items()
                if item in probe_operations
            },
            factory_defaults=factory_operation_defaults(),
            perimeter_join_mode=probe_join,
            cut_path_sequence=probe_sequence,
            perimeter_cut_early_confirmed=probe_early,
            cnc_machine=saved.get("cnc_machine") if cnc_machine is None else cnc_machine,
            offset_left_cm=saved.get("offset_left_cm") if offset_left_cm is None else offset_left_cm,
            offset_bottom_cm=saved.get("offset_bottom_cm") if offset_bottom_cm is None else offset_bottom_cm,
            post_processor=post_processor,
            machine_catalog=list_cnc_machines(),
            plan_snapshot=approved_plan_snapshot(order),
            toolpath_snapshots=list(saved.get("toolpath_snapshots") or []),
            vector_associations=list(saved.get("vector_associations") or []),
            reversed_path_keys=records,
        )
        save_sheet(
            str(saved.get("name") or ""),
            prepared,
            expected_revision=_revision(base_revision),
        )
    except (
        OperationalFileError,
        ToolPresetError,
        PlacementError,
        MachiningSetupError,
        PostProcessorError,
    ) as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    workspace = _workspace_for(order, can_prepare=True)
    workspace["reversed_path_key"] = key
    return workspace


def _compile_authorized_program(
    order: Any,
    *,
    sheet_no: int,
    operation_presets: dict[str, Any],
    path_overrides: dict[str, Any],
    operation_order: list[Any],
    cut_path_early_confirmed: bool,
    viewed_plan_token: str | None,
    perimeter_join_mode: str = "separate",
    cut_path_sequence: Sequence[str] | None = None,
    perimeter_cut_early_confirmed: bool = False,
    known_presets: Mapping[str, Mapping[str, Any]] | None = None,
    extra_path_overrides: Mapping[str, str] | None = None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    plan = approved_plan_ref(order)
    if plan is None:
        raise OperationalFileError("no_approved_plan")
    assert_viewed_plan_token(plan, viewed_plan_token)
    mode, uploaded = _manufacturing_inputs(order, int(sheet_no))
    presets = dict(known_presets or known_tool_presets())
    merged_paths = {str(key): value for key, value in path_overrides.items()}
    merged_paths.update({str(key): value for key, value in dict(extra_path_overrides or {}).items()})
    payload = compile_sheet_program(
        sheet_no=int(sheet_no),
        pieces=placed_piece_views(order),
        snapshot=approved_plan_snapshot(order),
        operation_presets={str(key): value for key, value in operation_presets.items()},
        path_overrides=merged_paths,
        operation_order=[str(item) for item in operation_order],
        known_presets=presets,
        cut_path_early_confirmed=bool(cut_path_early_confirmed),
        manufacturing_mode=mode,
        uploaded=uploaded,
        perimeter_join_mode=str(perimeter_join_mode or "separate"),
        cut_path_sequence=cut_path_sequence,
        perimeter_cut_early_confirmed=bool(perimeter_cut_early_confirmed),
    )
    return plan, payload, presets


def _parse_sheet_settings(
    operation_presets: str | dict[str, Any] | None,
    path_overrides: str | dict[str, Any] | None,
    operation_order: str | list[Any] | None,
    operation_sources: str | dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[Any], dict[str, Any] | None]:
    parsed_operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
    parsed_paths = frappe.parse_json(path_overrides) if isinstance(path_overrides, str) else dict(path_overrides or {})
    parsed_order = frappe.parse_json(operation_order) if isinstance(operation_order, str) else list(operation_order or [])
    if operation_sources is None:
        parsed_sources = None
    else:
        parsed_sources = frappe.parse_json(operation_sources) if isinstance(operation_sources, str) else dict(operation_sources)
    if not isinstance(parsed_operations, dict) or not isinstance(parsed_paths, dict) or not isinstance(parsed_order, list) or (
        parsed_sources is not None and not isinstance(parsed_sources, dict)
    ):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    return parsed_operations, parsed_paths, parsed_order, parsed_sources


def _settings_from_saved(
    saved: Mapping[str, Any] | None,
    factory_defaults: Mapping[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, str], list[str], bool, dict[str, str], str, list[str], bool]:
    defaults = dict(factory_defaults or {})
    rows = list((saved or {}).get("operations") or [])
    operations: dict[str, str] = {}
    sources: dict[str, str] = {}
    order: list[str] = []
    for row in sorted(rows, key=lambda item: int(item.get("sequence") or 0)):
        key = str(row.get("operation_key") or "").strip()
        if not key:
            continue
        chosen, source = operation_preset_choice(
            row.get("tool_preset"),
            row.get("preset_source"),
            defaults.get(key, ""),
        )
        operations[key] = chosen
        sources[key] = source
        order.append(key)
    paths = {
        str(row.get("path_key") or ""): str(row.get("tool_preset") or "").strip()
        for row in (saved or {}).get("paths") or []
        if str(row.get("tool_preset") or "").strip()
    }
    sequence = [str(item) for item in list((saved or {}).get("cut_path_sequence") or []) if str(item or "").strip()]
    return (
        operations,
        paths,
        order,
        bool((saved or {}).get("cut_path_early_confirmed")),
        sources,
        str((saved or {}).get("perimeter_join_mode") or "separate"),
        sequence,
        bool((saved or {}).get("perimeter_cut_early_confirmed")),
    )


@frappe.whitelist()
def generate_cnc_sheet_nc(
    order_name: str,
    sheet_no: int | str,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    viewed_plan_token: str | None = None,
    operation_sources: str | dict[str, Any] | None = None,
    perimeter_join_mode: str | None = None,
    cut_path_sequence: str | list[Any] | None = None,
    perimeter_cut_early_confirmed: int | str | bool | None = None,
    cnc_machine: str | None = None,
    offset_left_cm: float | int | str | None = None,
    offset_bottom_cm: float | int | str | None = None,
    post_processor: str | None = None,
) -> dict[str, Any]:
    """Build one verified NC file from the current sheet settings and return it.

    Sheet settings are not saved. Associations and toolpath snapshots already
    stored by their own operations are applied in memory. No NC file is stored.
    """

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    parsed_operations, parsed_paths, parsed_order, parsed_sources = _parse_sheet_settings(
        operation_presets,
        path_overrides,
        operation_order,
        operation_sources,
    )
    parsed_sequence = _parse_optional_sequence(cut_path_sequence)
    plan = approved_plan_ref(order)
    if plan is None:
        frappe.throw(_message("no_approved_plan"), frappe.ValidationError)
    existing = _existing_sheet(str(order.name), plan, cint(sheet_no))
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        sheet_arguments = {
            "order_name": str(order.name),
            "approved_plan": plan,
            "plan_is_current": True,
            "pieces": placed_piece_views(order),
            "sheet_no": cint(sheet_no),
            "existing": existing,
            "operation_presets": {str(key): value for key, value in parsed_operations.items()},
            "path_overrides": {str(key): value for key, value in parsed_paths.items()},
            "known_presets": known_tool_presets(),
            "machine_profile": machine_profile_view(),
            "operation_order": [str(item) for item in parsed_order],
            "cut_path_early_confirmed": bool(cint(cut_path_early_confirmed)),
            "operation_sources": None if parsed_sources is None else {
                str(key): value for key, value in parsed_sources.items()
            },
            "factory_defaults": factory_operation_defaults(),
            "perimeter_join_mode": perimeter_join_mode,
            "cut_path_sequence": parsed_sequence,
            "perimeter_cut_early_confirmed": (
                None
                if perimeter_cut_early_confirmed is None
                else bool(cint(perimeter_cut_early_confirmed))
            ),
            "cnc_machine": cnc_machine,
            "offset_left_cm": offset_left_cm,
            "offset_bottom_cm": offset_bottom_cm,
            "post_processor": post_processor,
            "machine_catalog": list_cnc_machines(),
            "plan_snapshot": approved_plan_snapshot(order),
            "require_cnc_machine": True,
        }
        prepared = prepare_sheet_settings(**sheet_arguments)
        direction_snapshots = list((existing or {}).get("toolpath_snapshots") or [])
        direction_associations = list((existing or {}).get("vector_associations") or [])
        direction_records = _reconciled_direction_records(
            order,
            sheet_no=cint(sheet_no),
            prepared=prepared,
            saved=existing,
            viewed_plan_token=viewed_plan_token,
            snapshots=direction_snapshots,
            associations=direction_associations,
        )
        prepared = prepare_sheet_settings(
            **sheet_arguments,
            toolpath_snapshots=direction_snapshots,
            vector_associations=direction_associations,
            reversed_path_keys=direction_records,
        )
    except (OperationalFileError, ToolPresetError, PlacementError, MachiningSetupError, PostProcessorError) as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    (
        operations,
        paths,
        order_keys,
        confirmed,
        _sources,
        join_mode,
        sequence,
        perimeter_early,
    ) = _settings_from_saved(
        prepared,
        factory_operation_defaults(),
    )
    try:
        plan, program, _presets = _compile_authorized_program(
            order,
            sheet_no=cint(sheet_no),
            operation_presets=operations,
            path_overrides=paths,
            operation_order=order_keys,
            cut_path_early_confirmed=confirmed,
            viewed_plan_token=viewed_plan_token,
            perimeter_join_mode=join_mode,
            cut_path_sequence=sequence,
            perimeter_cut_early_confirmed=perimeter_early,
        )
        program = _effective_sheet_program(
            program,
            {
                "toolpath_snapshots": direction_snapshots,
                "vector_associations": direction_associations,
                "reversed_path_keys": direction_records,
            },
        )
        blocked = reversed_direction_block(program)
        if blocked:
            frappe.throw(_message(blocked), frappe.ValidationError)
        fingerprint = str(prepared["settings_fingerprint"])
        diameter_message = _diameter_program_message(program)
        if diameter_message:
            frappe.throw(diameter_message, frappe.ValidationError)
        machine_row = get_cnc_machine(str(prepared.get("cnc_machine") or ""))
        sheet_w, sheet_l = approved_sheet_size_cm(
            approved_plan_snapshot(order),
            sheet_no=cint(sheet_no),
        )
        placement = resolve_sheet_placement(
            machine=machine_row,
            sheet_width_cm=sheet_w,
            sheet_length_cm=sheet_l,
            require_machine=True,
        )
        package = build_post_processed_nc(
            program,
            post_processor_id=str(prepared.get("post_processor") or ""),
            sheet_placement=placement,
            sheet_no=cint(sheet_no),
            settings_fingerprint=fingerprint,
        )
    except (OperationalFileError, ToolPresetError, PostProcessorError, PlacementError) as exc:
        frappe.throw(_failure_message(exc), frappe.ValidationError)
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc

    text = str(package.get("text") or "")
    try:
        download = nc_download_payload(
            filename=nc_export_filename(
                order_name=str(order.name),
                cutting_plan=str(plan.name),
                plan_revision=int(plan.revision),
                sheet_no=cint(sheet_no),
                content_sha256=nc_content_sha256(text),
            ),
            text=text,
            verification=package.get("verification"),
        )
    except ValueError as exc:
        frappe.throw(_message("nc_verification_failed"), frappe.ValidationError)
        raise AssertionError("unreachable") from exc
    if existing and existing.get("name"):
        record_nc_generation(
            str(existing["name"]),
            fingerprint=fingerprint,
            content_sha256=nc_content_sha256(text),
        )
        download_nc_current = True
    else:
        download_nc_current = False
    download["message"] = _("NC file generated successfully.")
    download["nc_file_current"] = download_nc_current
    download["production"] = False
    download["content_sha256"] = nc_content_sha256(text)
    download["tool_number"] = package.get("tool_number")
    download["path_count"] = package.get("path_count")
    download["pass_count"] = package.get("pass_count")
    download["post_processor_version"] = package.get("post_processor_version")
    download["sheet_no"] = cint(sheet_no)
    return download


@frappe.whitelist()
def download_cnc_sheet_nc(
    order_name: str,
    operational_file_name: str,
    file_url: str | None = None,
) -> None:
    """Reject a stored NC download after generation permission and order scope checks."""

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    name = str(operational_file_name or "").strip()
    if name:
        owner = frappe.db.get_value("CNC Operational File", name, "door_cutting_order")
        if not owner:
            frappe.throw(_("Operational file was not found."), frappe.ValidationError)
        if str(owner) != str(order.name):
            frappe.throw(
                _("You do not have permission to download this NC file."),
                frappe.PermissionError,
            )
    if file_url is not None and str(file_url).strip() and not name:
        frappe.throw(_("Operational file was not found."), frappe.ValidationError)
    frappe.throw(_message("stored_nc_unavailable"), frappe.ValidationError)


def _existing_sheet(order_name: str, plan: Any, sheet_no: int) -> dict[str, Any] | None:
    if plan is None:
        return None
    for row in saved_operational_files(order_name):
        if (
            row["cutting_plan"] == plan.name
            and int(row["plan_revision"]) == int(plan.revision)
            and int(row["sheet_no"]) == int(sheet_no)
        ):
            return row
    return None


__all__ = [
    "download_cnc_sheet_nc",
    "generate_cnc_sheet_nc",
    "get_cnc_operational_workspace",
    "calculate_cnc_association_toolpath",
    "delete_cnc_association",
    "get_cnc_sheet_program",
    "set_cnc_path_direction",
    "save_cnc_operational_sheet",
]
