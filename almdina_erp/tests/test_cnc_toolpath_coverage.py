"""Toolpath coverage: kerf, mill reuse, uploaded plans, and units.

Fixtures are explicit. They do not claim a match to an ArtCAM sample.
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_paths
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    sawn_liner_ends,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    generate_liner_set_toolpaths,
    generate_toolpath,
)
from almdina_erp.almdina_erp.infrastructure.cutting.cnc_dxf_source import read_operational_dxf


APP_ROOT = Path(__file__).resolve().parents[1]
APPLICATION = APP_ROOT / "almdina_erp" / "application" / "cnc" / "program.py"


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 5,
        "final_depth_mm": 18.5,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 10200,
        "plunge_rate_mm_min": 1800,
        "pass_depth_mm": None,
        "enabled": True,
    }
    values.update(overrides)
    return values


PRESETS = {
    "Finish": _raw(),
    "Shallow": _raw(preset_name="Shallow", final_depth_mm=7, feed_rate_mm_min=8000),
    "Wide": _raw(preset_name="Wide", tool_diameter_mm=8),
}


def _rect(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def _piece(instance_id, outer, **extra):
    piece = {
        "piece_instance_id": instance_id,
        "label": extra.pop("label", instance_id),
        "sheet_no": 1,
        "piece_type": "Regular",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": {
            "schema_version": 1,
            "unit": "mm",
            "coordinate_space": "usable_sheet",
            "outer": outer,
            "holes": extra.pop("holes", []),
        },
    }
    piece.update(extra)
    return piece


def _snapshot(**extra):
    snapshot = {
        "kerf_mm": 5,
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
            }
        ],
    }
    snapshot.update(extra)
    return snapshot


def _compile(pieces, **kwargs):
    presets = {
        "cut_path": "Finish",
        "liner": "Finish",
        "back_groove": "Finish",
        "recessed_handle_cutout": "Finish",
    }
    presets.update(kwargs.pop("operation_presets", {}))
    return compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=kwargs.pop("snapshot", _snapshot()),
        operation_presets=presets,
        path_overrides=kwargs.pop("path_overrides", {}),
        operation_order=kwargs.pop(
            "operation_order",
            ["liner", "recessed_handle_cutout", "back_groove", "cut_path"],
        ),
        known_presets=PRESETS,
        cut_path_early_confirmed=kwargs.pop("cut_path_early_confirmed", False),
        manufacturing_mode=kwargs.pop("manufacturing_mode", "generated"),
        uploaded=kwargs.pop("uploaded", None),
    )


def _paths(program, operation):
    for row in program["operations"]:
        if row["operation_key"] == operation:
            return row["toolpaths"]
    return []


def _motions(program):
    return [
        motion
        for operation in program["operations"]
        for path in operation["toolpaths"]
        for motion in path["motions"]
    ]


def _codes(program):
    found = [issue["code"] for issue in program["issues"]]
    for operation in program["operations"]:
        for path in operation["toolpaths"]:
            found.extend(path["issues"])
    return found


def _placed(piece):
    return {
        "piece_type": piece.get("piece_type") or "Regular",
        "width_cm": piece["original_width_cm"],
        "length_cm": piece["original_length_cm"],
        "x_mm": piece["x_mm"],
        "y_mm": piece["y_mm"],
        "quarter_turns": 1 if piece.get("rotated") else 0,
        "clipped_corner_position": piece.get("clipped_corner_position") or "Top Right",
        "clipped_corner_width_cm": piece.get("clipped_corner_width_cm") or 0,
        "clipped_corner_length_cm": piece.get("clipped_corner_length_cm") or 0,
    }


def _sheet_points(path, placement, *, length_mm=2440, trim_x=0, trim_y=0):
    width = placement["width_cm"] * 10
    height = placement["length_cm"] * 10
    placed = []
    for point in path:
        turned = transform_point(
            point,
            mirrored=False,
            quarter_turns=placement["quarter_turns"],
            width=width,
            height=height,
        )
        placed.append((turned[0] + placement["x_mm"], turned[1] + placement["y_mm"]))
    return [(trim_x + point[0], length_mm - trim_y - point[1]) for point in placed]


def _same_sequence(actual, expected):
    forward = [[round(point[0], 3), round(point[1], 3)] for point in expected]
    backward = list(reversed(forward))
    got = [[round(point[0], 3), round(point[1], 3)] for point in actual]
    return got == forward or got == backward


def _expected_mill(piece, kind, spec, *, diameter=5, length_mm=2440, trim_x=0, trim_y=0, width_mm=1220):
    placement = _placed(piece)
    liner = LinerPiece(
        placement["piece_type"],
        placement["width_cm"],
        placement["length_cm"],
        placement["clipped_corner_position"],
        placement["clipped_corner_width_cm"],
        placement["clipped_corner_length_cm"],
    )
    board = (-trim_x, -trim_y, width_mm - trim_x, length_mm - trim_y)
    start_sawn, end_sawn = sawn_liner_ends(
        liner,
        spec["side"],
        origin_mm=(placement["x_mm"], placement["y_mm"]),
        mirrored=False,
        quarter_turns=placement["quarter_turns"],
        board=board,
        start_cm=spec["start_cm"],
        length_cm=spec["length_cm"],
    )
    path = generate_toolpath(
        kind=kind,
        piece=liner,
        reference_side=spec["side"],
        offset_cm=spec["offset_cm"],
        width_cm=spec["width_cm"],
        start_cm=spec["start_cm"],
        length_cm=spec["length_cm"],
        cutter_diameter_mm=diameter,
        start_sawn=start_sawn,
        end_sawn=end_sawn,
    )
    return _sheet_points(path, placement, length_mm=length_mm, trim_x=trim_x, trim_y=trim_y)


def _mill_piece(instance_id="piece-a", **extra):
    extra.setdefault("original_width_cm", 40)
    extra.setdefault("original_length_cm", 80)
    extra.setdefault("x_mm", 100)
    extra.setdefault("y_mm", 80)
    return _piece(instance_id, _rect(100, 80, 400, 800), **extra)


def test_a_sheet_with_only_cut_path_is_ready_when_the_diameter_matches_the_kerf():
    program = _compile([_piece("piece-a", _rect(10, 20, 200, 300), label="1.1")])
    cuts = _paths(program, "cut_path")
    assert program["ready"] is True
    assert len(cuts) == 1
    assert cuts[0]["closed"] is True
    assert cuts[0]["preset"]["tool_diameter_mm"] == 5
    assert cuts[0]["preset_name"] == "Finish"
    assert _paths(program, "liner") == []
    shape = _rect(10, 20, 200, 300)
    sheet = [(point[0], 2440 - point[1]) for point in shape]
    expected = cutter_center_paths([(sheet, [])], 2.5)[0].points
    assert _same_sequence(cuts[0]["points"], expected)


def test_tool_diameter_must_match_the_approved_kerf_and_is_not_recalculated():
    pieces = [_piece("piece-a", _rect(10, 20, 200, 300), label="1.1")]
    matched = _compile(pieces)
    mismatched = _compile(pieces, operation_presets={"cut_path": "Wide"})
    assert matched["ready"] is True
    assert mismatched["ready"] is False
    path = _paths(mismatched, "cut_path")[0]
    assert path["preset"]["tool_diameter_mm"] == 8
    assert path["preset_name"] == "Wide"
    assert "tool_diameter_kerf_mismatch" in path["issues"]
    assert path["motions"] == []
    assert path["points"] == _paths(matched, "cut_path")[0]["points"]
    wide = cutter_center_paths(
        [([(point[0], 2440 - point[1]) for point in _rect(10, 20, 200, 300)], [])],
        4,
    )[0].points
    assert not _same_sequence(path["points"], wide)


def test_cut_path_and_liner_use_the_existing_cutter_center():
    spec = {"side": "edge_width_top", "offset_cm": 2, "width_cm": 1.8, "start_cm": 0, "length_cm": 0}
    piece = _mill_piece(
        extra_liner=1,
        liner_reference_side=spec["side"],
        liner_offset_cm=spec["offset_cm"],
        liner_width_cm=spec["width_cm"],
    )
    program = _compile([piece])
    assert program["ready"] is True
    liner = _paths(program, "liner")
    assert len(liner) == 1
    assert liner[0]["closed"] is False
    assert liner[0]["path_key"] == "liner:piece-a:liner_1"
    assert liner[0]["preset_name"] == "Finish"
    assert _same_sequence(liner[0]["points"], _expected_mill(piece, "liner", spec))
    assert len(_paths(program, "cut_path")) == 1


def test_four_operations_and_a_closed_region_are_not_the_same_thing():
    spec = {"side": "edge_long_left", "offset_cm": 3, "width_cm": 1.6, "start_cm": 4, "length_cm": 20}
    piece = _mill_piece(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=2,
        liner_width_cm=1.8,
        extra_back_groove=1,
        back_groove_reference_side=spec["side"],
        back_groove_offset_cm=spec["offset_cm"],
        back_groove_width_cm=spec["width_cm"],
        back_groove_start_cm=spec["start_cm"],
        back_groove_length_cm=spec["length_cm"],
        extra_recessed_handle_cutout=1,
        recessed_handle_reference_side="edge_width_bottom",
        recessed_handle_offset_cm=2,
        recessed_handle_width_cm=1.8,
        recessed_handle_start_cm=10,
        recessed_handle_length_cm=18,
    )
    program = _compile([piece])
    assert program["ready"] is True
    assert [row["operation_key"] for row in program["operations"]] == [
        "liner",
        "recessed_handle_cutout",
        "back_groove",
        "cut_path",
    ]
    groove = _paths(program, "back_groove")[0]
    handle = _paths(program, "recessed_handle_cutout")[0]
    assert groove["closed"] is False and handle["closed"] is False
    assert groove["path_key"] == "back_groove:piece-a:primary"
    assert handle["path_key"] == "recessed_handle_cutout:piece-a:primary"
    assert _same_sequence(groove["points"], _expected_mill(piece, "back_groove", spec))
    assert _same_sequence(
        handle["points"],
        _expected_mill(
            piece,
            "recessed_handle_cutout",
            {"side": "edge_width_bottom", "offset_cm": 2, "width_cm": 1.8, "start_cm": 10, "length_cm": 18},
        ),
    )
    closed = _compile([
        _piece(
            "piece-a",
            _rect(0, 0, 200, 400),
            overlays=[{
                "kind": "liner",
                "layer": "Liner",
                "geometry": {
                    "schema_version": 1,
                    "unit": "mm",
                    "coordinate_space": "usable_sheet",
                    "path": [[20, 20], [80, 20], [80, 80], [20, 80]],
                    "closed": True,
                },
            }],
        )
    ])
    assert "region_not_supported" in _codes(closed)
    assert _motions(closed) == [] or _paths(closed, "liner")[0]["motions"] == []
    assert closed["ready"] is False


def test_closed_region_with_mill_settings_becomes_the_existing_zigzag():
    piece = _mill_piece(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=2,
        liner_width_cm=1.8,
        overlays=[{
            "kind": "liner",
            "layer": "Liner",
            "geometry": {
                "schema_version": 1,
                "unit": "mm",
                "coordinate_space": "usable_sheet",
                "path": [[110, 90], [490, 90], [490, 110], [110, 110]],
                "closed": True,
            },
        }],
    )
    program = _compile([piece])
    paths = _paths(program, "liner")
    assert program["ready"] is True
    assert len(paths) == 1
    assert paths[0]["closed"] is False
    assert len(paths[0]["points"]) > 4
    assert paths[0]["path_key"].startswith("liner:piece-a:")
    assert _same_sequence(
        paths[0]["points"],
        _expected_mill(
            piece,
            "liner",
            {"side": "edge_width_top", "offset_cm": 2, "width_cm": 1.8, "start_cm": 0, "length_cm": 0},
        ),
    )


def test_five_liners_inherit_one_preset_until_one_path_is_overridden():
    specs = [
        {"id": "liner_1", "side": "edge_width_top", "offset_cm": 2, "start_cm": 0, "length_cm": 30},
        {"id": "liner_2", "side": "edge_long_left", "offset_cm": 3, "start_cm": 5, "length_cm": 20},
        {"id": "liner_3", "side": "edge_long_right", "offset_cm": 3, "start_cm": 5, "length_cm": 20},
        {"id": "liner_4", "side": "edge_width_bottom", "offset_cm": 2, "start_cm": 0, "length_cm": 20},
        {"id": "liner_5", "side": "edge_width_top", "offset_cm": 8, "start_cm": 10, "length_cm": 15},
    ]
    piece = _mill_piece(
        extra_liner=1,
        liner_width_cm=1.6,
        liner_specs_json=json.dumps({"width_cm": 1.6, "liners": specs}),
    )
    program = _compile([piece])
    paths = _paths(program, "liner")
    assert len(paths) == 5
    assert {path["preset_name"] for path in paths} == {"Finish"}
    assert {path["preset"]["final_depth_mm"] for path in paths} == {18.5}
    assert all(path["ready"] and not path["closed"] for path in paths)
    changed = _compile([piece], operation_presets={"liner": "Shallow"})
    assert {path["preset"]["final_depth_mm"] for path in _paths(changed, "liner")} == {7}
    assert {path["preset_name"] for path in _paths(changed, "cut_path")} == {"Finish"}
    target = next(path["path_key"] for path in paths if path["path_key"].endswith("liner_3"))
    overridden = _compile([piece], path_overrides={target: "Shallow"})
    chosen = next(path for path in _paths(overridden, "liner") if path["path_key"] == target)
    others = [path for path in _paths(overridden, "liner") if path["path_key"] != target]
    assert chosen["preset"]["final_depth_mm"] == 7
    assert {path["preset"]["final_depth_mm"] for path in others} == {18.5}
    assert overridden["ready"] is True


def test_overlapping_liners_are_milled_once_and_a_split_preset_is_rejected():
    specs = [
        {"id": "liner_1", "side": "edge_width_top", "offset_cm": 2, "start_cm": 0, "length_cm": 0},
        {"id": "liner_2", "side": "edge_width_top", "offset_cm": 2.4, "start_cm": 0, "length_cm": 0},
    ]
    piece = _mill_piece(
        extra_liner=1,
        liner_width_cm=1.8,
        liner_specs_json=json.dumps({"width_cm": 1.8, "liners": specs}),
    )
    placement = _placed(piece)
    liner = LinerPiece("Regular", 40, 80)
    board = (0, 0, 1220, 2440)
    sawn = [
        sawn_liner_ends(
            liner,
            spec["side"],
            origin_mm=(100, 80),
            mirrored=False,
            quarter_turns=0,
            board=board,
            start_cm=0,
            length_cm=0,
        )
        for spec in specs
    ]
    expected = generate_liner_set_toolpaths(
        piece=liner,
        specs=specs,
        width_cm=1.8,
        cutter_diameter_mm=5,
        start_sawn=[item[0] for item in sawn],
        end_sawn=[item[1] for item in sawn],
    )
    program = _compile([piece])
    paths = _paths(program, "liner")
    assert len(expected) == 2
    assert len(paths) == 2
    assert any(path["path_key"] == "liner:piece-a:liner_1" for path in paths)
    assert not any(path["path_key"].endswith("liner_2") for path in paths)
    assert any(":merged:" in path["path_key"] for path in paths)
    for path in paths:
        assert any(
            _same_sequence(path["points"], _sheet_points(candidate, placement))
            for candidate in expected
        )
    assert program["ready"] is True
    rejected = _compile([piece], path_overrides={"liner:piece-a:liner_2": "Shallow"})
    assert rejected["ready"] is False
    assert "merged_mill_preset_ambiguous" in _codes(rejected)
    assert _paths(rejected, "liner")[0]["motions"] == []


def test_a_shared_cut_is_not_repeated_or_given_one_piece_preset():
    pieces = [
        _piece("piece-a", _rect(0, 0, 200, 500), label="1.1"),
        _piece("piece-b", _rect(205, 0, 200, 500), label="1.2"),
    ]
    program = _compile(pieces)
    shared = [
        path for path in _paths(program, "cut_path")
        if path["points"] and all(abs(point[0] - 202.5) < 0.2 for point in path["points"])
    ]
    assert len(shared) == 1
    assert shared[0]["piece_instance_id"] == ""
    assert program["ready"] is True
    ambiguous = _compile(pieces, path_overrides={"cut_path:piece-a:outer": "Shallow"})
    assert ambiguous["ready"] is False
    assert "shared_cut_preset_ambiguous" in _codes(ambiguous)


def test_rotated_piece_and_trim_keep_the_same_mill_placement():
    spec = {"side": "edge_width_top", "offset_cm": 2, "width_cm": 1.8, "start_cm": 0, "length_cm": 0}
    piece = _mill_piece(
        rotated=1,
        extra_liner=1,
        liner_reference_side=spec["side"],
        liner_offset_cm=2,
        liner_width_cm=1.8,
    )
    snapshot = _snapshot()
    snapshot["sheets"][0]["applied_trim_width_cm"] = 1
    snapshot["sheets"][0]["applied_trim_length_cm"] = 1
    program = _compile([piece], snapshot=snapshot)
    path = _paths(program, "liner")[0]
    assert _same_sequence(
        path["points"],
        _expected_mill(piece, "liner", spec, length_mm=2440, trim_x=10, trim_y=10, width_mm=1220),
    )


def test_uploaded_present_legacy_unknown_and_unspecified_units_stay_distinct():
    pieces = [_piece("piece-a", _rect(10, 10, 200, 300), label="1.1")]
    generated = _compile(pieces)
    points = _paths(generated, "cut_path")[0]["points"]
    segments = list(zip(points, points[1:])) + [(points[-1], points[0])]
    present = _compile(
        pieces,
        manufacturing_mode="uploaded_present",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert present["ready"] is True
    assert _paths(present, "cut_path")[0]["points"] == points
    wide = _compile(
        pieces,
        operation_presets={"cut_path": "Wide"},
        manufacturing_mode="uploaded_present",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert wide["ready"] is False
    assert "tool_diameter_kerf_mismatch" in _codes(wide)
    assert _motions(wide) == []
    legacy = _compile(
        pieces,
        manufacturing_mode="uploaded_legacy",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert "cut_path_is_piece_boundary" in _codes(legacy)
    assert _motions(legacy) == []
    unknown = _compile(
        pieces,
        manufacturing_mode="uploaded_unknown",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert "compensation_unverified" in _codes(unknown)
    assert _motions(unknown) == []
    unspecified = _compile(
        pieces,
        manufacturing_mode="uploaded_present",
        uploaded={"units": "unspecified", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert unspecified["issues"][0]["code"] == "units_unspecified"
    assert unspecified["operations"] == []
    open_mill = _compile(
        pieces,
        manufacturing_mode="uploaded_present",
        uploaded={
            "units": "mm",
            "origin": (0, 0),
            "cut_segments": segments,
            "overlays": [{"layer": "Liner", "points": [(30, 40), (30, 90)], "closed": False, "entity_type": "LINE"}],
        },
    )
    assert "mill_path_unverified" in _codes(open_mill)
    assert open_mill["ready"] is False


def test_missing_placement_invalid_geometry_and_a_narrow_band_do_not_invent_a_path():
    unplaced = _compile([
        _piece(
            "piece-a",
            _rect(0, 0, 400, 800),
            extra_liner=1,
            liner_reference_side="edge_width_top",
            liner_offset_cm=2,
            liner_width_cm=1.8,
        )
    ])
    assert "mill_placement_unknown" in _codes(unplaced)
    assert _paths(unplaced, "liner")[0]["motions"] == []
    assert _paths(unplaced, "liner")[0]["points"] == []
    invalid = _compile([{
        "piece_instance_id": "piece-a",
        "label": "1.1",
        "sheet_no": 1,
        "geometry": {
            "unit": "mm",
            "coordinate_space": "board",
            "outer": _rect(0, 0, 100, 100),
            "holes": [],
        },
    }])
    assert "geometry_invalid" in _codes(invalid)
    assert _motions(invalid) == []
    narrow = _mill_piece(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=2,
        liner_width_cm=0.3,
    )
    blocked = _compile([narrow])
    assert "liner_narrower_than_cutter" in _codes(blocked)
    assert _paths(blocked, "liner")[0]["motions"] == []


def test_an_open_drawing_path_is_not_a_center_unless_marked_or_calculated():
    unverified = _compile([
        _piece(
            "piece-a",
            _rect(0, 0, 200, 400),
            overlays=[{
                "kind": "liner",
                "layer": "Liner",
                "geometry": {
                    "unit": "mm",
                    "coordinate_space": "usable_sheet",
                    "path": [[20, 30], [20, 120]],
                    "closed": False,
                },
            }],
        )
    ])
    assert "mill_path_unverified" in _codes(unverified)
    assert unverified["ready"] is False
    verified = _compile([
        _piece(
            "piece-a",
            _rect(0, 0, 200, 400),
            overlays=[{
                "kind": "liner",
                "layer": "Liner",
                "geometry": {
                    "unit": "mm",
                    "coordinate_space": "usable_sheet",
                    "path": [[20, 30], [20, 120]],
                    "closed": False,
                    "toolpath": True,
                },
            }],
        )
    ])
    path = _paths(verified, "liner")[0]
    assert path["ready"] is True
    assert _same_sequence(path["points"], [(20, 2440 - 30), (20, 2440 - 120)])


def test_results_are_stable_and_this_compiler_does_not_own_nesting_or_export(tmp_path):
    from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf

    piece = _mill_piece(
        extra_liner=1,
        liner_reference_side="edge_width_top",
        liner_offset_cm=2,
        liner_width_cm=1.8,
    )
    assert _compile([piece]) == _compile([piece])
    first = _compile([piece])
    assert first["geometry_ready"] is True
    assert first["machine_ready"] is False
    assert first["nc_export_ready"] is True
    source = APPLICATION.read_text(encoding="utf-8")
    assert "dxf_export_service" not in source
    assert "nesting" not in source
    assert "piece_cost" not in source
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 0
    document.layers.add("SHEET_OUTLINE")
    document.modelspace().add_lwpolyline([(0, 0), (400, 0), (400, 600), (0, 600)], close=True, dxfattribs={"layer": "SHEET_OUTLINE"})
    target = tmp_path / "unspecified.dxf"
    document.saveas(target)
    assert read_operational_dxf(str(target), sheet_no=1)["units"] == "unspecified"
    document.header["$INSUNITS"] = 4
    stated = tmp_path / "millimetres.dxf"
    document.saveas(stated)
    assert read_operational_dxf(str(stated), sheet_no=1)["units"] == "mm"
    raw = (
        "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n9\n$INSUNITS\n70\n4\n0\nENDSEC\n"
        "0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n1\n0\nLAYER\n2\nSHEET_OUTLINE\n70\n0\n62\n8\n6\nCONTINUOUS\n0\nENDTAB\n0\nENDSEC\n"
        "0\nSECTION\n2\nENTITIES\n0\nLINE\n8\nSHEET_OUTLINE\n10\n0\n20\n0\n11\n10\n21\n0\n0\nENDSEC\n0\nEOF\n"
    ).encode("ascii")
    rebuilt = tmp_path / "rebuilt.dxf"
    rebuilt.write_bytes(rebuild_autocad_dxf(raw))
    assert read_operational_dxf(str(rebuilt), sheet_no=1)["units"] == "mm"
