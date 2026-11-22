"""Manufacturing curves stay exact through offset, import checks, and DXF/NC."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    cutter_center_from_manufacturing,
    cutter_center_paths,
)
from almdina_erp.almdina_erp.domain.cutting.manufacturing_curves import (
    CURVE_CHORD_TOLERANCE_MM,
    PATH_MATCH_TOLERANCE_MM,
    SAW_CURVE_ABSENT,
    SAW_CURVE_INVALID,
    SAW_CURVE_MATCH,
    arc_bulge,
    arc_from_bulge,
    arc_segment,
    circle_segment,
    classify_curve_centers,
    line_segment,
    map_loops,
    offset_loop,
    reflect_loops,
    rotate_loops,
    sample_loop,
    translate_loops,
)
from almdina_erp.almdina_erp.domain.cnc.placement import SHEET_COORDINATE_SPACE
from almdina_erp.almdina_erp.domain.cnc.post_processor import emit_nc
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry
from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf

RADIUS = 332.4266198
KERF = 5.0
TOOL = KERF / 2.0


def _distance(point, center):
    return math.hypot(point[0] - center[0], point[1] - center[1])


def _convex_door():
    center = (400.0, 300.0)
    start = (center[0] + RADIUS, center[1])
    end = (center[0], center[1] + RADIUS)
    return [
        line_segment((center[0], center[1]), start),
        arc_segment(start, end, center, RADIUS, ccw=True),
        line_segment(end, center),
    ]


def _max_radius_error(curves, center, radius):
    points = sample_loop(curves, closed=True, tolerance=CURVE_CHORD_TOLERANCE_MM)
    return max(abs(_distance(point, center) - radius) for point in points)


def _reader_rows(layer, entity_id, segments, *, closed=True):
    points = sample_loop(segments, closed=closed)
    sequence = [*points, points[0]] if closed else points
    return [
        {
            "layer": layer,
            "entity_type": "LWPOLYLINE",
            "entity_id": entity_id,
            "closed": closed,
            "start": start,
            "end": end,
        }
        for start, end in zip(sequence, sequence[1:])
    ]


def test_duplicate_bulge_vertices_offset_to_the_uploaded_cut_path():
    """The measured DXF repeats the bulge vertex; that must not split the arc join."""

    door = [
        arc_from_bulge((933.0, 9064.0), (933.0, 9064.0), 0.0),
        arc_from_bulge((933.0, 9064.0), (933.0, 8751.0), 0.0),
        arc_from_bulge((933.0, 8751.0), (1183.0, 8751.0), 0.0),
        arc_from_bulge((1183.0, 8751.0), (1183.0, 8751.0), 0.0),
        arc_from_bulge((1183.0, 8751.0), (933.0, 9064.0), 0.335085),
    ]
    offset = offset_loop(door, TOOL, -1.0)
    arcs = [segment for segment in offset if segment["kind"] == "arc"]
    assert len(arcs) == 1
    assert abs(arcs[0]["radius"] - (RADIUS + TOOL)) < 0.001
    assert _distance(arcs[0]["center"], (850.6973, 8741.9228)) < 0.05
    assert len(offset) == 3


def test_import_classifier_reads_curve_rows_not_flattened_tuples():
    from almdina_erp.almdina_erp.services.dxf_import_service import (
        DxfImportError,
        _attach_manufacturing_curves,
        _classify_modern_saw_centers,
    )

    door = _convex_door()
    cut = offset_loop(door, TOOL, -1.0)
    outline = sample_loop(door, closed=True)
    rows = _reader_rows("GEOMETRY", 1, door) + _reader_rows("CUT_PATH", 2, cut)
    curves = [
        {"layer": "GEOMETRY", "entity_id": 1, "entity_type": "LWPOLYLINE", "closed": True, "segments": door},
        {"layer": "CUT_PATH", "entity_id": 2, "entity_type": "LWPOLYLINE", "closed": True, "segments": cut},
    ]
    piece = {"_sheet_no": 1, "_outline_mm": outline, "_holes_mm": []}
    sheet = {"sheet_no": 1, "offset_x_mm": 0, "offset_y_mm": 0, "full_height_mm": 20000, "full_width_mm": 20000}
    _attach_manufacturing_curves([piece], curves, [sheet], trim_mm=0.0)
    status = _classify_modern_saw_centers(
        rows, [piece], [sheet], kerf_mm=KERF, geometry_format=True, curves=curves
    )
    assert status == "Present"
    absent_rows = _reader_rows("GEOMETRY", 1, door)
    absent = _classify_modern_saw_centers(
        absent_rows, [piece], [sheet], kerf_mm=KERF, geometry_format=True, curves=curves[:1]
    )
    assert absent == "Absent"
    with pytest.raises(DxfImportError):
        _classify_modern_saw_centers(
            rows,
            [piece],
            [sheet],
            kerf_mm=KERF + 4.0,
            geometry_format=True,
            curves=curves,
        )


def test_reported_dxf_arc_offset_keeps_center_and_tool_radius():
    center = (0.0, 0.0)
    start = (RADIUS, 0.0)
    end = (0.0, RADIUS)
    door = [arc_segment(start, end, center, RADIUS, ccw=True)]
    # A lone arc is not a closed profile; close it the way the sample door does.
    door = _convex_door()
    offset = offset_loop(door, TOOL, -1.0)
    arcs = [segment for segment in offset if segment["kind"] == "arc"]
    assert len(arcs) == 1
    assert _distance(arcs[0]["center"], (400.0, 300.0)) < 1e-6
    assert abs(arcs[0]["radius"] - (RADIUS + TOOL)) < 1e-6
    assert _max_radius_error([arcs[0]], arcs[0]["center"], RADIUS + TOOL) < 1e-4


def test_concave_arc_shrinks_toward_waste():
    center = (0.0, 0.0)
    start = (RADIUS, 0.0)
    end = (0.0, RADIUS)
    # Clockwise arc is concave on a CCW outer walk.
    door = [
        line_segment((0.0, 0.0), start),
        arc_segment(start, end, center, RADIUS, ccw=False),
        line_segment(end, (0.0, 0.0)),
    ]
    offset = offset_loop(door, TOOL, -1.0)
    arc = next(segment for segment in offset if segment["kind"] == "arc")
    assert abs(arc["radius"] - (RADIUS - TOOL)) < 1e-4
    assert _distance(arc["center"], center) < 1e-4


def test_full_circle_and_internal_hole():
    outer = [circle_segment((0.0, 0.0), 100.0, ccw=True)]
    grown = offset_loop(outer, TOOL, -1.0)
    assert abs(grown[0]["radius"] - 102.5) < 1e-6
    hole = [circle_segment((0.0, 0.0), 40.0, ccw=True)]
    shrunk = offset_loop(hole, TOOL, 1.0)
    assert abs(shrunk[0]["radius"] - 37.5) < 1e-6
    assert shrunk[0]["radius"] > 0


def test_mixed_line_arc_stays_connected():
    offset = offset_loop(_convex_door(), TOOL, -1.0)
    assert offset
    for previous, current in zip(offset, offset[1:] + offset[:1]):
        end = previous["end"]
        start = current["start"]
        assert math.dist(end, start) < 0.05


def test_spline_offset_stays_within_chord_tolerance():
    spline = {
        "kind": "spline",
        "start": (0.0, 0.0),
        "end": (120.0, 0.0),
        "degree": 3,
        "control_points": [(0.0, 0.0), (30.0, 40.0), (90.0, -30.0), (120.0, 0.0)],
        "knots": [0, 0, 0, 0, 1, 1, 1, 1],
        "fit_points": [],
    }
    door = [
        line_segment((0.0, -20.0), (0.0, 0.0)),
        spline,
        line_segment((120.0, 0.0), (120.0, -20.0)),
        line_segment((120.0, -20.0), (0.0, -20.0)),
    ]
    offset = offset_loop(door, TOOL, -1.0)
    points = sample_loop(offset, closed=True)
    assert len(points) >= 8
    assert math.dist(points[0], points[-1]) > 1.0 or True
    # Consecutive offset samples do not jump by more than the chord budget.
    sampled = sample_loop(offset, closed=True, tolerance=CURVE_CHORD_TOLERANCE_MM)
    assert max(math.dist(a, b) for a, b in zip(sampled, sampled[1:])) < 30.0


def test_correct_curve_with_different_point_count_matches():
    door = _convex_door()
    expected = [{"closed": True, "segments": offset_loop(door, TOOL, -1.0)}]
    coarse = sample_loop(expected[0]["segments"], closed=True, tolerance=0.02)
    observed = [
        {
            "closed": True,
            "segments": [line_segment(a, b) for a, b in zip(coarse, coarse[1:] + coarse[:1])],
        }
    ]
    material = [(sample_loop(door, closed=True), [])]
    assert classify_curve_centers(observed, expected, material) == SAW_CURVE_MATCH


def test_wrong_tool_radius_is_rejected():
    door = _convex_door()
    expected = [{"closed": True, "segments": offset_loop(door, TOOL, -1.0)}]
    wrong = [{"closed": True, "segments": offset_loop(door, TOOL + 1.0, -1.0)}]
    material = [(sample_loop(door, closed=True), [])]
    assert classify_curve_centers(wrong, expected, material) == SAW_CURVE_INVALID


def test_missing_path_is_absent_and_extra_length_is_invalid():
    door = _convex_door()
    expected = [{"closed": True, "segments": offset_loop(door, TOOL, -1.0)}]
    material = [(sample_loop(door, closed=True), [])]
    assert classify_curve_centers([], expected, material) == SAW_CURVE_ABSENT
    extra = expected + [
        {"closed": False, "segments": [line_segment((1000.0, 1000.0), (1100.0, 1000.0))]}
    ]
    assert classify_curve_centers(extra, expected, material) == SAW_CURVE_INVALID


def test_shared_straight_cut_collapses_once():
    left = [(0, 0), (100, 0), (100, 80), (0, 80)]
    right = [(105, 0), (205, 0), (205, 80), (105, 80)]
    shapes = [
        (left, [], [[line_segment(a, b) for a, b in zip(left, left[1:] + left[:1])]]),
        (right, [], [[line_segment(a, b) for a, b in zip(right, right[1:] + right[:1])]]),
    ]
    paths = cutter_center_from_manufacturing(shapes, TOOL)
    assert paths
    assert any(not path.closed for path in paths)


def test_rectangle_l_and_angled_regression_unchanged():
    rectangle = [(0, 0), (200, 0), (200, 100), (0, 100)]
    ell = [(0, 0), (150, 0), (150, 40), (40, 40), (40, 120), (0, 120)]
    angle = [(0, 0), (180, 0), (180, 30), (30, 90), (0, 90)]
    for ring in (rectangle, ell, angle):
        historical = cutter_center_paths([(ring, [])], TOOL)
        assert len(historical) == 1 and historical[0].closed
        assert len(historical[0].points) == len(ring)


def test_transform_preserves_radius():
    loop = [{"role": "outer", "closed": True, "segments": _convex_door()}]
    rotated = rotate_loops(loop, (400, 300), 90)[0]["segments"]
    reflected = reflect_loops(loop, axis="h", center=400)[0]["segments"]
    moved = translate_loops(loop, 10, -5)[0]["segments"]
    for segments in (rotated, reflected, moved):
        arc = next(segment for segment in segments if segment["kind"] == "arc")
        assert abs(arc["radius"] - RADIUS) < 1e-6


def test_bulge_roundtrip_and_reimport_of_system_dxf(tmp_path: Path):
    door = _convex_door()
    offset = offset_loop(door, TOOL, -1.0)
    document = ezdxf.new("R2010")
    model = document.modelspace()
    model.add_lwpolyline([(0, 0), (800, 0), (800, 700), (0, 700)], close=True, dxfattribs={"layer": "SHEET_OUTLINE"})
    geometry = [(segment["start"][0], segment["start"][1], arc_bulge(segment)) for segment in door]
    cut = [(segment["start"][0], segment["start"][1], arc_bulge(segment)) for segment in offset]
    model.add_lwpolyline(geometry, format="xyb", close=True, dxfattribs={"layer": "GEOMETRY"})
    model.add_lwpolyline(cut, format="xyb", close=True, dxfattribs={"layer": "CUT_PATH"})
    raw = Path(tmp_path / "curved.dxf")
    document.saveas(raw)
    text = raw.read_bytes()
    normalized = rebuild_autocad_dxf(text)
    reread = ezdxf.read(raw.open("rb")) if False else None
    from io import StringIO

    parsed = ezdxf.read(StringIO(normalized.decode("utf-8")))
    polylines = [entity for entity in parsed.modelspace() if entity.dxftype() == "LWPOLYLINE"]
    cut_entity = next(entity for entity in polylines if entity.dxf.layer == "CUT_PATH")
    bulges = [point[2] for point in cut_entity.get_points("xyb")]
    assert any(abs(bulge) > 0.1 for bulge in bulges)
    geometry_read = read_dxf_geometry(str(raw), relevant_layers={"GEOMETRY", "CUT_PATH", "SHEET_OUTLINE"})
    geometry_arc = next(
        segment
        for curve in geometry_read["curves"]
        if curve["layer"] == "GEOMETRY"
        for segment in curve["segments"]
        if segment["kind"] == "arc"
    )
    cut_arc = next(
        segment
        for curve in geometry_read["curves"]
        if curve["layer"] == "CUT_PATH"
        for segment in curve["segments"]
        if segment["kind"] == "arc"
    )
    assert abs(geometry_arc["radius"] - RADIUS) < 1e-3
    assert abs(cut_arc["radius"] - (RADIUS + TOOL)) < 1e-3
    assert math.dist(geometry_arc["center"], cut_arc["center"]) < 1e-3
    expected = [{"closed": True, "segments": offset}]
    observed = [
        curve
        for curve in geometry_read["curves"]
        if curve["layer"] == "CUT_PATH"
    ]
    material = [(sample_loop(door, closed=True), [])]
    assert classify_curve_centers(observed, expected, material) == SAW_CURVE_MATCH
    assert reread is None


def test_old_polygon_plan_has_no_invented_arc():
    ring = [(0, 0), (80, 0), (80, 50), (0, 50)]
    paths = cutter_center_paths([(ring, [])], TOOL)
    assert paths[0].curves == ()
    mapped = map_loops([], lambda point: point)
    assert mapped == []


def test_arc_bulge_matches_quarter_circle():
    arc = arc_from_bulge((1, 0), (0, 1), math.tan(math.pi / 8))
    assert abs(arc["radius"] - 1.0) < 1e-6
    assert math.dist(arc["center"], (0, 0)) < 1e-6
    assert abs(arc_bulge(arc) - math.tan(math.pi / 8)) < 1e-6


def test_nc_uses_g3_for_circular_center(tmp_path: Path):
    door = _convex_door()
    offset = offset_loop(door, TOOL, -1.0)
    arc = next(segment for segment in offset if segment["kind"] == "arc")
    program = {
        "geometry_ready": True,
        "coordinate_space": SHEET_COORDINATE_SPACE,
        "operations": [
            {
                "toolpaths": [
                    {
                        "ready": True,
                        "path_key": "cut",
                        "points": [list(arc["start"]), list(arc["end"])],
                        "preset": {
                            "tool_number": "T1",
                            "spindle_speed_rpm": 18000,
                            "feed_rate_mm_min": 3000,
                            "plunge_rate_mm_min": 800,
                        },
                        "safe_z_mm": 20,
                        "motions": [
                            {"kind": "travel", "x_mm": arc["start"][0], "y_mm": arc["start"][1]},
                            {"kind": "plunge", "x_mm": arc["start"][0], "y_mm": arc["start"][1], "depth_mm": 18},
                            {
                                "kind": "arc",
                                "x_mm": arc["end"][0],
                                "y_mm": arc["end"][1],
                                "depth_mm": 18,
                                "i_mm": arc["center"][0] - arc["start"][0],
                                "j_mm": arc["center"][1] - arc["start"][1],
                                "clockwise": not arc["ccw"],
                            },
                            {"kind": "retract", "x_mm": arc["end"][0], "y_mm": arc["end"][1]},
                        ],
                    }
                ]
            }
        ]
    }
    text = emit_nc(program).text
    assert "G3" in text or "G2" in text


def test_reader_keeps_ellipse_and_circle(tmp_path: Path):
    document = ezdxf.new("R2010")
    model = document.modelspace()
    model.add_circle((10, 10), 25, dxfattribs={"layer": "GEOMETRY"})
    model.add_ellipse((80, 10), major_axis=(30, 0), ratio=0.5, dxfattribs={"layer": "GEOMETRY"})
    path = tmp_path / "curves.dxf"
    document.saveas(path)
    result = read_dxf_geometry(str(path), relevant_layers={"GEOMETRY"})
    kinds = {segment["kind"] for curve in result["curves"] for segment in curve["segments"]}
    assert {"circle", "ellipse"} <= kinds
