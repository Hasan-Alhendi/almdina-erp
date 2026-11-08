"""Shorten a machining centerline only far enough to keep the cutter body out of the next door."""

import math

import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import GEOMETRY_TOLERANCE_MM
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    compare_liner_path,
    compare_liner_set_paths,
    extension_conflict,
    liner_toolpath_mm,
    merged_liner_toolpaths_mm,
    obstacles_in_toolpath_frame,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import generate_toolpath


def _regular() -> LinerPiece:
    return LinerPiece("Regular", 40, 60)


def _box(min_x: float, min_y: float, max_x: float, max_y: float) -> dict:
    return {"polygon": [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]}


def _right_neighbor(gap: float) -> list[dict]:
    edge = 400.0 + gap
    return [_box(edge, -80.0, edge + 400.0, 200.0)]


def _ends(path):
    return min(path, key=lambda point: point[0]), max(path, key=lambda point: point[0])


def _boundary_gap(point, polygon) -> float:
    best = math.inf
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_sq = dx * dx + dy * dy or 1.0
        ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
        ratio = min(1.0, max(0.0, ratio))
        nearest = (start[0] + dx * ratio, start[1] + dy * ratio)
        best = min(best, math.dist(point, nearest))
    return best


def _body_clears(path, diameter: float, obstacles) -> bool:
    """The cutter disk around every centerline sample stays out of neighbor material."""

    radius = diameter / 2.0
    for index in range(len(path) - 1):
        start, end = path[index], path[index + 1]
        length = math.dist(start, end)
        if length <= 1e-9:
            continue
        steps = max(1, int(length))
        for step in range(steps + 1):
            ratio = step / steps
            center = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            for angle in range(12):
                theta = angle * math.tau / 12.0
                body = (
                    center[0] + math.cos(theta) * radius,
                    center[1] + math.sin(theta) * radius,
                )
                for obstacle in obstacles:
                    outer = obstacle["polygon"]
                    holes = obstacle.get("holes") or ()
                    if not point_in_polygon(body, outer):
                        continue
                    if any(point_in_polygon(body, hole) for hole in holes):
                        continue
                    # Tangent contact is the historical full-radius extension.
                    # Only material strictly inside the neighbor is an intrusion.
                    if _boundary_gap(body, outer) > 1e-4:
                        return False
    return True


def test_equal_gap_and_bit_keep_the_historical_extension():
    piece = _regular()
    obstacles = _right_neighbor(5)
    bare = liner_toolpath_mm(piece, "edge_width_top", 0, 0.5, 5)
    safe = liner_toolpath_mm(piece, "edge_width_top", 0, 0.5, 5, obstacles=obstacles)
    assert safe == bare
    assert extension_conflict(safe, 5, None, obstacles) == ""
    assert _body_clears(safe, 5, obstacles)


def test_wider_bit_shortens_only_the_obstructed_end():
    piece = _regular()
    obstacles = _right_neighbor(5)
    bare = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8)
    safe = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=obstacles)
    bare_left, bare_right = _ends(bare)
    safe_left, safe_right = _ends(safe)
    assert safe_left == pytest.approx(bare_left)
    assert safe_right[0] == pytest.approx(400.0 + (5.0 - 4.0 - GEOMETRY_TOLERANCE_MM))
    assert safe_right[0] < bare_right[0]
    assert extension_conflict(bare, 8, None, obstacles) == "liner_extension_hits_piece"
    assert extension_conflict(safe, 8, None, obstacles) == ""
    assert _body_clears(safe, 8, obstacles)


def test_bit_larger_than_the_gap_may_stop_inside_the_target_edge():
    piece = _regular()
    obstacles = _right_neighbor(5)
    safe = liner_toolpath_mm(piece, "edge_width_top", 0, 1.0, 10, obstacles=obstacles)
    _left, right = _ends(safe)
    assert right[0] == pytest.approx(400.0 + (5.0 - 5.0 - GEOMETRY_TOLERANCE_MM))
    assert right[0] < 400.0
    assert extension_conflict(safe, 10, None, obstacles) == ""
    assert _body_clears(safe, 10, obstacles)

    wider = liner_toolpath_mm(piece, "edge_width_top", 0, 1.2, 12, obstacles=obstacles)
    _left, wider_right = _ends(wider)
    assert wider_right[0] == pytest.approx(400.0 + (5.0 - 6.0 - GEOMETRY_TOLERANCE_MM))
    assert _body_clears(wider, 12, obstacles)


def test_a_wider_gap_keeps_a_longer_extension_than_a_tight_gap():
    piece = _regular()
    tight = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=_right_neighbor(5))
    wide = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=_right_neighbor(10))
    bare = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8)
    assert _ends(wide)[1][0] > _ends(tight)[1][0]
    assert wide == bare


def test_each_end_is_independent():
    piece = _regular()
    start_only = [_box(-400.0, -80.0, -5.0, 200.0)]
    end_only = _right_neighbor(5)
    start_path = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=start_only)
    end_path = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=end_only)
    both = liner_toolpath_mm(
        piece, "edge_width_top", 0, 0.8, 8, obstacles=start_only + end_only
    )
    bare = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8)
    assert _ends(start_path)[0][0] == pytest.approx(0.0 - (5.0 - 4.0 - GEOMETRY_TOLERANCE_MM))
    assert _ends(start_path)[1] == pytest.approx(_ends(bare)[1])
    assert _ends(end_path)[0] == pytest.approx(_ends(bare)[0])
    assert _ends(both)[0][0] == pytest.approx(_ends(start_path)[0][0])
    assert _ends(both)[1][0] == pytest.approx(_ends(end_path)[1][0])


def test_no_neighbor_on_the_extension_keeps_the_original_path():
    piece = _regular()
    below = [_box(0.0, 500.0, 400.0, 900.0)]
    bare = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8)
    safe = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=below)
    assert safe == bare


def test_several_neighbors_use_the_nearest_material():
    piece = _regular()
    far = _box(420.0, -40.0, 900.0, 80.0)
    near = _box(405.0, -10.0, 415.0, 30.0)
    path = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=[far, near])
    assert _ends(path)[1][0] == pytest.approx(400.75)
    assert extension_conflict(path, 8, None, [far, near]) == ""


def test_a_lateral_collision_is_not_cleared_by_shortening_the_ends():
    piece = _regular()
    lateral = [_box(120.0, -2.0, 280.0, 12.0)]
    path = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=lateral)
    assert extension_conflict(path, 8, None, lateral) == "liner_extension_hits_piece"


def test_impossible_clearance_refuses_the_toolpath():
    piece = _regular()
    with pytest.raises(LinerGeometryError) as raised:
        liner_toolpath_mm(piece, "edge_width_top", 0, 1.2, 12, obstacles=_right_neighbor(1))
    assert raised.value.code == "liner_extension_hits_piece"


def test_rotated_neighbor_uses_the_placed_outline():
    piece = _regular()
    local = _right_neighbor(5)
    bare_local = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=local)
    width, height = 400.0, 600.0
    turns = 1
    host_outer = [
        transform_point(point, mirrored=False, quarter_turns=turns, width=width, height=height)
        for point in [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    ]
    neighbor_outer = [
        transform_point(point, mirrored=False, quarter_turns=turns, width=width, height=height)
        for point in local[0]["polygon"]
    ]
    host = {"id": "host", "x": 0, "y": 0, "w": 40, "h": 60, "label": "1.1"}
    neighbor = {
        "id": "neighbor",
        "x": 0,
        "y": 0,
        "w": 40,
        "h": 60,
        "label": "2.1",
        "geometry": {"outer": neighbor_outer, "holes": []},
    }
    framed = obstacles_in_toolpath_frame(
        [host, neighbor],
        host,
        host_outer,
        mirrored=False,
        quarter_turns=turns,
        width_mm=width,
        height_mm=height,
    )
    framed_path = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=framed)
    assert framed_path == bare_local


def test_l_shaped_end_shortens_against_the_real_tip():
    piece = LinerPiece("L-Shaped Corner", 40, 60, "Top Right", 15, 20)
    obstacles = [_box(255.0, -40.0, 500.0, 40.0)]
    path = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=obstacles)
    assert max(point[0] for point in path) == pytest.approx(250.0 + 0.75)
    assert extension_conflict(path, 8, None, obstacles) == ""
    assert _body_clears(path, 8, obstacles)


def test_clipped_corner_shortens_along_the_diagonal_end():
    piece = LinerPiece("Clipped Corner", 40, 60, "Top Right", 10, 12)
    bare = liner_toolpath_mm(piece, "edge_break_only", 0, 0.8, 8)
    tip = max(bare, key=lambda point: point[0] + point[1])
    obstacles = [_box(tip[0], tip[1], tip[0] + 40.0, tip[1] + 40.0)]
    assert extension_conflict(bare, 8, None, obstacles) == "liner_extension_hits_piece"
    safe = liner_toolpath_mm(piece, "edge_break_only", 0, 0.8, 8, obstacles=obstacles)
    safe_tip = max(safe, key=lambda point: point[0] + point[1])
    assert safe_tip[0] + safe_tip[1] < tip[0] + tip[1] - 0.2
    assert extension_conflict(safe, 8, None, obstacles) == ""
    assert _body_clears(safe, 8, obstacles)


def test_a_glass_hole_is_not_solid_material():
    hole = {
        "polygon": [(350.0, -80.0), (900.0, -80.0), (900.0, 80.0), (350.0, 80.0)],
        "holes": [[(360.0, -40.0), (700.0, -40.0), (700.0, 40.0), (360.0, 40.0)]],
    }
    solid = {"polygon": [(360.0, -40.0), (700.0, -40.0), (700.0, 40.0), (360.0, 40.0)]}
    segment = [(380.0, 4.0), (420.0, 4.0)]
    assert extension_conflict(segment, 8, None, [hole]) == ""
    assert extension_conflict(segment, 8, None, [solid]) == "liner_extension_hits_piece"


def test_each_pass_end_is_shortened_and_merged_joins_stay_clear():
    piece = _regular()
    obstacles = _right_neighbor(5)
    path = liner_toolpath_mm(piece, "edge_width_top", 0, 2.0, 8, obstacles=obstacles)
    right_ends = {round(point[0], 3) for point in path if point[0] > 390.0}
    assert right_ends == {400.75}
    assert len({round(point[1], 3) for point in path if abs(point[0] - 400.75) < 0.01}) >= 2
    assert extension_conflict(path, 8, None, obstacles) == ""

    specs = [
        {"side": "edge_width_top", "offset_cm": 0, "start_cm": 0, "length_cm": 0},
        {"side": "edge_long_left", "offset_cm": 0, "start_cm": 0, "length_cm": 0},
    ]
    merged = merged_liner_toolpaths_mm(piece, specs, 1.5, 8, obstacles=obstacles)
    bare = merged_liner_toolpaths_mm(piece, specs, 1.5, 8)
    assert len(merged) == len(bare) == 2
    assert merged != bare
    assert all(extension_conflict(item, 8, None, obstacles) == "" for item in merged)
    assert compare_liner_set_paths(merged, piece, specs, 1.5, 8, obstacles=obstacles).ok
    assert compare_liner_set_paths(bare, piece, specs, 1.5, 8, obstacles=obstacles).ok


def test_each_operation_uses_its_own_bit_diameter():
    piece = _regular()
    obstacles = _right_neighbor(5)
    ends = {}
    for kind, diameter in (
        ("liner", 8.0),
        ("back_groove", 5.0),
        ("recessed_handle_cutout", 12.0),
    ):
        path = generate_toolpath(
            kind=kind,
            piece=piece,
            reference_side="edge_width_top",
            offset_cm=0,
            width_cm=diameter / 10.0,
            start_cm=0,
            length_cm=None,
            cutter_diameter_mm=diameter,
            obstacles=obstacles,
        )
        ends[kind] = _ends(path)[1][0]
        assert extension_conflict(path, diameter, None, obstacles) == ""
        assert _body_clears(path, diameter, obstacles)
    assert ends["back_groove"] > ends["liner"] > ends["recessed_handle_cutout"]
    assert ends["back_groove"] == pytest.approx(402.5)
    assert ends["liner"] == pytest.approx(400.75)
    assert ends["recessed_handle_cutout"] == pytest.approx(398.75)


def test_import_accepts_only_the_proven_short_extension():
    piece = _regular()
    obstacles = _right_neighbor(5)
    safe = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8, obstacles=obstacles)
    full = liner_toolpath_mm(piece, "edge_width_top", 0, 0.8, 8)
    assert compare_liner_path(
        safe, piece, "edge_width_top", 0, 0.8, 8, obstacles=obstacles
    ).ok
    assert compare_liner_path(full, piece, "edge_width_top", 0, 0.8, 8, obstacles=obstacles).ok
    unproven = compare_liner_path(safe, piece, "edge_width_top", 0, 0.8, 8)
    assert unproven.ok is False
    too_short = [(point[0] - (1.0 if point[0] > 400.0 else 0.0), point[1]) for point in safe]
    assert compare_liner_path(
        too_short, piece, "edge_width_top", 0, 0.8, 8, obstacles=obstacles
    ).ok is False
