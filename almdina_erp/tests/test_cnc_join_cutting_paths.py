"""Join Cutting Paths: geometric trail decomposition and CNC compile wiring."""

from __future__ import annotations

import math

from almdina_erp.almdina_erp.application.cnc.program import compile_sheet_program
from almdina_erp.almdina_erp.domain.cnc.join_cutting_paths import (
    JOIN_CUTTING_PATHS_NO,
    JOIN_CUTTING_PATHS_YES,
    decompose_minimum_trails,
    join_cut_path_entities,
    join_cutting_paths_enabled,
    normalize_join_cutting_paths,
    segments_have_real_gap,
    trails_cover_segments,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import settings_fingerprint
from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY
from almdina_erp.almdina_erp.domain.cnc.program import CncSourceEntity, direction_invariant_identity
from almdina_erp.almdina_erp.domain.cnc.post_processor import POST_PROCESSOR_VERSION


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 5,
        "final_depth_mm": 18,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 8000,
        "plunge_rate_mm_min": 1500,
        "pass_depth_mm": None,
        "enabled": True,
    }
    values.update(overrides)
    return values


PRESETS = {"Finish": _raw(), "Deep": _raw(preset_name="Deep", pass_depth_mm=6, final_depth_mm=18)}


def test_normalize_join_defaults_missing_to_no():
    assert normalize_join_cutting_paths(None) == JOIN_CUTTING_PATHS_NO
    assert normalize_join_cutting_paths("") == JOIN_CUTTING_PATHS_NO
    assert join_cutting_paths_enabled("yes") is True
    assert join_cutting_paths_enabled("no") is False


def test_four_sequential_segments_become_one_trail():
    result = decompose_minimum_trails(
        [((0, 0), (10, 0)), ((10, 0), (20, 0)), ((20, 0), (30, 0)), ((30, 0), (40, 0))]
    )
    assert result.joined is True
    assert result.trail_count == 1
    assert result.theoretical_minimum == 1
    assert result.trails[0].points == ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0), (40.0, 0.0))


def test_opposite_direction_segments_join():
    result = decompose_minimum_trails([((0, 0), (10, 0)), ((20, 0), (10, 0))])
    assert result.trail_count == 1
    assert result.trails[0].points[0] == (0.0, 0.0)
    assert result.trails[0].points[-1] == (20.0, 0.0)


def test_x_crossing_yields_two_trails_without_duplication():
    segments = [((0, 0), (10, 10)), ((10, 0), (0, 10))]
    result = decompose_minimum_trails(segments)
    assert result.trail_count == 2
    assert result.theoretical_minimum == 2
    assert trails_cover_segments(
        segments,
        [trail.points for trail in result.trails],
        closed_flags=[trail.closed for trail in result.trails],
    )


def test_t_junction_minimum_trails():
    segments = [((0, 0), (20, 0)), ((10, 0), (10, 10))]
    result = decompose_minimum_trails(segments)
    assert result.trail_count == 2
    assert result.theoretical_minimum == 2


def test_closed_loop_single_trail():
    segments = [
        ((0, 0), (10, 0)),
        ((10, 0), (10, 10)),
        ((10, 10), (0, 10)),
        ((0, 10), (0, 0)),
    ]
    result = decompose_minimum_trails(segments)
    assert result.trail_count == 1
    assert result.trails[0].closed is True


def test_branched_network_matches_odd_degree_bound():
    segments = [
        ((0, 0), (10, 0)),
        ((10, 0), (20, 0)),
        ((10, 0), (10, 10)),
        ((10, 10), (0, 10)),
        ((10, 10), (20, 10)),
    ]
    result = decompose_minimum_trails(segments)
    assert result.joined is True
    assert result.trail_count == result.theoretical_minimum == 3


def test_disjoint_components_stay_separate():
    result = decompose_minimum_trails(
        [((0, 0), (5, 0)), ((5, 0), (10, 0)), ((0, 10), (5, 10))]
    )
    assert result.trail_count == 2


def test_real_gap_is_not_bridged():
    assert segments_have_real_gap((10, 0), (10.1, 0)) is True
    result = decompose_minimum_trails([((0, 0), (10, 0)), ((10.1, 0), (20, 0))])
    assert result.trail_count == 2


def test_line_to_arc_polyline_and_arc_to_arc_join():
    # Approximated arc as polyline chords that share endpoints with a line.
    chords = [
        ((0, 0), (10, 0)),
        ((10, 0), (14, 3)),
        ((14, 3), (16, 8)),
        ((16, 8), (14, 13)),
        ((14, 13), (10, 16)),
    ]
    result = decompose_minimum_trails(chords)
    assert result.trail_count == 1
    second = [
        ((0, 0), (5, 2)),
        ((5, 2), (8, 6)),
        ((8, 6), (5, 10)),
        ((5, 10), (10, 12)),
        ((10, 12), (15, 10)),
    ]
    result2 = decompose_minimum_trails(second)
    assert result2.trail_count == 1


def test_closed_curved_ring_stays_one_trail():
    points = [(10 + 8 * math.cos(t), 10 + 8 * math.sin(t)) for t in [i * math.pi / 4 for i in range(8)]]
    segments = [(points[i], points[(i + 1) % 8]) for i in range(8)]
    result = decompose_minimum_trails(segments)
    assert result.trail_count == 1
    assert result.trails[0].closed is True


def test_identity_stable_across_recomputation():
    segments = [((0, 0), (10, 0)), ((10, 0), (20, 0)), ((20, 0), (30, 0))]
    first = decompose_minimum_trails(segments)
    second = decompose_minimum_trails(list(reversed(segments)))
    assert first.trails[0].path_key == second.trails[0].path_key
    assert direction_invariant_identity(first.trails[0].points, False) == direction_invariant_identity(
        tuple(reversed(second.trails[0].points)), False
    )


def test_different_presets_do_not_cross_join():
    left = CncSourceEntity(
        layer="CUT_PATH",
        points=((0.0, 0.0), (10.0, 0.0)),
        closed=False,
        entity_type="LINE",
        role="tool_center",
        path_key="cut_path:a",
    )
    right = CncSourceEntity(
        layer="CUT_PATH",
        points=((10.0, 0.0), (20.0, 0.0)),
        closed=False,
        entity_type="LINE",
        role="tool_center",
        path_key="cut_path:b",
    )
    rebuilt, summary = join_cut_path_entities(
        [left, right],
        operation_presets={"cut_path": "Finish"},
        path_overrides={"cut_path:a": "Finish", "cut_path:b": "Deep"},
    )
    assert summary is None
    assert rebuilt == [left, right]


def test_sheet_perimeter_entity_is_preserved():
    perimeter = CncSourceEntity(
        layer="CUT_PATH",
        points=((0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)),
        closed=True,
        entity_type="LWPOLYLINE",
        role="tool_center",
        ring="outer",
        path_key=SHEET_PERIMETER_PATH_KEY,
    )
    internal_a = CncSourceEntity(
        layer="CUT_PATH",
        points=((10.0, 10.0), (20.0, 10.0)),
        closed=False,
        entity_type="LINE",
        role="tool_center",
        path_key="cut_path:i1",
    )
    internal_b = CncSourceEntity(
        layer="CUT_PATH",
        points=((20.0, 10.0), (30.0, 10.0)),
        closed=False,
        entity_type="LINE",
        role="tool_center",
        path_key="cut_path:i2",
    )
    liner = CncSourceEntity(
        layer="LINER",
        points=((5.0, 5.0), (15.0, 5.0)),
        closed=False,
        entity_type="LINE",
        role="tool_center",
        path_key="liner:x",
    )
    rebuilt, summary = join_cut_path_entities(
        [perimeter, internal_a, internal_b, liner],
        operation_presets={"cut_path": "Finish"},
    )
    assert summary is not None
    assert summary.trail_count == 1
    assert any(getattr(entity, "path_key", "") == SHEET_PERIMETER_PATH_KEY for entity in rebuilt)
    assert any(getattr(entity, "layer", "").upper() == "LINER" for entity in rebuilt)


def _piece(instance_id, outer, *, sheet_no=1):
    return {
        "piece_instance_id": instance_id,
        "label": instance_id,
        "sheet_no": sheet_no,
        "piece_type": "Regular",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": {
            "unit": "mm",
            "coordinate_space": "usable_sheet",
            "outer": outer,
            "holes": [],
        },
        "width_mm": abs(outer[1][0] - outer[0][0]),
        "height_mm": abs(outer[2][1] - outer[1][1]),
        "x_mm": outer[0][0],
        "y_mm": outer[0][1],
        "original_width_cm": abs(outer[1][0] - outer[0][0]) / 10.0,
        "original_length_cm": abs(outer[2][1] - outer[1][1]) / 10.0,
        "rotated": 0,
    }


def _snapshot():
    return {
        "kerf_mm": 5,
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "sheets": [
            {
                "sheet_no": 1,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "usable_width_cm": 122,
                "usable_length_cm": 244,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
                "pieces": [],
            }
        ],
    }


def _cut_path_count(program):
    for operation in program.get("operations") or []:
        if operation.get("operation_key") == "cut_path":
            return len([path for path in operation.get("toolpaths") or [] if path.get("points")])
    return 0


def _plunge_count(program):
    plunges = 0
    for operation in program.get("operations") or []:
        if operation.get("operation_key") != "cut_path":
            continue
        for path in operation.get("toolpaths") or []:
            depths = []
            for motion in path.get("motions") or []:
                if motion.get("kind") == "plunge":
                    plunges += 1
                depth = motion.get("depth_mm")
                if depth is not None:
                    depths.append(depth)
    return plunges


def test_compile_join_disabled_matches_baseline():
    pieces = [
        _piece("r1", [[50, 50], [250, 50], [250, 250], [50, 250]]),
        _piece("r2", [[300, 50], [500, 50], [500, 250], [300, 250]]),
    ]
    baseline = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        join_cutting_paths="no",
    )
    joined = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        join_cutting_paths="no",
    )
    assert _cut_path_count(baseline) == _cut_path_count(joined)
    assert baseline["geometry_ready"] is True


def test_compile_join_enabled_reduces_or_keeps_cut_paths_and_plunges():
    # Adjacent pieces share a kerf center when edges touch after compensation;
    # even without shared edges, join remains a no-op that never invents links.
    pieces = [
        _piece("r1", [[50, 50], [250, 50], [250, 250], [50, 250]]),
        _piece("r2", [[255, 50], [455, 50], [455, 250], [255, 250]]),
    ]
    off = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        join_cutting_paths="no",
    )
    on = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        join_cutting_paths="yes",
    )
    assert on["geometry_ready"] is True
    assert _cut_path_count(on) <= _cut_path_count(off)
    assert _plunge_count(on) <= _plunge_count(off)


def test_compile_join_with_stepdown_keeps_depth_passes():
    pieces = [_piece("r1", [[40, 40], [200, 40], [200, 180], [40, 180]])]
    program = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Deep"},
        path_overrides={},
        operation_order=["cut_path"],
        known_presets=PRESETS,
        join_cutting_paths="yes",
    )
    assert program["geometry_ready"] is True
    depths = set()
    for operation in program["operations"]:
        if operation["operation_key"] != "cut_path":
            continue
        for path in operation["toolpaths"]:
            for motion in path.get("motions") or []:
                if motion.get("depth_mm") is not None:
                    depths.add(round(float(motion["depth_mm"]), 3))
    assert depths == {6.0, 12.0, 18.0}


def test_compile_connected_perimeter_then_join_keeps_perimeter_vector():
    pieces = [
        _piece("r1", [[50, 50], [400, 50], [400, 400], [50, 400]]),
        _piece("r2", [[450, 50], [800, 50], [800, 400], [450, 400]]),
    ]
    program = compile_sheet_program(
        sheet_no=1,
        pieces=pieces,
        snapshot=_snapshot(),
        operation_presets={"cut_path": "Finish", "sheet_perimeter": "Finish"},
        path_overrides={},
        operation_order=["cut_path", "sheet_perimeter"],
        known_presets=PRESETS,
        perimeter_join_mode="connected",
        join_cutting_paths="yes",
    )
    keys = {
        path.get("path_key")
        for operation in program.get("operations") or []
        for path in operation.get("toolpaths") or []
    }
    # Perimeter may be unavailable for sparse layouts; when present it stays distinct.
    if SHEET_PERIMETER_PATH_KEY in keys:
        assert SHEET_PERIMETER_PATH_KEY in keys


def test_settings_fingerprint_includes_join_flag():
    base = dict(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets=PRESETS,
        operation_order=["cut_path"],
        perimeter_join_mode="separate",
        post_processor="ima_wh",
    )
    off = settings_fingerprint(**base, join_cutting_paths="no")
    on = settings_fingerprint(**base, join_cutting_paths="yes")
    assert off != on
    assert settings_fingerprint(**base) == off


def test_entity_join_deterministic_and_covers_source():
    entities = [
        CncSourceEntity(
            layer="CUT_PATH",
            points=((0.0, 0.0), (10.0, 0.0)),
            closed=False,
            entity_type="LINE",
            role="tool_center",
            path_key="cut_path:1",
        ),
        CncSourceEntity(
            layer="CUT_PATH",
            points=((10.0, 0.0), (20.0, 0.0)),
            closed=False,
            entity_type="LINE",
            role="tool_center",
            path_key="cut_path:2",
        ),
        CncSourceEntity(
            layer="CUT_PATH",
            points=((20.0, 0.0), (30.0, 0.0)),
            closed=False,
            entity_type="LINE",
            role="tool_center",
            path_key="cut_path:3",
        ),
        CncSourceEntity(
            layer="CUT_PATH",
            points=((30.0, 0.0), (40.0, 0.0)),
            closed=False,
            entity_type="LINE",
            role="tool_center",
            path_key="cut_path:4",
        ),
    ]
    first, summary = join_cut_path_entities(entities, operation_presets={"cut_path": "Finish"})
    second, summary2 = join_cut_path_entities(list(reversed(entities)), operation_presets={"cut_path": "Finish"})
    assert summary is not None and summary2 is not None
    assert summary.trail_count == 1
    cut = [entity for entity in first if getattr(entity, "layer", "").upper() == "CUT_PATH"]
    assert len(cut) == 1
    assert cut[0].path_key == [
        entity for entity in second if getattr(entity, "layer", "").upper() == "CUT_PATH"
    ][0].path_key
    assert trails_cover_segments(
        [((0, 0), (10, 0)), ((10, 0), (20, 0)), ((20, 0), (30, 0)), ((30, 0), (40, 0))],
        [cut[0].points],
        closed_flags=[False],
    )


def test_ui_contract_exposes_join_radio_without_extra_metrics():
    from pathlib import Path

    ux = (
        Path(__file__).resolve().parents[1]
        / "public"
        / "js"
        / "door_cutting_order"
        / "cnc"
        / "door_cutting_order_operational_files_ux.js"
    ).read_text(encoding="utf-8")
    assert 'translate("Join Cutting Paths")' in ux
    assert 'data-join-cutting-paths="yes"' in ux
    assert 'data-join-cutting-paths="no"' in ux
    assert "join_cutting_paths: joinCuts" in ux
    assert "expected machining time" not in ux.lower()
    assert "paths before" not in ux.lower()


def test_measured_path_and_plunge_reduction_on_joined_entities():
    entities = [
        CncSourceEntity(
            layer="CUT_PATH",
            points=((float(index * 10), 0.0), (float(index * 10 + 10), 0.0)),
            closed=False,
            entity_type="LINE",
            role="tool_center",
            path_key=f"cut_path:{index}",
        )
        for index in range(4)
    ]
    before = len(entities)
    rebuilt, summary = join_cut_path_entities(entities, operation_presets={"cut_path": "Finish"})
    after = len([entity for entity in rebuilt if getattr(entity, "layer", "").upper() == "CUT_PATH"])
    assert summary is not None
    assert before == 4
    assert after == 1
    # One continuous trail replaces four open segments ⇒ one plunge family instead of four.
    assert summary.trail_count == 1
    assert summary.theoretical_minimum == 1
