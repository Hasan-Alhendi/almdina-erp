"""Approved plan diameters gate every CNC layer, and profile edits stay allow-listed."""

from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.application.cnc.machining_setup import calculation_preset_injection
from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    MachiningSetupError,
    calculate_toolpath_snapshot,
    catalog_rows_from_program,
    effective_operational_program,
    normalize_associations,
    normalize_profile,
    vectors_from_paths,
)
from almdina_erp.almdina_erp.domain.cnc.post_processor import PostProcessorError, emit_nc
from almdina_erp.almdina_erp.domain.cnc.program import apply_plan_diameter_gate
from almdina_erp.tests.test_artcam_machining import _profile, _stored_tool
from almdina_erp.tests.test_cnc_sheet_perimeter_operation import (
    PRESETS as PERIMETER_PRESETS,
)
from almdina_erp.tests.test_cnc_sheet_perimeter_operation import (
    _pieces_with_addons,
    _snapshot as _perimeter_snapshot,
)
from almdina_erp.tests.test_cnc_toolpath_coverage import (
    PRESETS,
    _compile,
    _mill_piece,
    _paths,
    _piece,
    _rect,
    _snapshot,
)


CASES = ((3, 3, True), (3, 5, False), (5, 3, False), (5, 5, True), (8, 6, False))


def _tool(name, diameter, **extra):
    tool = dict(PRESETS["Finish"])
    tool.update({"preset_name": name, "tool_name": name, "tool_diameter_mm": diameter})
    tool.update(extra)
    return tool


def _piece_for(operation):
    if operation == "cut_path":
        return _piece("piece-a", _rect(10, 20, 200, 300))
    if operation == "liner":
        return _mill_piece(
            extra_liner=1,
            liner_reference_side="edge_width_top",
            liner_offset_cm=2,
            liner_width_cm=1.8,
        )
    if operation == "recessed_handle_cutout":
        return _mill_piece(
            extra_recessed_handle_cutout=1,
            recessed_handle_reference_side="edge_width_bottom",
            recessed_handle_offset_cm=2,
            recessed_handle_width_cm=1.8,
            recessed_handle_start_cm=5,
            recessed_handle_length_cm=20,
        )
    return _mill_piece(
        extra_back_groove=1,
        back_groove_reference_side="edge_long_left",
        back_groove_offset_cm=2,
        back_groove_width_cm=1.8,
    )


def _layer_program(operation, approved, selected):
    snapshot = _snapshot(kerf_mm=approved)
    if operation == "liner":
        snapshot["liner_tool_diameter_mm"] = approved
    elif operation == "recessed_handle_cutout":
        snapshot["handle_recess_tool_diameter_mm"] = approved
    elif operation == "back_groove":
        snapshot["rear_groove_tool_diameter_mm"] = approved
    presets = {
        "Plan": _tool("Plan", approved),
        "Chosen": _tool("Chosen", selected),
    }
    return compile_sheet_program(
        sheet_no=1,
        pieces=[_piece_for(operation)],
        snapshot=snapshot,
        operation_presets={
            "cut_path": "Chosen" if operation == "cut_path" else "Plan",
            "liner": "Chosen" if operation == "liner" else "Plan",
            "recessed_handle_cutout": "Chosen" if operation == "recessed_handle_cutout" else "Plan",
            "back_groove": "Chosen" if operation == "back_groove" else "Plan",
        },
        path_overrides={},
        operation_order=["liner", "recessed_handle_cutout", "back_groove", "cut_path"],
        known_presets=presets,
    )


@pytest.mark.parametrize(("operation", "approved", "selected", "accepted"), [
    (operation, approved, selected, accepted)
    for operation in ("cut_path", "liner", "recessed_handle_cutout", "back_groove")
    for approved, selected, accepted in CASES
])
def test_every_layer_compares_diameter_with_the_approved_plan(operation, approved, selected, accepted):
    matched = _layer_program(operation, approved, approved)
    program = _layer_program(operation, approved, selected)
    path = _paths(program, operation)[0]
    approved_points = _paths(matched, operation)[0]["points"]
    assert path["points"] == approved_points
    assert path["preset"]["tool_diameter_mm"] == selected
    if accepted:
        assert path["ready"] is True
        assert path["motions"]
        assert "tool_diameter_plan_mismatch" not in path["issues"]
        assert "tool_diameter_kerf_mismatch" not in path["issues"]
        return
    assert path["ready"] is False
    assert path["motions"] == []
    code = "tool_diameter_kerf_mismatch" if operation == "cut_path" else "tool_diameter_plan_mismatch"
    assert code in path["issues"]
    detail = path["issue_details"][0]
    assert detail["approved_diameter_mm"] == approved
    assert detail["selected_diameter_mm"] == selected
    with pytest.raises(PostProcessorError) as blocked:
        emit_nc(program)
    assert blocked.value.code == "geometry_not_ready"


def test_sheet_perimeter_uses_the_approved_cut_diameter():
    presets = dict(PERIMETER_PRESETS)
    presets["Wide"] = _tool("Wide", 8)
    pieces = _pieces_with_addons()
    order = ["liner", "recessed_handle_cutout", "back_groove", "sheet_perimeter", "cut_path"]
    matched = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_perimeter_snapshot(),
        operation_presets={key: "Finish" for key in order},
        path_overrides={},
        operation_order=order,
        known_presets=presets,
        perimeter_join_mode="connected",
    )
    mismatched = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_perimeter_snapshot(),
        operation_presets={**{key: "Finish" for key in order}, "sheet_perimeter": "Wide"},
        path_overrides={},
        operation_order=order,
        known_presets=presets,
        perimeter_join_mode="connected",
    )
    matched_path = _paths(matched, "sheet_perimeter")[0]
    path = _paths(mismatched, "sheet_perimeter")[0]
    assert matched_path["ready"] is True
    assert path["ready"] is False
    assert path["points"] == matched_path["points"]
    assert "tool_diameter_kerf_mismatch" in path["issues"]
    assert path["issue_details"][0]["approved_diameter_mm"] == 5
    assert path["issue_details"][0]["selected_diameter_mm"] == 8


def test_an_old_plan_inherits_the_layer_diameter_from_kerf():
    piece = _piece_for("liner")
    inherited = _snapshot(kerf_mm=5)
    assert "liner_tool_diameter_mm" not in inherited
    accepted = _compile(
        [piece],
        snapshot=inherited,
        operation_presets={"cut_path": "Finish", "liner": "Finish"},
    )
    rejected = _compile(
        [piece],
        snapshot=inherited,
        operation_presets={"cut_path": "Finish", "liner": "Wide"},
    )
    assert _paths(accepted, "liner")[0]["ready"] is True
    liner = _paths(rejected, "liner")[0]
    assert liner["ready"] is False
    assert liner["points"] == _paths(accepted, "liner")[0]["points"]
    assert liner["issue_details"][0]["approved_diameter_mm"] == 5


def test_an_active_snapshot_cannot_skip_the_diameter_gate():
    program = _compile([_piece("piece-a", _rect(10, 20, 200, 300))])
    path = _paths(program, "cut_path")[0]
    points = [list(point) for point in path["points"]]
    snapshot = {
        "toolpath_id": "toolpath:old",
        "association_id": "association:old",
        "archived": False,
        "preset": {**path["preset"], "tool_diameter_mm": 8},
        "safe_z_mm": 20,
        "home": {"x_mm": 0, "y_mm": 0, "z_mm": 20},
        "paths": [{
            "path_key": path["path_key"],
            "vector_id": path.get("vector_id") or path["path_key"],
            "operation_key": "cut_path",
            "points": points,
            "motions": list(path["motions"]),
            "closed": path["closed"],
        }],
    }
    effective = effective_operational_program(
        program,
        snapshots=[snapshot],
        associations=[{
            "association_id": "association:old",
            "toolpath_id": "toolpath:old",
            "vector_ids": [path.get("vector_id") or path["path_key"]],
        }],
    )
    frozen = _paths(effective, "cut_path")[0]
    assert frozen["ready"] is False
    assert frozen["points"] == path["points"]
    assert frozen["motions"] == []
    assert "tool_diameter_kerf_mismatch" in frozen["issues"]
    with pytest.raises(PostProcessorError) as blocked:
        emit_nc(effective)
    assert blocked.value.code == "geometry_not_ready"


def test_profile_overrides_keep_protected_tool_properties():
    stored = _stored_tool()
    known = {"T9_CUT": stored}
    created = normalize_profile(_profile(), known_tools=known)
    edited = normalize_profile(
        {
            **created,
            "tool_values": {
                "tool_number": 4,
                "stepdown_mm": 6,
                "stepover_size_mm": 1,
                "feed_rate_mm_sec": 20,
                "plunge_rate_mm_sec": 8,
                "spindle_speed_rpm": 12000,
            },
        },
        known_tools=known,
        stored_profile=created,
    )
    assert edited["tool_values"]["tool_number"] == "T4"
    assert edited["tool_values"]["stepdown_mm"] == 6
    assert edited["tool_values"]["stepover_size_mm"] == 1
    assert edited["tool_values"]["stepover_percent"] == 20
    assert edited["tool_values"]["feed_rate_mm_sec"] == 20
    assert edited["tool_values"]["plunge_rate_mm_sec"] == 8
    assert edited["tool_values"]["spindle_speed_rpm"] == 12000
    assert edited["tool_values"]["diameter_mm"] == 5
    assert edited["tool_values"]["tool_type"] == created["tool_values"]["tool_type"]
    assert stored["tool_diameter_mm"] == 5
    assert stored["feed_rate_mm_sec"] == 170
    stored["tool_diameter_mm"] = 9
    stored["feed_rate_mm_sec"] = 1
    reopened = normalize_profile(edited, known_tools=known, stored_profile=edited)
    assert reopened["tool_values"]["diameter_mm"] == 5
    assert reopened["tool_values"]["feed_rate_mm_sec"] == 20
    replacement = _stored_tool()
    replacement.update({
        "description": "Other",
        "tool_name": "Other",
        "preset_name": "Other",
        "diameter_mm": 8,
        "tool_diameter_mm": 8,
        "tool_number": 3,
        "feed_rate_mm_sec": 11,
    })
    switched = normalize_profile(
        {**edited, "tool_preset": "Other", "tool_values": {"feed_rate_mm_sec": 15, "stepdown_mm": 2}},
        known_tools={"T9_CUT": stored, "Other": replacement},
        stored_profile=edited,
    )
    assert switched["tool_values"]["diameter_mm"] == 8
    assert switched["tool_values"]["tool_number"] == "T3"
    assert switched["tool_values"]["feed_rate_mm_sec"] == 15
    assert switched["tool_values"]["stepdown_mm"] == 2
    assert edited["tool_values"]["diameter_mm"] == 5


@pytest.mark.parametrize("field,value,label", [
    ("diameter_mm", 8, "Diameter"),
    ("tool_type", "End Mill", "Tool Type"),
    ("final_tool_offset_mm", 9, "Final Tool Offset"),
    ("description", "Changed", "Description"),
])
def test_direct_profile_and_association_payloads_cannot_change_protected_fields(field, value, label):
    known = {"T9_CUT": _stored_tool()}
    created = normalize_profile(_profile(), known_tools=known)
    with pytest.raises(MachiningSetupError) as profile_error:
        normalize_profile(
            {**created, "tool_values": {**created["tool_values"], field: value}},
            known_tools=known,
            stored_profile=created,
        )
    assert profile_error.value.code == "tool_property_locked"
    assert profile_error.value.detail == label
    catalog = vectors_from_paths([{
        "vector_id": "cut_path:piece-a:outer",
        "path_key": "cut_path:piece-a:outer",
        "operation_key": "cut_path",
        "dxf_layer": "CUT_PATH",
    }])
    with pytest.raises(MachiningSetupError) as association_error:
        normalize_associations(
            [{
                "association_id": "association:cut",
                "profile_id": created["profile_id"],
                "selection": {"kind": "vectors", "vector_ids": ["cut_path:piece-a:outer"]},
                "local_values": {"tool_values": {field: value, "feed_rate_mm_sec": 12}},
            }],
            profiles=[created],
            catalog=catalog,
        )
    assert association_error.value.code == "tool_property_locked"
    assert association_error.value.detail == label
    assert created["tool_values"]["diameter_mm"] == 5


def test_association_overrides_reach_nc_without_moving_the_approved_path():
    piece = _piece("piece-a", _rect(10, 20, 200, 300))
    source = _compile([piece])
    approved_points = _paths(source, "cut_path")[0]["points"]
    tool = _stored_tool()
    tool["preset_name"] = "Finish"
    tool["description"] = "Finish"
    tool["tool_name"] = "Finish"
    tool["stepdown_mm"] = 4
    known = {"Finish": tool}
    profile = normalize_profile(
        {
            "name": "Cut",
            "tool_preset": "Finish",
            "final_depth_mm": 10,
            "safe_z_mm": 12,
            "home_x_mm": 4,
            "home_y_mm": 6,
            "home_z_mm": 18,
        },
        known_tools=known,
        profile_id="profile:cut",
    )
    catalog = catalog_rows_from_program(source)
    association = normalize_associations(
        [{
            "association_id": "association:cut",
            "name": "Cut",
            "profile_id": profile["profile_id"],
            "selection": {"kind": "vectors", "vector_ids": [catalog[0]["vector_id"]]},
            "local_values": {
                "final_depth_mm": 10,
                "safe_z_mm": 12,
                "home_x_mm": 4,
                "home_y_mm": 6,
                "home_z_mm": 18,
                "tool_values": {
                    "tool_number": 4,
                    "stepdown_mm": 4,
                    "feed_rate_mm_sec": 20,
                    "plunge_rate_mm_sec": 8,
                    "spindle_speed_rpm": 12000,
                },
            },
        }],
        profiles=[profile],
        catalog=vectors_from_paths(catalog),
    )[0]
    injected, overrides = calculation_preset_injection(association, known, catalog=catalog)
    calculated = compile_sheet_program(
        sheet_no=1,
        pieces=[piece],
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides=overrides,
        operation_order=["cut_path"],
        known_presets=injected,
    )
    path = _paths(calculated, "cut_path")[0]
    assert path["points"] == approved_points
    assert path["ready"] is True
    snapshot = calculate_toolpath_snapshot(
        association=association,
        toolpath_name="Cut",
        program=calculated,
    )
    assert snapshot["preset"]["tool_number"] == "T4"
    assert snapshot["preset"]["feed_rate_mm_min"] == 1200
    assert snapshot["preset"]["plunge_rate_mm_min"] == 480
    assert snapshot["preset"]["spindle_speed_rpm"] == 12000
    assert snapshot["preset"]["tool_diameter_mm"] == 5
    linked = {**association, "toolpath_id": snapshot["toolpath_id"]}
    effective = effective_operational_program(
        calculated,
        snapshots=[snapshot],
        associations=[linked],
    )
    frozen = _paths(effective, "cut_path")[0]
    assert frozen["points"] == approved_points
    depths = sorted({
        float(motion["depth_mm"])
        for motion in frozen["motions"]
        if motion["kind"] == "plunge"
    })
    assert depths == [4.0, 8.0, 10.0]
    document = emit_nc(effective)
    assert document.tool_number == "T4"
    text = document.text
    assert "S12000 M3" in text
    assert "F1200" in text
    assert "F480" in text
    assert "G0 Z12" in text
    assert "G0 X4 Y6" in text
    assert "G0 Z18" in text
    mismatched = _compile([piece], operation_presets={"cut_path": "Wide"})
    with pytest.raises(MachiningSetupError) as rejected:
        calculate_toolpath_snapshot(
            association=association,
            toolpath_name="Cut",
            program=mismatched,
        )
    assert rejected.value.code == "tool_diameter_kerf_mismatch"
    assert rejected.value.detail == "cut_path|5|8"
    with pytest.raises(PostProcessorError):
        emit_nc(mismatched)


def test_saved_snapshot_gate_leaves_matching_geometry_executable():
    program = _compile([_piece("piece-a", _rect(10, 20, 200, 300))])
    gated = apply_plan_diameter_gate(program)
    assert _paths(gated, "cut_path")[0]["ready"] is True
    assert _paths(gated, "cut_path")[0]["points"] == _paths(program, "cut_path")[0]["points"]
