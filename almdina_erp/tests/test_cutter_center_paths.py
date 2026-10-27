"""Saw-center geometry and the new GEOMETRY / CUT_PATH DXF contract."""

from __future__ import annotations

import io
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    classify_saw_center_segments,
    cutter_center_paths,
    cutter_center_segments,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import LinerPiece, liner_toolpath_mm, piece_polygon_mm
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path("/Users/macbook/Downloads/147.dxf")


def _rect(x, y, width, height):
    return ((x, y), (x + width, y), (x + width, y + height), (x, y + height))


def _midpoint(segment):
    start, end = segment
    return ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)


def _distance_to_ring(point, ring):
    best = math.inf
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_sq = dx * dx + dy * dy or 1.0
        along = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
        along = min(1.0, max(0.0, along))
        nearest = (start[0] + along * dx, start[1] + along * dy)
        best = min(best, math.dist(point, nearest))
    return best


def _material(point, shapes):
    for outer, holes in shapes:
        if not point_in_polygon(point, outer):
            continue
        if any(point_in_polygon(point, hole) for hole in holes):
            continue
        return True
    return False


def _assert_centers_follow_radius(shapes, radius):
    centers = cutter_center_segments(shapes, radius)
    assert centers
    for segment in centers:
        point = _midpoint(segment)
        assert _material(point, shapes) is False
        rings = [outer for outer, _holes in shapes]
        rings.extend(hole for _outer, holes in shapes for hole in holes)
        clearance = min(_distance_to_ring(point, ring) for ring in rings)
        # A corner junction sits R√2 from the finished corner. The disk must
        # still reach the finished edge and must not cross into the door.
        assert clearance + 1e-6 >= radius - 0.05
    return centers


def _on_line(segment, *, axis, value):
    start, end = segment
    if axis == "x":
        return abs(start[0] - value) < 0.02 and abs(end[0] - value) < 0.02
    return abs(start[1] - value) < 0.02 and abs(end[1] - value) < 0.02


def _layer_segments(document, layer):
    segments = []
    for entity in document.modelspace():
        if entity.dxf.layer != layer:
            continue
        if entity.dxftype() == "LINE":
            segments.append(
                (
                    (entity.dxf.start.x, entity.dxf.start.y),
                    (entity.dxf.end.x, entity.dxf.end.y),
                )
            )
            continue
        if entity.dxftype() == "LWPOLYLINE":
            points = [tuple(point[:2]) for point in entity.get_points("xy")]
        elif entity.dxftype() == "POLYLINE":
            points = [(vertex.dxf.location.x, vertex.dxf.location.y) for vertex in entity.vertices]
        else:
            continue
        segments.extend(zip(points, points[1:]))
        if entity.is_closed and len(points) >= 3:
            segments.append((points[-1], points[0]))
    return segments


def test_one_door_center_is_radius_outside_not_on_the_finished_edge():
    door = _rect(10, 10, 200, 538)
    centers = _assert_centers_follow_radius([(door, ())], 2.5)
    assert any(_on_line(segment, axis="x", value=7.5) for segment in centers)
    assert not any(_on_line(segment, axis="x", value=10) for segment in centers)
    assert not any(_on_line(segment, axis="x", value=5) for segment in centers)


@pytest.mark.parametrize("kerf", [3, 4, 5])
@pytest.mark.parametrize("width", [1220, 1218, 1215])
def test_full_perimeter_keeps_dynamic_offset_at_physical_sheet_edges(kerf, width):
    radius = kerf / 2
    x = (1220 - width) / 2
    ring = _rect(x, 0, width, 2440)
    paths = cutter_center_paths([(ring, ())], radius, board=(0, 0, 1220, 2440))
    assert len(paths) == 1 and paths[0].closed
    for actual, expected in zip(paths[0].points, _rect(x - radius, -radius, width + kerf, 2440 + kerf)):
        assert actual == pytest.approx(expected, abs=1e-9)
    assert ring == _rect(x, 0, width, 2440)


def test_exported_shared_paths_are_not_repeated():
    shapes = [(_rect(0, 0, 200, 500), ()), (_rect(205, 100, 200, 400), ())]
    paths = cutter_center_paths(shapes, 2.5, board=(0, 0, 1220, 2440))
    observed = []
    for path in paths:
        observed.extend(zip(path.points, path.points[1:]))
        if path.closed:
            observed.append((path.points[-1], path.points[0]))
    expected = cutter_center_segments(shapes, 2.5)
    assert sum(math.dist(*segment) for segment in observed) == pytest.approx(
        sum(math.dist(*segment) for segment in expected), abs=0.05,
    )


def test_python_javascript_full_perimeter_parity_and_round_trip(tmp_path):
    """Compare actual browser DXF with Python, including every finished edge."""
    cases = []

    def add_case(kerf, entries):
        pieces, shapes, rows = [], [], []
        for index, (outer, holes, fields) in enumerate(entries, start=1):
            xs, ys = [p[0] for p in outer], [p[1] for p in outer]
            width, height = (max(xs) - min(xs)) / 10, (max(ys) - min(ys)) / 10
            row = _piece(
                piece_instance_id=f"door-{index}", width_cm=width, length_cm=height,
                cut_width_cm=width, cut_length_cm=height, **fields,
            )
            rows.append(row)
            pieces.append(dict(
                vars(row), id=index, label=f"{index}.1", x=min(xs) / 10, y=min(ys) / 10,
                w=width, h=height, geometry=dict(
                    schema_version=1, unit="mm", coordinate_space="usable_sheet",
                    outer=outer, holes=holes,
                ),
            ))
            shapes.append((
                [(x, 2440 - y) for x, y in outer],
                [[(x, 2440 - y) for x, y in hole] for hole in holes],
            ))
        plan = dict(
            full_board_width_cm=122, full_board_length_cm=244,
            usable_board_width_cm=122, usable_board_length_cm=244,
            kerf_mm=kerf, trim_cm=0,
            sheets=[dict(sheet_no=1, full_width_cm=122, full_length_cm=244, pieces=pieces)],
        )
        cases.append((plan, shapes, _order(rows)))

    for kerf in (3, 4, 5):
        for width in (1220, 1218, 1215):
            add_case(kerf, [(_rect((1220 - width) / 2, 0, width, 2440), (), {})])
        for x, y in ((0, 0), (820, 0), (0, 1940), (820, 1940)):
            add_case(kerf, [(_rect(x, y, 400, 500), (), {})])
        add_case(kerf, [
            (_rect(0, 0, 200, 500), (), {}),
            (_rect(200 + kerf, 100, 200, 400), (), {}),
        ])
        add_case(kerf, [
            (_rect(column * (200 + kerf), row * (300 + kerf), 200, 300), (), {})
            for row in range(2) for column in range(2)
        ])
        add_case(kerf, [
            (_rect(0, 0, 1000, 1000), (_rect(200, 200, 600, 600),),
             dict(piece_type="Glass", glass_margin_mm=200)),
            (_rect(300, 300, 200, 200), (), {}),
        ])
        for piece_type in ("L-Shaped Corner", "Clipped Corner"):
            for position in ("Top Right", "Top Left", "Bottom Right", "Bottom Left"):
                ring = piece_polygon_mm(LinerPiece(piece_type, 40, 50, position, 10, 15))
                add_case(kerf, [(ring, (), dict(
                    piece_type=piece_type, clipped_corner_position=position,
                    clipped_corner_width_cm=10, clipped_corner_length_cm=15,
                ))])
        add_case(kerf, [(tuple(reversed(_rect(0, 0, 400, 500))), (), {})])

    source = tmp_path / "cases.json"
    source.write_text(json.dumps([case[0] for case in cases]))
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True, capture_output=True, text=True,
        env=dict(os.environ, PERIMETER_CASES=str(source), PERIMETER_OUTPUT_DIR=str(tmp_path)),
    )
    for index, (plan, shapes, order) in enumerate(cases):
        path = tmp_path / f"{index}.dxf"
        document = ezdxf.readfile(str(path))
        observed = _layer_segments(document, "CUT_PATH")
        expected = cutter_center_segments(shapes, plan["kerf_mm"] / 2, board=(0, 0, 1220, 2440))
        assert classify_saw_center_segments(observed, expected) == "match", index
        assert sum(math.dist(*edge) for edge in observed) == pytest.approx(
            sum(math.dist(*edge) for edge in expected), abs=0.05,
        ), index
        # Finished material, including hole boundaries, must be unchanged.
        finished = [
            (ring[i], ring[(i + 1) % len(ring)])
            for outer, holes in shapes for ring in [outer, *holes] for i in range(len(ring))
        ]
        assert classify_saw_center_segments(_layer_segments(document, "GEOMETRY"), finished) == "match", index
        normalized = rebuild_autocad_dxf(path.read_bytes())
        path.write_bytes(normalized)
        snapshot = _import(str(path), order, kerf_mm=plan["kerf_mm"], trim_mm=0)
        assert snapshot["saw_center_status"] == "Present", index
        assert len(snapshot["sheets"][0]["pieces"]) == len(order.pieces), index


def test_two_adjacent_doors_share_one_center_and_keep_a_real_gap():
    radius = 2.5
    shapes = [(_rect(0, 0, 200, 500), ()), (_rect(205, 0, 200, 500), ())]
    centers = _assert_centers_follow_radius(shapes, radius)
    shared = [segment for segment in centers if _on_line(segment, axis="x", value=202.5)]
    assert len(shared) == 1
    assert abs(math.dist(*shared[0]) - 505) < 0.05
    separated = [(_rect(0, 0, 200, 500), ()), (_rect(206, 0, 200, 500), ())]
    apart = cutter_center_segments(separated, radius)
    assert len([segment for segment in apart if _on_line(segment, axis="x", value=202.5)]) == 1
    assert len([segment for segment in apart if _on_line(segment, axis="x", value=203.5)]) == 1


def test_multi_offset_paths_merge_shared_centers_without_losing_edges():
    shapes = [(_rect(10, 10, 200, 500), ()), (_rect(215, 10, 200, 500), ())]
    paths = cutter_center_paths(shapes, 2.5, board=(0, 0, 1220, 2440))
    assert len(paths) == 5
    assert all(not path.closed for path in paths)
    observed = [tuple(path.points) for path in paths]
    assert len([segment for segment in observed if _on_line(segment, axis="x", value=212.5)]) == 1
    assert classify_saw_center_segments(observed, cutter_center_segments(shapes, 2.5)) == "match"


def test_physical_board_edges_keep_the_full_closed_offset():
    shapes = [(_rect(0, 0, 400, 500), ())]
    paths = cutter_center_paths(shapes, 2.5, board=(0, 0, 1220, 2440))
    assert len(paths) == 1 and paths[0].closed
    assert paths == cutter_center_paths(shapes, 2.5)


def test_partial_overlap_keeps_the_union_and_a_gap_stays_open():
    shapes = [(_rect(0, 0, 200, 500), ()), (_rect(205, 100, 200, 400), ())]
    centers = _assert_centers_follow_radius(shapes, 2.5)
    shared = [segment for segment in centers if _on_line(segment, axis="x", value=202.5)]
    assert len(shared) == 1
    assert abs(math.dist(*shared[0]) - 505) < 0.05

    gapped = [(_rect(0, 0, 100, 100), ()), (_rect(110, 0, 100, 100), ())]
    tops = [
        segment for segment in cutter_center_segments(gapped, 2.5)
        if _on_line(segment, axis="y", value=102.5)
    ]
    assert len(tops) == 2


def test_row_and_grid_do_not_repeat_shared_cuts_or_cross_material():
    row = [(_rect(index * 105, 0, 100, 80), ()) for index in range(4)]
    centers = _assert_centers_follow_radius(row, 2.5)
    for index in range(3):
        shared_x = 100 + index * 105 + 2.5
        assert len([segment for segment in centers if _on_line(segment, axis="x", value=shared_x)]) == 1

    grid = []
    for row_index in range(2):
        for column in range(2):
            grid.append((_rect(column * 105, row_index * 105, 100, 100), ()))
    centers = _assert_centers_follow_radius(grid, 2.5)
    assert len([segment for segment in centers if _on_line(segment, axis="x", value=102.5)]) == 1
    assert len([segment for segment in centers if _on_line(segment, axis="y", value=102.5)]) == 1


def test_trim_offset_follows_the_door_on_one_side_and_zero_trim_leaves_the_sheet():
    centers = cutter_center_segments([(_rect(10, 0, 200, 400), ())], 2.5)
    assert any(_on_line(segment, axis="x", value=7.5) for segment in centers)
    assert any(_on_line(segment, axis="y", value=-2.5) for segment in centers)
    flush = cutter_center_segments([(_rect(0, 0, 200, 400), ())], 0)
    assert any(_on_line(segment, axis="x", value=0) for segment in flush)


def test_a_finished_edge_on_the_physical_board_is_still_cut():
    board = (0.0, 0.0, 1220.0, 2440.0)
    assert len(cutter_center_segments([(_rect(0, 0, 1220, 2440), ())], 2.5, board=board)) == 4

    one_side = cutter_center_segments([(_rect(0, 0, 400, 500), ())], 2.5, board=board)
    assert any(_on_line(segment, axis="x", value=-2.5) for segment in one_side)
    assert any(_on_line(segment, axis="y", value=-2.5) for segment in one_side)
    assert any(_on_line(segment, axis="x", value=402.5) for segment in one_side)
    assert any(_on_line(segment, axis="y", value=502.5) for segment in one_side)

    trimmed = cutter_center_segments([(_rect(10, 10, 1200, 2420), ())], 2.5, board=board)
    assert any(_on_line(segment, axis="x", value=7.5) for segment in trimmed)
    assert any(_on_line(segment, axis="y", value=7.5) for segment in trimmed)

    shared = cutter_center_segments(
        [(_rect(0, 0, 400, 500), ()), (_rect(405, 0, 400, 500), ())],
        2.5,
        board=board,
    )
    assert len([segment for segment in shared if _on_line(segment, axis="x", value=402.5)]) == 1
    assert any(_on_line(segment, axis="x", value=-2.5) for segment in shared)


def test_hole_clipped_and_l_contours_offset_from_the_real_ring():
    outer = _rect(0, 0, 100, 100)
    hole = _rect(20, 20, 60, 60)
    nested = _rect(30, 30, 20, 20)
    nested_shapes = [(outer, (hole,)), (nested, ())]
    _assert_centers_follow_radius(nested_shapes, 2.5)
    nested_paths = cutter_center_paths(nested_shapes, 2.5)
    assert len(nested_paths) == 3
    assert all(path.closed for path in nested_paths)

    for position in ("Top Right", "Top Left", "Bottom Right", "Bottom Left"):
        clipped = piece_polygon_mm(LinerPiece("Clipped Corner", 84, 63, position, 54, 23))
        shaped = piece_polygon_mm(LinerPiece("L-Shaped Corner", 40, 40, position, 20.1, 30.1))
        _assert_centers_follow_radius([(clipped, ())], 1.5)
        _assert_centers_follow_radius([(shaped, ())], 1.5)
        clipped_path = cutter_center_paths([(clipped, ())], 1.5)
        shaped_path = cutter_center_paths([(shaped, ())], 1.5)
        assert len(clipped_path) == 1 and clipped_path[0].closed
        assert len(clipped_path[0].points) == 5
        assert len(shaped_path) == 1 and shaped_path[0].closed
        assert len(shaped_path[0].points) == 6

    raw_notch = ((0, 0), (199, 0), (199, 301), (400, 301), (400, 400), (0, 400))
    _assert_centers_follow_radius([(raw_notch, ())], 1.5)


def test_full_liner_meets_the_saw_center_and_a_partial_liner_stops_inside():
    piece = LinerPiece("Regular", 20, 50)
    full = liner_toolpath_mm(piece, "edge_long_left", 2, 1.8, 5, 0, 0)
    ys = [point[1] for point in full]
    assert min(ys) == pytest.approx(-2.5, abs=0.05)
    assert max(ys) == pytest.approx(502.5, abs=0.05)
    partial = liner_toolpath_mm(piece, "edge_long_left", 2, 1.8, 5, 0, 20)
    partial_ys = [point[1] for point in partial]
    assert max(partial_ys) < 250
    assert min(partial_ys) == pytest.approx(-2.5, abs=0.05)


def _settings(kerf_mm, trim_mm):
    return normalize_plan_settings(
        optimization_mode=DEFAULT_OPTIMIZATION_MODE_ID,
        machine_type=DEFAULT_MACHINE_TYPE,
        optimization_time_limit_sec=DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        kerf_mm=kerf_mm,
        preferred_trim_mm=trim_mm,
    )


def _piece(**kwargs):
    base = dict(
        qty=1,
        allow_rotation=0,
        extra_liner=0,
        extra_back_groove=0,
        extra_full_door_double=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        liner_reference_side="",
        liner_offset_cm=0,
        liner_width_cm=0,
        liner_start_cm=0,
        liner_length_cm=0,
        edge_long_right=0,
        edge_long_left=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_break=0,
        piece_type="Regular",
        piece_instance_id="piece",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _order(pieces):
    return SimpleNamespace(
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        default_edge_type="",
        pieces=pieces,
    )


def _write(document) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    document.saveas(handle.name)
    return handle.name


def _sheet(document):
    modelspace = document.modelspace()
    outline = _rect(0, 0, 1220, 2440)
    for start, end in zip(outline, (*outline[1:], outline[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "SHEET_OUTLINE"})
    return modelspace


def _import(path, order, *, kerf_mm, trim_mm):
    with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
        return parse_production_dxf(path, order, settings=_settings(kerf_mm, trim_mm))


def test_new_geometry_layer_wins_and_legacy_cut_path_still_imports():
    finished = _rect(5, 5, 500, 500)
    center = _rect(2.5, 2.5, 505, 505)
    document = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "CUT_PATH", "GEOMETRY", "TEXT"):
        document.layers.add(name)
    modelspace = _sheet(document)
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "GEOMETRY"})
    for start, end in zip(center, (*center[1:], center[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_lwpolyline(_rect(40, 40, 80, 80), dxfattribs={"layer": "GEOMETRY"}, close=True)
    modelspace.add_lwpolyline(_rect(700, 700, 100, 100), dxfattribs={"layer": "0"}, close=True)
    modelspace.add_text("1", dxfattribs={"layer": "TEXT", "insert": (250, 250), "height": 12})
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=50, length_cm=50, cut_width_cm=50, cut_length_cm=50),
    ])
    piece = _import(_write(document), order, kerf_mm=5, trim_mm=5)["sheets"][0]["pieces"][0]
    assert piece["w"] == 50
    assert piece["h"] == 50

    legacy = ezdxf.new("R2010")
    for name in ("SHEET_OUTLINE", "CUT_PATH", "text"):
        legacy.layers.add(name)
    modelspace = _sheet(legacy)
    for start, end in zip(finished, (*finished[1:], finished[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_text("1", dxfattribs={"layer": "text", "insert": (250, 250), "height": 12})
    piece = _import(_write(legacy), order, kerf_mm=5, trim_mm=5)["sheets"][0]["pieces"][0]
    assert piece["w"] == 50
    assert piece["h"] == 50


def test_exported_dxf_round_trip_matches_the_reference_offset(tmp_path):
    client_path = tmp_path / "saw-center-client.dxf"
    env = os.environ.copy()
    env["SAW_CENTER_DXF_OUT"] = str(client_path)
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True,
        env=env,
    )
    source = ezdxf.readfile(str(client_path))
    layers = {entity.dxf.layer for entity in source.modelspace()}
    assert {"CUT_PATH", "GEOMETRY", "Liner", "SHEET_OUTLINE", "TEXT"} <= layers
    assert "0" not in layers
    geometry_lines = [
        entity for entity in source.modelspace()
        if entity.dxftype() == "LINE" and entity.dxf.layer == "GEOMETRY"
    ]
    center_paths = [
        entity for entity in source.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "CUT_PATH"
    ]
    region_polylines = [
        entity for entity in source.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "GEOMETRY"
    ]
    liner = next(
        entity for entity in source.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "Liner"
    )
    assert geometry_lines
    assert center_paths == []
    assert [
        entity for entity in source.modelspace()
        if entity.dxftype() == "LINE" and entity.dxf.layer == "CUT_PATH"
    ]
    assert region_polylines and all(entity.closed for entity in region_polylines)
    assert liner.closed is False
    shared = [
        segment for segment in _layer_segments(source, "CUT_PATH")
        if _on_line(segment, axis="x", value=212.5)
    ]
    assert len(shared) == 1

    normalized = rebuild_autocad_dxf(client_path.read_bytes())
    audited = ezdxf.read(io.StringIO(normalized.decode("utf-8")))
    assert audited.audit().has_errors is False
    assert audited.dxfversion == "AC1024"
    normalized_path = tmp_path / "saw-center-normalized.dxf"
    normalized_path.write_bytes(normalized)
    order = _order([
        _piece(
            piece_instance_id="door-1",
            width_cm=20,
            length_cm=50,
            cut_width_cm=20,
            cut_length_cm=50,
            extra_liner=1,
            liner_reference_side="edge_long_left",
            liner_offset_cm=2,
            liner_width_cm=1.8,
        ),
        _piece(
            piece_instance_id="door-2",
            width_cm=30,
            length_cm=40,
            cut_width_cm=30,
            cut_length_cm=40,
        ),
    ])
    pieces = _import(str(normalized_path), order, kerf_mm=5, trim_mm=10)["sheets"][0]["pieces"]
    sizes = sorted((piece["w"], piece["h"]) for piece in pieces)
    assert sizes == [(20, 50), (30, 40)]
    assert sum(1 for piece in pieces if piece.get("overlays")) == 1


def _vertical_spans(points):
    spans = []
    run = [points[0]]
    for previous, point in zip(points, points[1:]):
        if abs(point[0] - previous[0]) <= 0.05:
            run.append(point)
            continue
        if len(run) >= 2:
            spans.append(abs(run[-1][1] - run[0][1]))
        run = [point]
    if len(run) >= 2:
        spans.append(abs(run[-1][1] - run[0][1]))
    return spans


def test_full_board_door_has_a_closed_perimeter_and_unchanged_liner(tmp_path):
    client_path = tmp_path / "full-board-liner.dxf"
    env = os.environ.copy()
    env["FULL_BOARD_DXF_OUT"] = str(client_path)
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True,
        env=env,
    )
    source = ezdxf.readfile(str(client_path))
    modelspace = source.modelspace()
    cuts = [entity for entity in modelspace if entity.dxf.layer == "CUT_PATH"]
    assert len(cuts) == 1 and cuts[0].closed
    assert len(_layer_segments(source, "CUT_PATH")) == 4
    geometry = [
        entity for entity in modelspace
        if entity.dxftype() == "LINE" and entity.dxf.layer == "GEOMETRY"
    ]
    outline = [
        entity for entity in modelspace
        if entity.dxftype() == "LINE" and entity.dxf.layer == "SHEET_OUTLINE"
    ]
    assert geometry and outline
    liner_entities = [
        entity for entity in modelspace
        if entity.dxf.layer == "Liner"
    ]
    assert len(liner_entities) == 1
    liner = liner_entities[0]
    assert liner.dxftype() == "LWPOLYLINE"
    assert liner.closed is False
    points = [tuple(point[:2]) for point in liner.get_points("xy")]
    xs = [point[0] for point in points]
    assert min(xs) == pytest.approx(-2.5, abs=0.05)
    assert max(xs) == pytest.approx(1222.5, abs=0.05)
    assert sorted(span for span in _vertical_spans(points) if span > 10) == pytest.approx([13, 13], abs=0.05)

    normalized = rebuild_autocad_dxf(client_path.read_bytes())
    audited = ezdxf.read(io.StringIO(normalized.decode("utf-8")))
    assert audited.audit().has_errors is False
    normalized_path = tmp_path / "full-board-liner-normalized.dxf"
    normalized_path.write_bytes(normalized)
    order = _order([
        _piece(
            piece_instance_id="door-1",
            width_cm=122,
            length_cm=244,
            cut_width_cm=122,
            cut_length_cm=244,
            extra_liner=1,
            liner_reference_side="edge_width_top",
            liner_offset_cm=0,
            liner_width_cm=1.8,
        ),
    ])
    pieces = _import(str(normalized_path), order, kerf_mm=5, trim_mm=0)["sheets"][0]["pieces"]
    assert [(piece["w"], piece["h"]) for piece in pieces] == [(122, 244)]
    assert sum(1 for piece in pieces if piece.get("overlays")) == 1


def test_split_trim_exports_saw_centers_and_reimports(tmp_path):
    client_path = tmp_path / "trim-gaps.dxf"
    env = os.environ.copy()
    env["TRIM_GAPS_DXF_OUT"] = str(client_path)
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True,
        env=env,
    )
    source = ezdxf.readfile(str(client_path))
    cuts = _layer_segments(source, "CUT_PATH")

    def vertical(value):
        return [
            segment for segment in cuts
            if _on_line(segment, axis="x", value=value)
        ]

    def horizontal(value):
        return [
            segment for segment in cuts
            if _on_line(segment, axis="y", value=value)
        ]

    assert len(vertical(2.5)) == 1
    assert len(vertical(407.5)) == 1
    assert len(vertical(812.5)) == 1
    assert len(vertical(1217.5)) == 1
    assert len(horizontal(2.5)) == 1
    assert vertical(0) == []
    assert vertical(1220) == []
    geometry = [
        entity for entity in source.modelspace()
        if entity.dxftype() == "LINE" and entity.dxf.layer == "GEOMETRY"
    ]
    rights = sorted(
        max(entity.dxf.start.x, entity.dxf.end.x)
        for entity in geometry
        if abs(entity.dxf.start.x - entity.dxf.end.x) < 0.05
    )
    assert rights[-1] == pytest.approx(1215, abs=0.05)
    assert min(
        min(entity.dxf.start.x, entity.dxf.end.x) for entity in geometry
    ) == pytest.approx(5, abs=0.05)

    normalized = rebuild_autocad_dxf(client_path.read_bytes())
    audited = ezdxf.read(io.StringIO(normalized.decode("utf-8")))
    assert audited.audit().has_errors is False
    normalized_path = tmp_path / "trim-gaps-normalized.dxf"
    normalized_path.write_bytes(normalized)
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=40, length_cm=40, cut_width_cm=40, cut_length_cm=40),
        _piece(piece_instance_id="door-2", width_cm=40, length_cm=40, cut_width_cm=40, cut_length_cm=40),
        _piece(piece_instance_id="door-3", width_cm=40, length_cm=40, cut_width_cm=40, cut_length_cm=40),
    ])
    imported = _import(str(normalized_path), order, kerf_mm=5, trim_mm=5)
    sizes = sorted((piece["w"], piece["h"]) for piece in imported["sheets"][0]["pieces"])
    assert sizes == [(40, 40), (40, 40), (40, 40)]


def test_three_millimetre_kerf_trim_exports_and_reimports(tmp_path):
    client_path = tmp_path / "kerf3-trim.dxf"
    env = os.environ.copy()
    env["KERF3_DXF_OUT"] = str(client_path)
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True,
        env=env,
    )
    source = ezdxf.readfile(str(client_path))
    cuts = _layer_segments(source, "CUT_PATH")

    def vertical(value):
        return [
            segment for segment in cuts
            if _on_line(segment, axis="x", value=value)
        ]

    def horizontal(value):
        return [
            segment for segment in cuts
            if _on_line(segment, axis="y", value=value)
        ]

    assert len(vertical(3.5)) == 1
    assert len(vertical(406.5)) == 1
    assert len(vertical(809.5)) == 1
    assert len(vertical(1212.5)) == 1
    assert len(horizontal(3.5)) == 1
    assert vertical(0) == []
    assert vertical(1220) == []
    geometry = [
        entity for entity in source.modelspace()
        if entity.dxftype() == "LINE" and entity.dxf.layer == "GEOMETRY"
    ]
    xs = [
        value
        for entity in geometry
        for value in (entity.dxf.start.x, entity.dxf.end.x)
    ]
    assert min(xs) == pytest.approx(5, abs=0.05)
    assert max(xs) == pytest.approx(1211, abs=0.05)

    normalized = rebuild_autocad_dxf(client_path.read_bytes())
    audited = ezdxf.read(io.StringIO(normalized.decode("utf-8")))
    assert audited.audit().has_errors is False
    normalized_path = tmp_path / "kerf3-trim-normalized.dxf"
    normalized_path.write_bytes(normalized)
    order = _order([
        _piece(piece_instance_id="door-1", width_cm=40, length_cm=40, cut_width_cm=40, cut_length_cm=40),
        _piece(piece_instance_id="door-2", width_cm=40, length_cm=40, cut_width_cm=40, cut_length_cm=40),
        _piece(piece_instance_id="door-3", width_cm=40, length_cm=40, cut_width_cm=40, cut_length_cm=40),
    ])
    imported = _import(str(normalized_path), order, kerf_mm=3, trim_mm=5)
    sizes = sorted((piece["w"], piece["h"]) for piece in imported["sheets"][0]["pieces"])
    assert sizes == [(40, 40), (40, 40), (40, 40)]


def test_reference_file_uses_the_same_radius_offset():
    if not REFERENCE.is_file():
        pytest.skip("reference 147.dxf is not on this machine")
    document = ezdxf.readfile(str(REFERENCE))
    finished = [
        [tuple(point[:2]) for point in entity.get_points("xy")]
        for entity in document.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "CUT_PATH" and entity.closed
    ]
    centers = [
        [tuple(point[:2]) for point in entity.get_points("xy")]
        for entity in document.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "0" and entity.closed
    ]
    boxes = []
    for ring in finished:
        xs = [point[0] for point in ring]
        ys = [point[1] for point in ring]
        boxes.append((min(xs), min(ys), max(xs), max(ys)))
    boxes.sort()
    gaps = []
    for left, right in zip(boxes, boxes[1:]):
        if abs(left[1] - right[1]) < 0.1 and abs(left[3] - right[3]) < 0.1:
            gaps.append(right[0] - left[2])
    assert gaps
    assert min(gaps) == pytest.approx(5, abs=0.05)
    door = next(box for box in boxes if abs(box[0] - 10) < 0.1)
    center_boxes = []
    for ring in centers:
        xs = [point[0] for point in ring]
        ys = [point[1] for point in ring]
        center_boxes.append((min(xs), min(ys), max(xs), max(ys)))
    match = next(
        box for box in center_boxes
        if abs((box[0] + box[2]) / 2 - (door[0] + door[2]) / 2) < 1
        and abs((box[1] + box[3]) / 2 - (door[1] + door[3]) / 2) < 1
        and (box[2] - box[0]) > (door[2] - door[0])
    )
    assert match[0] == pytest.approx(door[0] - 2.5, abs=0.05)
    assert match[0] != pytest.approx(5, abs=0.2)
