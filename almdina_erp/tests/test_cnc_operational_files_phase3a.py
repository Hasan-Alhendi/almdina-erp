"""Phase 3A: prepare CNC motion from approved geometry without writing NC."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cnc.program import (
    CncSourceEntity,
    build_board_program,
    program_payload,
)
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_segments
from almdina_erp.almdina_erp.infrastructure.cutting.cnc_dxf_source import read_operational_dxf


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = APP_ROOT / "almdina_erp" / "services" / "cnc_operational_file_service.py"
DOMAIN = APP_ROOT / "almdina_erp" / "domain" / "cnc" / "program.py"
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
    "Shallow": _raw(preset_name="Shallow", final_depth_mm=7, feed_rate_mm_min=8000, pass_depth_mm=2),
    "Other": _raw(preset_name="Other", tool_number="T8"),
    "Disabled": _raw(preset_name="Disabled", enabled=False),
}


def _rect(x, y, width, height):
    return [[x, y], [x + width, y], [x + width, y + height], [x, y + height]]


def _geometry(outer, holes=None):
    return {
        "schema_version": 1,
        "unit": "mm",
        "coordinate_space": "usable_sheet",
        "outer": outer,
        "holes": holes or [],
    }


def _overlay(kind, layer, path, *, closed=False, toolpath=None):
    geometry = {
        "schema_version": 1,
        "unit": "mm",
        "coordinate_space": "usable_sheet",
        "path": path,
        "closed": closed,
    }
    if toolpath is None:
        toolpath = not closed
    if toolpath:
        geometry["toolpath"] = True
    return {
        "kind": kind,
        "layer": layer,
        "geometry": geometry,
    }


def _piece(instance_id, outer, **extra):
    piece = {
        "piece_instance_id": instance_id,
        "label": extra.pop("label", instance_id),
        "sheet_no": 1,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": _geometry(outer, extra.pop("holes", None)),
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
    return compile_sheet_program(
        sheet_no=kwargs.pop("sheet_no", 1),
        pieces=pieces,
        snapshot=kwargs.pop("snapshot", _snapshot()),
        operation_presets=kwargs.pop("operation_presets", {"cut_path": "Finish", "liner": "Finish"}),
        path_overrides=kwargs.pop("path_overrides", {}),
        operation_order=kwargs.pop("operation_order", ["liner", "recessed_handle_cutout", "back_groove", "cut_path"]),
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


def _line(start, end, **kwargs):
    return CncSourceEntity(
        layer=kwargs.get("layer", "CUT_PATH"),
        points=(start, end),
        closed=False,
        entity_type="LINE",
        role=kwargs.get("role", "tool_center"),
        ring=kwargs.get("ring", "outer"),
        path_key=kwargs.get("path_key", ""),
        piece_instance_id=kwargs.get("piece_id", "piece-a"),
        piece_label=kwargs.get("label", "A"),
    )


def _build(entities, **kwargs):
    program = build_board_program(
        sheet_no=1,
        entities=entities,
        operation_order=kwargs.get("order", ["cut_path", "liner"]),
        operation_presets=kwargs.get("presets", {"cut_path": "Finish", "liner": "Finish"}),
        path_overrides=kwargs.get("overrides", {}),
        known_presets=PRESETS,
        cut_path_early_confirmed=kwargs.get("confirmed", False),
        units=kwargs.get("units", "mm"),
        frame_origin_mm=kwargs.get("origin", (0.0, 0.0)),
        sheet_width_mm=1000,
        sheet_length_mm=2000,
        shared_cut_ambiguous=kwargs.get("ambiguous", False),
    )
    return program_payload(program)


def test_connected_lines_are_one_path_and_a_duplicate_is_not_cut_twice():
    joined = _build([
        _line((0, 0), (10, 0)),
        _line((10, 0), (10, 8)),
        _line((10, 8), (4, 8)),
        _line((10, 0), (0, 0)),
    ])
    paths = _paths(joined, "cut_path")
    assert len(paths) == 1
    assert paths[0]["points"][0] == [0.0, 0.0]
    assert [motion["kind"] for motion in paths[0]["motions"]] == ["travel", "plunge", "cut", "cut", "cut", "retract"]
    assert all(motion["depth_mm"] is None or motion["depth_mm"] > 0 for motion in paths[0]["motions"])


def test_direction_is_deterministic_for_closed_and_open_paths():
    outer = _build([
        CncSourceEntity("CUT_PATH", ((10, 0), (0, 0), (0, 10), (10, 10)), True, "LWPOLYLINE", "tool_center", "outer", "cut_path:a:outer", "a", "A"),
    ])
    same = _build([
        CncSourceEntity("CUT_PATH", ((0, 0), (10, 0), (10, 10), (0, 10)), True, "LWPOLYLINE", "tool_center", "outer", "cut_path:a:outer", "a", "A"),
    ])
    assert _paths(outer, "cut_path")[0]["points"] == _paths(same, "cut_path")[0]["points"]
    assert _paths(outer, "cut_path")[0]["direction"] == "ccw"
    hole = _build([
        CncSourceEntity("CUT_PATH", ((0, 0), (10, 0), (10, 10), (0, 10)), True, "LWPOLYLINE", "tool_center", "hole", "cut_path:a:hole:1", "a", "A"),
    ])
    assert _paths(hole, "cut_path")[0]["direction"] == "cw"
    opened = _build([
        CncSourceEntity("Liner", ((8, 4), (1, 2)), False, "LWPOLYLINE", "tool_center", "open", "liner:a:1", "a", "A"),
    ])
    reverse = _build([
        CncSourceEntity("Liner", ((1, 2), (8, 4)), False, "LWPOLYLINE", "tool_center", "open", "liner:a:1", "a", "A"),
    ])
    assert _paths(opened, "liner")[0]["points"] == _paths(reverse, "liner")[0]["points"]
    assert _paths(opened, "liner")[0]["direction"] == "start_to_end"
    assert _paths(opened, "liner")[0]["start"] == [1, 2]


def test_a_branch_is_split_instead_of_guessing_one_route():
    program = _build([
        _line((0, 0), (5, 0)),
        _line((5, 0), (10, 0)),
        _line((5, 0), (5, 6)),
    ])
    paths = _paths(program, "cut_path")
    assert len(paths) == 3
    covered = sum(math.dist(path["points"][0], path["points"][-1]) for path in paths)
    assert covered == 16


def test_region_boundary_legacy_cut_and_unknown_units_have_no_motion():
    region = _build([
        CncSourceEntity("Liner", ((0, 0), (20, 0), (20, 12), (0, 12)), True, "LWPOLYLINE", "region_boundary", "unknown", "liner:a:1", "a", "A"),
    ])
    assert _paths(region, "liner")[0]["issues"] == ["region_not_supported"]
    assert _motions(region) == []
    legacy = _build([
        CncSourceEntity("CUT_PATH", ((0, 0), (30, 0), (30, 20), (0, 20)), True, "LWPOLYLINE", "finished_boundary", "outer", "cut_path:a:outer", "a", "A"),
    ])
    assert "cut_path_is_piece_boundary" in _paths(legacy, "cut_path")[0]["issues"]
    assert _motions(legacy) == []
    unknown = _build([_line((0, 0), (5, 0))], units="inch")
    assert unknown["issues"][0]["code"] == "units_unknown"
    assert unknown["operations"] == []
    assert unknown["depth_convention"] == "positive_millimetres"
    assert unknown["machine_origin"] == "not_established"


def test_shifted_coordinates_keep_the_same_sheet_geometry():
    local = _build([_line((0, 0), (12, 4))])
    shifted = _build([_line((1000, 2000), (1012, 2004))], origin=(1000, 2000))
    assert _paths(local, "cut_path")[0]["points"] == _paths(shifted, "cut_path")[0]["points"]


def test_same_tool_can_use_different_depth_and_feed_and_confirmation_does_not_clear_errors():
    program = _build(
        [
            CncSourceEntity("Liner", ((0, 0), (10, 0)), False, "LWPOLYLINE", "tool_center", "open", "liner:a:1", "a", "A"),
            CncSourceEntity("CUT_PATH", ((0, 20), (15, 20)), False, "LWPOLYLINE", "tool_center", "open", "cut_path:a:outer", "a", "A"),
        ],
        presets={"liner": "Finish", "cut_path": "Shallow"},
        order=["cut_path", "liner"],
        confirmed=True,
    )
    assert [row["operation_key"] for row in program["operations"]] == ["cut_path", "liner"]
    assert program["cut_path_early"] is True
    assert program["cut_path_early_confirmed"] is True
    depths = {path["path_key"]: path["preset"]["final_depth_mm"] for row in program["operations"] for path in row["toolpaths"]}
    assert depths == {"cut_path:a:outer": 7, "liner:a:1": 18.5}
    feeds = {path["path_key"]: path["preset"]["feed_rate_mm_min"] for row in program["operations"] for path in row["toolpaths"]}
    assert feeds["cut_path:a:outer"] == 8000
    assert feeds["liner:a:1"] == 10200
    shallow = _paths(program, "cut_path")[0]
    assert [motion["depth_mm"] for motion in shallow["motions"] if motion["kind"] == "plunge"] == [2, 4, 6, 7]
    invalid = _build(
        [CncSourceEntity("CUT_PATH", ((float("nan"), 0), (1, 0)), False, "LINE", "tool_center", "open", "cut_path:a:outer", "a", "A")],
        confirmed=True,
        order=["cut_path", "liner"],
    )
    assert invalid["ready"] is False
    assert "geometry_invalid" in _paths(invalid, "cut_path")[0]["issues"]


def test_several_pieces_liners_shared_cuts_and_an_l_shape():
    separated = _compile([
        _piece("piece-a", _rect(0, 0, 200, 500), label="1.1"),
        _piece("piece-b", _rect(400, 0, 180, 500), label="1.2"),
    ])
    cuts = _paths(separated, "cut_path")
    assert {path["piece_label"] for path in cuts} == {"1.1", "1.2"}
    assert all(path["closed"] and path["direction"] == "ccw" and path["ready"] for path in cuts)
    shared = _compile([
        _piece("piece-a", _rect(0, 0, 200, 500), label="1.1"),
        _piece("piece-b", _rect(205, 0, 200, 500), label="1.2"),
    ])
    shared_cuts = [
        path for path in _paths(shared, "cut_path")
        if path["points"] and all(abs(point[0] - 202.5) < 0.2 for point in path["points"])
    ]
    assert len(shared_cuts) == 1
    assert shared_cuts[0]["piece_instance_id"] == ""
    ambiguous = _compile(
        [
            _piece("piece-a", _rect(0, 0, 200, 500)),
            _piece("piece-b", _rect(205, 0, 200, 500)),
        ],
        path_overrides={"cut_path:piece-a:outer": "Shallow"},
    )
    assert any(path["issues"] == ["shared_cut_preset_ambiguous"] or "shared_cut_preset_ambiguous" in path["issues"] for path in _paths(ambiguous, "cut_path") if not path["piece_instance_id"])
    assert ambiguous["ready"] is False
    liners = _compile([
        _piece(
            "piece-a",
            _rect(0, 0, 200, 500),
            overlays=[
                _overlay("liner", "Liner", [[20, 30], [20, 120]]),
                _overlay("liner", "Liner", [[60, 30], [60, 140]]),
            ],
        )
    ])
    liner_paths = _paths(liners, "liner")
    assert len(liner_paths) == 2
    assert all(path["ready"] and path["direction"] == "start_to_end" and not path["closed"] for path in liner_paths)
    first_key = next(path["path_key"] for path in liner_paths if abs(path["points"][0][0] - 60) < 0.1)
    overridden = _compile(
        [
            _piece(
                "piece-a",
                _rect(0, 0, 200, 500),
                overlays=[
                    _overlay("liner", "Liner", [[20, 30], [20, 120]]),
                    _overlay("liner", "Liner", [[60, 30], [60, 140]]),
                ],
            )
        ],
        path_overrides={first_key: "Shallow"},
    )
    chosen = next(path for path in _paths(overridden, "liner") if path["path_key"] == first_key)
    other = next(path for path in _paths(overridden, "liner") if path["path_key"] != first_key)
    assert chosen["preset"]["final_depth_mm"] == 7
    assert other["preset"]["final_depth_mm"] == 18.5
    assert chosen["preset"]["tool_number"] == other["preset"]["tool_number"] == "T9"
    shaped = _compile([
        _piece("piece-a", [[0, 0], [200, 0], [200, 80], [80, 80], [80, 200], [0, 200]]),
    ])
    shape_path = _paths(shaped, "cut_path")[0]
    assert shape_path["ready"] is True
    assert len(shape_path["points"]) != 4
    ordered = _compile(
        [
            _piece(
                "piece-a",
                _rect(0, 0, 200, 400),
                overlays=[_overlay("liner", "Liner", [[20, 20], [20, 80]])],
            )
        ],
        operation_order=["cut_path", "liner"],
        cut_path_early_confirmed=True,
    )
    assert [row["operation_key"] for row in ordered["operations"]] == ["cut_path", "liner"]
    assert ordered["cut_path_early"] is True
    blocked = _compile([
        _piece(
            "piece-a",
            _rect(0, 0, 200, 400),
            overlays=[_overlay("liner", "Liner", [[20, 20], [80, 20], [80, 80], [20, 80]], closed=True)],
        )
    ], cut_path_early_confirmed=True, operation_order=["cut_path", "liner"])
    assert "region_not_supported" in _paths(blocked, "liner")[0]["issues"]
    assert blocked["ready"] is False
    assert _paths(blocked, "liner")[0]["motions"] == []


def test_missing_geometry_kerf_and_disabled_preset_block_motion():
    missing = _compile([
        {
            "piece_instance_id": "piece-a",
            "label": "1.1",
            "sheet_no": 1,
            "extra_liner": 0,
        }
    ])
    assert any(issue["code"] == "finished_geometry_missing" for issue in missing["issues"])
    assert _motions(missing) == []
    no_kerf = _compile(
        [_piece("piece-a", _rect(0, 0, 100, 100))],
        snapshot=_snapshot(kerf_mm=None),
    )
    assert any(issue["code"] == "kerf_unknown" for issue in no_kerf["issues"])
    assert _paths(no_kerf, "cut_path") == []
    disabled = _compile(
        [_piece("piece-a", _rect(0, 0, 100, 100))],
        operation_presets={"cut_path": "Disabled"},
    )
    assert "preset_disabled" in _paths(disabled, "cut_path")[0]["issues"]
    assert _motions(disabled) == []


def test_uploaded_plans_keep_or_reject_the_approved_cut():
    pieces = [_piece("piece-a", _rect(10, 10, 200, 300), label="1.1")]
    generated = _compile(pieces)
    points = _paths(generated, "cut_path")[0]["points"]
    segments = list(zip(points, points[1:])) + [(points[-1], points[0])]
    matched = _compile(
        pieces,
        manufacturing_mode="uploaded_present",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert matched["ready"] is True
    assert _paths(matched, "cut_path")[0]["points"] == points
    boundary = cutter_center_segments([(_rect(10, 10, 200, 300), [])], 0)
    rejected = _compile(
        pieces,
        manufacturing_mode="uploaded_present",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": boundary, "overlays": []},
    )
    assert rejected["ready"] is False
    assert any("cut_path_does_not_match_approved_centers" in path["issues"] for path in _paths(rejected, "cut_path"))
    assert _motions(rejected) == []
    legacy = _compile(
        pieces,
        manufacturing_mode="uploaded_legacy",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": boundary, "overlays": []},
    )
    assert any("cut_path_is_piece_boundary" in path["issues"] for path in _paths(legacy, "cut_path"))
    assert _motions(legacy) == []
    unknown = _compile(
        pieces,
        manufacturing_mode="uploaded_unknown",
        uploaded={"units": "mm", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert any("compensation_unverified" in path["issues"] for path in _paths(unknown, "cut_path"))
    assert _motions(unknown) == []
    inches = _compile(
        pieces,
        manufacturing_mode="uploaded_present",
        uploaded={"units": "inch", "origin": (0, 0), "cut_segments": segments, "overlays": []},
    )
    assert inches["issues"][0]["code"] == "units_unknown"
    assert _motions(inches) == []


def _dxf(origin, units):
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = units
    for name in ("SHEET_OUTLINE", "CUT_PATH", "GEOMETRY", "Liner"):
        document.layers.add(name)
    modelspace = document.modelspace()
    x, y = origin
    modelspace.add_lwpolyline(
        [(x, y), (x + 400, y), (x + 400, y + 600), (x, y + 600)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    modelspace.add_lwpolyline(
        [(x + 10, y + 20), (x + 80, y + 20), (x + 80, y + 90)],
        dxfattribs={"layer": "CUT_PATH"},
    )
    modelspace.add_line((x + 15, y + 30), (x + 15, y + 70), dxfattribs={"layer": "Liner"})
    modelspace.add_lwpolyline(
        [(x + 1, y + 1), (x + 30, y + 1), (x + 30, y + 30)],
        close=True,
        dxfattribs={"layer": "GEOMETRY"},
    )
    return document


def test_a_shifted_dxf_uses_the_sheet_outline_and_ignores_geometry(tmp_path):
    first = tmp_path / "origin.dxf"
    second = tmp_path / "shifted.dxf"
    _dxf((0, 0), 4).saveas(first)
    _dxf((1500, 800), 4).saveas(second)
    origin = read_operational_dxf(str(first), sheet_no=1)
    shifted = read_operational_dxf(str(second), sheet_no=1)
    assert origin["units"] == "mm"
    assert origin["cut_segments"] == shifted["cut_segments"]
    assert origin["overlays"] == shifted["overlays"]
    assert origin["origin"] == (0, 0)
    assert shifted["origin"] == (1500, 800)
    assert all(start[0] < 100 and end[0] < 100 for start, end in origin["cut_segments"])
    inches = tmp_path / "inches.dxf"
    _dxf((0, 0), 1).saveas(inches)
    assert read_operational_dxf(str(inches), sheet_no=1)["units"] == "unknown"


def test_program_text_has_no_machine_words_and_preview_requires_view_permission():
    for path in (DOMAIN, APPLICATION):
        source = path.read_text(encoding="utf-8")
        assert "frappe" not in source
        assert "G01" not in source
        assert "G00" not in source
        assert "M03" not in source
    service = SERVICE.read_text(encoding="utf-8")
    body = service.split("def get_cnc_sheet_program", 1)[1].split("\ndef ", 1)[0]
    assert "Capability.VIEW_CNC_OPERATIONAL_FILES" in body
    assert "save_sheet" not in body
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" not in body
    payload = _compile([_piece("piece-a", _rect(0, 0, 100, 80))])
    rendered = str(payload)
    assert "G01" not in rendered
    assert "G00" not in rendered
    assert payload["coordinate_space"] == "sheet_bottom_left_y_up_mm"
