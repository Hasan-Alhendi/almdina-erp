"""Thin RPC boundary for CNC operational files.

Authorization and the current approved plan are resolved here. Machining
rules stay in the domain. NC text is generated only through the simulation
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
)
from almdina_erp.almdina_erp.application.cnc.nc_export import build_simulation_nc
from almdina_erp.almdina_erp.application.cnc.program import _kerf_mm, compile_sheet_program
from almdina_erp.almdina_erp.application.cnc.simulation_nc import (
    build_generation_snapshot,
    nc_content_sha256,
    simulation_nc_filename,
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
    apply_reversed_directions,
    effective_operational_program,
    normalize_reversed_paths,
    path_geometry_id,
    reversed_direction_block,
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
    attach_simulation_nc,
    discard_orphan_file,
    factory_operation_defaults,
    get_cnc_machine,
    known_tool_presets,
    list_cnc_machines,
    machining_profile_catalog,
    machine_profile_view,
    manufacturing_source,
    placed_piece_views,
    read_simulation_nc_bytes,
    record_nc_generation,
    save_sheet,
    saved_operational_files,
    sync_status,
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
    "tool_diameter_conflict": "The same tool cannot use two diameters in one operational file.",
    "tool_type_invalid": "Choose a tool type.",
    "tool_type_unsupported": "Only a Ball Nose tool can be created here.",
    "tool_units_invalid": "Tool units must be mm.",
    "rate_units_invalid": "Rate units must be mm/sec.",
    "description_required": "Enter the tool description.",
    "notes_invalid": "The tool notes are too long.",
    "stepdown_invalid": "Stepdown must be a positive number of millimetres within the supported range.",
    "final_tool_offset_invalid": "Final tool offset must be zero or a positive number of millimetres within the supported range.",
    "stepover_invalid": "Enter the stepover size and its percent of diameter.",
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
    "layer_not_machinable": "That layer has no machinable vectors on this sheet.",
    "selected_vectors_pending": "Selected Vectors needs a direct selection on the board before this association can be calculated.",
    "sheet_perimeter_unavailable": "Sheet Perimeter is available only while Connected Perimeter is enabled.",
    "toolpath_name_required": "Enter a toolpath name.",
    "toolpath_name_duplicate": "A calculated toolpath already uses that name.",
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
    "tool_diameter_kerf_mismatch": "This CUT_PATH was calculated for the approved kerf and does not match the selected tool diameter.",
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
    "file_persist_failed": "The simulation NC file could not be stored.",
    "path_reverse_unsupported": "This path cannot be reversed safely, so the NC file was not created.",
    "path_reverse_stale": "A saved path direction belongs to an older geometry, so the NC file was not created.",
    "path_reverse_missing": "A saved path direction no longer matches a path on this sheet, so the NC file was not created.",
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
    "offset_left_invalid": "The distance from the left must be zero or a positive number of centimetres.",
    "offset_bottom_invalid": "The distance from the bottom must be zero or a positive number of centimetres.",
    "sheet_width_invalid": "The approved sheet width is not valid.",
    "sheet_length_invalid": "The approved sheet length is not valid.",
    "sheet_exceeds_machine_width": "The sheet plus the left offset exceeds the machine width.",
    "sheet_exceeds_machine_length": "The sheet plus the bottom offset exceeds the machine length.",
    "toolpath_exceeds_machine": "A cutter path would leave the machine travel area after placement.",
    "placement_incomplete": "Sheet placement on the CNC machine is incomplete.",
}


def _message(code: str) -> str:
    return _(_MESSAGES.get(code, _NO_APPROVED_PLAN))


def _issue_message(code: str, path_key: str = "") -> str:
    if code == "tool_diameter_kerf_mismatch":
        return _(
            "CUT_PATH {0} was calculated for the approved kerf and does not match the selected tool diameter."
        ).format(path_key or _("the shared cut"))
    if code in {"path_reverse_unsupported", "path_reverse_stale", "path_reverse_missing"} and path_key:
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
    except OperationalFileError as exc:
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
        if sheet["operational_file"]:
            sync_status(sheet["operational_file"], sheet["status"])
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
    for historical in workspace["historical_files"]:
        if historical["name"]:
            sync_status(historical["name"], historical["status"])
    return workspace


@frappe.whitelist()
def get_cnc_operational_workspace(order_name: str) -> dict[str, Any]:
    order = _authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)
    can_prepare = document_has_capability(
        order,
        Capability.PREPARE_CNC_OPERATIONAL_FILES,
    )
    return _workspace_for(order, can_prepare=can_prepare)


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
    machining_profiles: str | list[Any] | None = None,
    vector_associations: str | list[Any] | None = None,
) -> dict[str, Any]:
    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    existing = _existing_sheet(str(order.name), plan, cint(sheet_no))
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
            "machine_catalog": list_cnc_machines(),
            "plan_snapshot": approved_plan_snapshot(order),
            "require_cnc_machine": False,
        }
        prepared = prepare_sheet_settings(**sheet_arguments)
        if machining_profiles is not None or vector_associations is not None:
            snapshots = list((existing or {}).get("toolpath_snapshots") or [])
            profiles, associations = accept_sheet_machining(
                paths=list(prepared.get("paths") or []),
                profiles=_json_list(machining_profiles)
                if machining_profiles is not None
                else list((existing or {}).get("machining_profiles") or []),
                associations=_json_list(vector_associations)
                if vector_associations is not None
                else list((existing or {}).get("vector_associations") or []),
                known_tools=known_tool_presets(),
                snapshots=snapshots,
            )
            prepared = prepare_sheet_settings(
                **sheet_arguments,
                toolpath_snapshots=snapshots,
                vector_associations=associations,
            )
            prepared["machining_profiles_json"] = profiles
            prepared["vector_associations_json"] = associations
    except (OperationalFileError, ToolPresetError, PlacementError, MachiningSetupError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    existing_name = str((existing or {}).get("name") or "")
    save_sheet(existing_name, prepared)
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
) -> dict[str, Any]:
    """Calculate one named toolpath from the association copy and freeze it."""

    save_cnc_operational_sheet(
        order_name,
        sheet_no,
        operation_presets,
        path_overrides,
        operation_order,
        cut_path_early_confirmed,
        viewed_plan_token,
        operation_sources,
        perimeter_join_mode,
        cut_path_sequence,
        perimeter_cut_early_confirmed,
        cnc_machine,
        offset_left_cm,
        offset_bottom_cm,
        machining_profiles,
        vector_associations,
    )
    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    if not saved or not saved.get("name"):
        frappe.throw(_message("generation_incomplete"), frappe.ValidationError)
    associations = list(saved.get("vector_associations") or [])
    association = next(
        (
            row
            for row in associations
            if str(row.get("association_id") or "") == str(association_id or "").strip()
        ),
        None,
    )
    if association is None:
        frappe.throw(_message("association_not_found"), frappe.ValidationError)
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
    try:
        known, overrides = calculation_preset_injection(association, known_tool_presets())
        _plan, program, _presets = _compile_authorized_program(
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
            known_presets=known,
            extra_path_overrides=overrides,
        )
        snapshots = freeze_calculated_toolpath(
            association=association,
            toolpath_name=toolpath_name,
            program=program,
            snapshots=list(saved.get("toolpath_snapshots") or []),
        )
        stored_associations = remember_toolpath_on_association(associations, snapshots)
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
            vector_associations=stored_associations,
        )
    except (OperationalFileError, ToolPresetError, PlacementError, MachiningSetupError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    update_machining_json(
        str(saved.get("name") or ""),
        profiles=list(saved.get("machining_profiles") or []),
        associations=stored_associations,
        snapshots=snapshots,
        fingerprint=str(restamped.get("settings_fingerprint") or ""),
        status=str(restamped.get("status") or ""),
    )
    return _workspace_for(order, can_prepare=True)


def _describe_program(payload: dict[str, Any]) -> dict[str, Any]:
    for issue in payload.get("issues") or []:
        issue["message"] = _issue_message(str(issue.get("code") or ""), str(issue.get("path_key") or ""))
    for operation in payload.get("operations") or []:
        for path in operation.get("toolpaths") or []:
            path_key = str(path.get("path_key") or "")
            path["issue_messages"] = [
                _issue_message(str(code), path_key) for code in path.get("issues") or []
            ]
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
    if not isinstance(parsed_operations, dict) or not isinstance(parsed_paths, dict) or not isinstance(parsed_order, list):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        mode, uploaded = _manufacturing_inputs(order, cint(sheet_no))
        payload = compile_sheet_program(
            sheet_no=cint(sheet_no),
            pieces=placed_piece_views(order),
            snapshot=approved_plan_snapshot(order),
            operation_presets={str(key): value for key, value in parsed_operations.items()},
            path_overrides={str(key): value for key, value in parsed_paths.items()},
            operation_order=[str(item) for item in parsed_order],
            known_presets=known_tool_presets(),
            cut_path_early_confirmed=bool(cint(cut_path_early_confirmed)),
            manufacturing_mode=mode,
            uploaded=uploaded,
            perimeter_join_mode=str(perimeter_join_mode or "separate"),
            cut_path_sequence=parsed_sequence,
            perimeter_cut_early_confirmed=bool(cint(perimeter_cut_early_confirmed)),
        )
    except OperationalFileError as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    payload = _effective_sheet_program(payload, saved)
    return _describe_program(payload)


@frappe.whitelist()
def set_cnc_path_direction(
    order_name: str,
    sheet_no: int | str,
    path_key: str,
    viewed_plan_token: str | None = None,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    perimeter_join_mode: str | None = None,
    cut_path_sequence: str | list[Any] | None = None,
    perimeter_cut_early_confirmed: int | str | bool = 0,
) -> dict[str, Any]:
    """Toggle one path direction and keep it for the next NC generation."""

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    if not saved or not saved.get("name"):
        frappe.throw(_message("sheet_settings_required"), frappe.ValidationError)
    key = str(path_key or "").strip()
    if not key:
        frappe.throw(_message("path_reverse_unsupported"), frappe.ValidationError)
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
    probe_operations = operations
    probe_paths = paths
    probe_order = order_keys
    probe_confirmed = confirmed
    probe_join = join_mode
    probe_sequence = sequence
    probe_early = perimeter_early
    if operation_presets is not None:
        parsed_operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
        if isinstance(parsed_operations, dict):
            probe_operations = {str(item): value for item, value in parsed_operations.items()}
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
    records = normalize_reversed_paths(saved.get("reversed_path_keys"))
    if any(row["path_key"] == key for row in records):
        records = [row for row in records if row["path_key"] != key]
    else:
        current = _effective_sheet_program(program, saved)
        found = None
        for operation in current.get("operations") or []:
            for path in operation.get("toolpaths") or []:
                if str(path.get("path_key") or "") == key:
                    found = path
                    break
            if found is not None:
                break
        if not isinstance(found, dict):
            frappe.throw(_issue_message("path_reverse_missing", key), frappe.ValidationError)
        geometry_id = path_geometry_id(found)
        probe = apply_reversed_directions(
            {"operations": [{"toolpaths": [found]}], "issues": []},
            [{"path_key": key, "geometry_id": geometry_id}],
        )
        blocked = reversed_direction_block(probe)
        if blocked:
            frappe.throw(_issue_message(blocked, key), frappe.ValidationError)
        records.append({"path_key": key, "geometry_id": geometry_id})
    records = normalize_reversed_paths(records)
    try:
        prepared = prepare_sheet_settings(
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
            toolpath_snapshots=list(saved.get("toolpath_snapshots") or []),
            vector_associations=list(saved.get("vector_associations") or []),
            reversed_path_keys=records,
        )
        save_sheet(str(saved.get("name") or ""), prepared)
    except (OperationalFileError, ToolPresetError, PlacementError, MachiningSetupError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
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
) -> dict[str, Any]:
    """Save sheet settings, then persist a verified Simulation NC file. Not production-approved."""

    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    parsed_operations, parsed_paths, parsed_order, parsed_sources = _parse_sheet_settings(
        operation_presets,
        path_overrides,
        operation_order,
        operation_sources,
    )
    parsed_sequence = _parse_optional_sequence(cut_path_sequence)
    plan = approved_plan_ref(order)
    existing = _existing_sheet(str(order.name), plan, cint(sheet_no))
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        prepared = prepare_sheet_settings(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=plan is not None,
            pieces=placed_piece_views(order),
            sheet_no=cint(sheet_no),
            existing=existing,
            operation_presets={str(key): value for key, value in parsed_operations.items()},
            path_overrides={str(key): value for key, value in parsed_paths.items()},
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            operation_order=[str(item) for item in parsed_order],
            cut_path_early_confirmed=bool(cint(cut_path_early_confirmed)),
            operation_sources=None if parsed_sources is None else {
                str(key): value for key, value in parsed_sources.items()
            },
            factory_defaults=factory_operation_defaults(),
            perimeter_join_mode=perimeter_join_mode,
            cut_path_sequence=parsed_sequence,
            perimeter_cut_early_confirmed=(
                None
                if perimeter_cut_early_confirmed is None
                else bool(cint(perimeter_cut_early_confirmed))
            ),
            cnc_machine=cnc_machine,
            offset_left_cm=offset_left_cm,
            offset_bottom_cm=offset_bottom_cm,
            machine_catalog=list_cnc_machines(),
            plan_snapshot=approved_plan_snapshot(order),
            require_cnc_machine=True,
        )
    except (OperationalFileError, ToolPresetError, PlacementError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    operational_name = save_sheet(str((existing or {}).get("name") or ""), prepared)
    saved = _existing_sheet(str(order.name), plan, cint(sheet_no))
    if not saved or str(saved.get("name") or "") != operational_name:
        frappe.throw(_message("generation_incomplete"), frappe.ValidationError)
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
        saved,
        factory_operation_defaults(),
    )
    try:
        plan, program, presets = _compile_authorized_program(
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
        program = _effective_sheet_program(program, saved)
        blocked = reversed_direction_block(program)
        if blocked:
            frappe.throw(_message(blocked), frappe.ValidationError)
        machine = machine_profile_view()
        fingerprint = str(prepared["settings_fingerprint"])
        if str(saved.get("settings_fingerprint") or "") != fingerprint:
            frappe.throw(_message("generation_incomplete"), frappe.ValidationError)
        machine_row = get_cnc_machine(str(saved.get("cnc_machine") or ""))
        sheet_w, sheet_l = approved_sheet_size_cm(
            approved_plan_snapshot(order),
            sheet_no=cint(sheet_no),
        )
        placement = resolve_sheet_placement(
            machine=machine_row,
            sheet_width_cm=sheet_w,
            sheet_length_cm=sheet_l,
            offset_left_cm=saved.get("offset_left_cm"),
            offset_bottom_cm=saved.get("offset_bottom_cm"),
            require_machine=True,
        )
        package = build_simulation_nc(
            program,
            machine_profile={
                **(machine.get("fingerprint_payload") or {}),
                "production_approved": machine.get("production_approved"),
                "retract_z_mm": (machine.get("fingerprint_payload") or {}).get("retract_z_mm", 20),
            },
            sheet_no=cint(sheet_no),
            settings_fingerprint=fingerprint,
            sheet_placement=placement,
        )
    except (OperationalFileError, ToolPresetError, PostProcessorError, PlacementError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc

    text = str(package.get("text") or "")
    content_hash = nc_content_sha256(text)
    package["content_sha256"] = content_hash
    package["production"] = False
    filename = simulation_nc_filename(
        order_name=str(order.name),
        cutting_plan=str(plan.name),
        plan_revision=int(plan.revision),
        sheet_no=cint(sheet_no),
        content_sha256=content_hash,
    )
    previous_file = str(saved.get("generated_file") or "")
    file_url = ""
    try:
        file_url = attach_simulation_nc(
            operational_file_name=operational_name,
            filename=filename,
            content=text,
        )
        snapshot = build_generation_snapshot(
            order_name=str(order.name),
            cutting_plan=str(plan.name),
            plan_revision=int(plan.revision),
            plan_source_type=str(plan.source_type or ""),
            sheet_no=cint(sheet_no),
            settings_fingerprint=fingerprint,
            operation_presets=operations,
            path_overrides=paths,
            operation_order=order_keys,
            cut_path_early_confirmed=confirmed,
            known_presets=presets,
            machine_profile={
                **(machine.get("fingerprint_payload") or {}),
                "production_approved": bool(machine.get("production_approved")),
                "source_note": str(machine.get("source_note") or ""),
            },
            package=package,
            program=program,
            previous_generated_file=previous_file if previous_file != file_url else "",
            generated_by=str(frappe.session.user or ""),
            generated_on=str(frappe.utils.now_datetime()),
            perimeter_join_mode=join_mode,
            cut_path_sequence=sequence,
            perimeter_cut_early_confirmed=perimeter_early,
            sheet_placement=dict(package.get("sheet_placement") or {}),
        )
        record_nc_generation(operational_name, snapshot, file_url)
    except Exception as exc:
        if file_url:
            discard_orphan_file(file_url)
        if isinstance(exc, frappe.ValidationError):
            raise
        frappe.throw(_message("file_persist_failed"), frappe.ValidationError)

    workspace = _workspace_for(order, can_prepare=True)
    sheet = next(
        (
            item
            for item in workspace.get("sheets") or []
            if int(item.get("sheet_no") or 0) == int(cint(sheet_no))
        ),
        None,
    )
    package["message"] = _(
        "Simulation NC prepared. This file is not approved for a workshop machine."
    )
    package["filename"] = filename
    package["file_url"] = file_url
    package["operational_file"] = operational_name
    package["status"] = (sheet or {}).get("status") or "Generated"
    package["workspace"] = workspace
    package["download_method"] = "almdina_erp.almdina_erp.services.cnc_operational_file_service.download_cnc_sheet_nc"
    return package


@frappe.whitelist()
def download_cnc_sheet_nc(
    order_name: str,
    operational_file_name: str,
    file_url: str | None = None,
) -> None:
    """Stream a private Simulation NC attachment after VIEW + order scope checks."""

    order = _authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)
    name = str(operational_file_name or "").strip()
    if not name:
        frappe.throw(_("Operational file was not found."), frappe.ValidationError)
    try:
        filename, content = read_simulation_nc_bytes(
            operational_file_name=name,
            expected_order=str(order.name),
            file_url=file_url,
        )
    except frappe.PermissionError:
        frappe.throw(
            _("You do not have permission to download this simulation NC file."),
            frappe.PermissionError,
        )
    except frappe.ValidationError as exc:
        frappe.throw(str(exc) or _("The simulation NC file could not be downloaded."), frappe.ValidationError)
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"


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
    "get_cnc_sheet_program",
    "set_cnc_path_direction",
    "save_cnc_operational_sheet",
]
