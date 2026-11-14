"""Simulation NC generation and independent verification."""

from __future__ import annotations

from almdina_erp.almdina_erp.application.cnc.nc_export import build_simulation_nc
from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cnc.nc_interpreter import interpret_nc, verify_nc_against_program
from almdina_erp.almdina_erp.domain.cnc.post_processor import POST_PROCESSOR_VERSION, PostProcessorError, emit_nc


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": 9,
        "tool_diameter_mm": 5,
        "final_depth_mm": 18,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 10200,
        "plunge_rate_mm_min": 1800,
        "pass_depth_mm": 6,
        "enabled": True,
    }
    values.update(overrides)
    return values


PRESETS = {
    "Finish": _raw(),
    "Shallow": _raw(preset_name="Shallow", final_depth_mm=7, pass_depth_mm=None, feed_rate_mm_min=8000),
    "OversizedStepdown": _raw(
        preset_name="OversizedStepdown",
        final_depth_mm=7,
        pass_depth_mm=20,
        feed_rate_mm_min=8000,
    ),
}


def _piece(instance_id="piece-a", **extra):
    piece = {
        "piece_instance_id": instance_id,
        "label": "1.1",
        "sheet_no": 1,
        "piece_type": "Regular",
        "original_width_cm": 20,
        "original_length_cm": 30,
        "x_mm": 10,
        "y_mm": 20,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": {
            "unit": "mm",
            "coordinate_space": "usable_sheet",
            "outer": [[10, 20], [210, 20], [210, 320], [10, 320]],
            "holes": [],
        },
    }
    piece.update(extra)
    return piece


def _snapshot():
    return {
        "kerf_mm": 5,
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "sheets": [{"sheet_no": 1, "full_width_cm": 122, "full_length_cm": 244, "applied_trim_width_cm": 0, "applied_trim_length_cm": 0}],
    }


def _program(**kwargs):
    return compile_sheet_program(
        sheet_no=1,
        pieces=kwargs.pop("pieces", [_piece()]),
        snapshot=_snapshot(),
        operation_presets=kwargs.pop("operation_presets", {"cut_path": "Finish", "liner": "Finish"}),
        path_overrides=kwargs.pop("path_overrides", {}),
        operation_order=kwargs.pop("operation_order", ["liner", "cut_path"]),
        known_presets=PRESETS,
        cut_path_early_confirmed=True,
        manufacturing_mode="generated",
        uploaded=None,
    )


def test_simulation_nc_matches_intermediate_program_with_depth_passes():
    program = _program()
    assert program["geometry_ready"] is True
    assert program["machine_ready"] is False
    assert program["nc_export_ready"] is True
    package = build_simulation_nc(
        program,
        machine_profile={"retract_z_mm": 20, "production_approved": False, "distance_mode": "G90", "work_offset": "G54"},
        sheet_no=1,
        settings_fingerprint="abc",
    )
    text = package["text"]
    assert package["production"] is False
    assert package["post_processor_version"] == POST_PROCESSOR_VERSION
    assert "G21" in text and "G90" in text and "G54" in text
    assert "G40" in text and "M3" in text and "M5" in text and "M30" in text
    assert "S15000 M3" in text
    assert "G0 Z20" in text
    assert "not approved" in text.lower() or "simulation" in text.lower()
    assert package["verification"]["ok"] is True
    assert package["pass_count"] >= 3
    assert package["spindle_speed_rpm"] == 15000
    assert package["tool_number"] == "T9"
    depths = sorted({
        abs(float(motion.z_mm))
        for motion in interpret_nc(text).motions
        if motion.kind == "plunge" and motion.z_mm is not None
    })
    assert depths == [6.0, 12.0, 18.0]
    assert verify_nc_against_program(text, program, safe_z_mm=20).ok is True


def test_stepdown_larger_than_final_depth_stops_at_final_depth():
    program = _program(
        operation_presets={"cut_path": "OversizedStepdown"},
        operation_order=["cut_path"],
    )
    path = program["operations"][0]["toolpaths"][0]
    assert path["preset"]["final_depth_mm"] == 7
    assert path["preset"]["pass_depth_mm"] == 7
    assert [motion["depth_mm"] for motion in path["motions"] if motion["kind"] == "plunge"] == [7]


def test_liner_and_shared_cut_are_posted_once():
    pieces = [
        _piece(
            "piece-a",
            original_width_cm=20,
            original_length_cm=50,
            x_mm=0,
            y_mm=0,
            geometry={"unit": "mm", "coordinate_space": "usable_sheet", "outer": [[0, 0], [200, 0], [200, 500], [0, 500]], "holes": []},
            extra_liner=1,
            liner_reference_side="edge_width_top",
            liner_offset_cm=2,
            liner_width_cm=1.8,
        ),
        _piece(
            "piece-b",
            label="1.2",
            original_width_cm=20,
            original_length_cm=50,
            x_mm=205,
            y_mm=0,
            geometry={"unit": "mm", "coordinate_space": "usable_sheet", "outer": [[205, 0], [405, 0], [405, 500], [205, 500]], "holes": []},
        ),
    ]
    program = _program(pieces=pieces, operation_order=["liner", "cut_path"], cut_path_early_confirmed=True)
    assert program["geometry_ready"] is True
    package = build_simulation_nc(program, machine_profile={"retract_z_mm": 20, "production_approved": 0})
    assert package["verification"]["ok"] is True
    assert package["text"].count("(Path liner:") == 1
    shared = [
        path
        for row in program["operations"]
        if row["operation_key"] == "cut_path"
        for path in row["toolpaths"]
        if path["points"] and all(abs(point[0] - 202.5) < 0.2 for point in path["points"])
    ]
    assert len(shared) == 1
    assert shared[0]["piece_instance_id"] == ""
    assert package["text"].count(f"(Path {shared[0]['path_key']})") == 1


def test_mill_outlines_stay_visible_when_the_cutter_diameter_is_missing():
    piece = _piece(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=2,
        liner_width_cm=1.8,
        extra_back_groove=1,
        extra_recessed_handle_cutout=1,
        overlays=[
            {"kind": "liner", "geometry": {"path": [[20, 40], [180, 40]], "closed": False, "entity_type": "LINE"}},
            {"kind": "liner", "geometry": {"path": [[20, 55], [180, 55]], "closed": False, "entity_type": "LINE"}},
            {"kind": "back_groove", "geometry": {"path": [[20, 80], [180, 80]], "closed": False, "entity_type": "LINE"}},
            {"kind": "recessed_handle_cutout", "geometry": {"path": [[40, 120], [90, 120]], "closed": False, "entity_type": "LINE"}},
        ],
    )
    program = _program(
        pieces=[piece],
        operation_presets={"cut_path": "Finish"},
        operation_order=["liner", "recessed_handle_cutout", "back_groove", "cut_path"],
    )
    drawn = {
        row["operation_key"]: [
            path for path in row["toolpaths"] if len(path.get("points") or []) >= 2
        ]
        for row in program["operations"]
    }
    assert set(drawn) >= {"liner", "back_groove", "recessed_handle_cutout", "cut_path"}
    for key in ("liner", "back_groove", "recessed_handle_cutout"):
        assert drawn[key], key
        assert drawn[key][0]["ready"] is False
        assert drawn[key][0]["motions"] == []
    assert len(drawn["liner"]) == 2
    assert "mill_diameter_required" in drawn["liner"][0]["issues"]
    assert program["geometry_ready"] is False
    bare = _program(
        pieces=[_piece(
            extra_liner=1,
            liner_reference_side="edge_width_top",
            liner_offset_cm=2,
            liner_width_cm=1.8,
        )],
        operation_presets={"cut_path": "Finish"},
        operation_order=["liner", "cut_path"],
    )
    bare_liner = next(row for row in bare["operations"] if row["operation_key"] == "liner")
    assert bare_liner["toolpaths"]
    assert all(len(path.get("points") or []) >= 2 for path in bare_liner["toolpaths"])
    assert all(
        "mill_diameter_required" in path["issues"] and not path["motions"]
        for path in bare_liner["toolpaths"]
    )


def test_unready_geometry_and_production_flag_are_rejected():
    program = _program(operation_presets={"cut_path": "Finish"})
    program["geometry_ready"] = False
    program["ready"] = False
    try:
        emit_nc(program)
        assert False
    except PostProcessorError as exc:
        assert exc.code == "geometry_not_ready"
    ready = _program()
    try:
        emit_nc(ready, machine_profile={"retract_z_mm": 20, "production_approved": True})
        assert False
    except PostProcessorError as exc:
        assert exc.code == "production_controller_not_confirmed"


def test_rapid_moves_are_only_at_safe_height():
    program = _program(operation_presets={"cut_path": "Shallow", "liner": "Shallow"})
    text = emit_nc(program, machine_profile={"retract_z_mm": 15, "production_approved": False}).text
    state = interpret_nc(text, safe_z_mm=15)
    assert state.unsafe_rapids == ()
    assert state.ended is True
    assert verify_nc_against_program(text, program, safe_z_mm=15).ok is True
