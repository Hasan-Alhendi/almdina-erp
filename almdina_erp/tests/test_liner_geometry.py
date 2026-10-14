from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    has_self_intersection,
    point_in_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LINER_OFFSET_MISMATCH,
    LINER_SHAPE_MISMATCH,
    LINER_SIDE_MISMATCH,
    LINER_WIDTH_MISMATCH,
    LINER_WIDTH_NOT_MEASURABLE,
    LinerGeometryError,
    LinerPiece,
    available_liner_sides,
    canonical_path,
    compare_liner_path,
    contour_notch_cm,
    liner_activation_error,
    cutter_center_offsets_mm,
    liner_centerline_mm,
    liner_toolpath_mm,
    sawn_liner_ends,
    liner_strip_polygon_mm,
    piece_polygon_mm,
    transform_point,
    validation_code,
)


def _regular() -> LinerPiece:
    return LinerPiece("Regular", 40, 60)


def _clipped(position: str = "Top Right") -> LinerPiece:
    return LinerPiece("Clipped Corner", 100, 80, position, 20, 30)


def _l_piece(position: str = "Top Right") -> LinerPiece:
    return LinerPiece("L-Shaped Corner", 100, 80, position, 20, 30)


def _bbox(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def test_regular_outer_sides_and_invalid_values():
    assert available_liner_sides("Regular") == (
        "edge_width_top",
        "edge_width_bottom",
        "edge_long_left",
        "edge_long_right",
    )
    assert "edge_break" not in available_liner_sides("Regular")
    piece = _regular()
    assert validation_code(piece, "edge_width_top", 2, 1.5) == ""
    assert validation_code(piece, "edge_width_top", -1, 1.5) == "offset_invalid"
    assert validation_code(piece, "edge_width_top", 2, 0) == "width_invalid"
    assert validation_code(piece, "edge_break", 2, 1.5) == "side_unavailable"
    assert validation_code(piece, "edge_width_top", 50, 20) == "strip_outside"


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        ("edge_width_top", (0, 20, 400, 35)),
        ("edge_width_bottom", (0, 560, 400, 570)),
        ("edge_long_left", (10, 0, 30, 600)),
        ("edge_long_right", (340, 0, 360, 600)),
    ],
)
def test_regular_strip_on_each_side(side, expected):
    offset, width = (2, 1.5) if side == "edge_width_top" else (
        (3, 1) if side == "edge_width_bottom" else (
            (1, 2) if side == "edge_long_left" else (4, 2)
        )
    )
    box = _bbox(liner_strip_polygon_mm(_regular(), side, offset, width))
    assert box == pytest.approx(expected)


def test_regular_path_matches_and_rejects_offset_width_side_and_line():
    piece = _regular()
    strip = liner_strip_polygon_mm(piece, "edge_width_top", 2, 1.5)
    assert compare_liner_path(strip, piece, "edge_width_top", 2, 1.5).ok

    shifted = [(x, y + 10) for x, y in strip]
    offset = compare_liner_path(shifted, piece, "edge_width_top", 2, 1.5)
    assert offset.code == LINER_OFFSET_MISMATCH
    assert offset.expected == "2.000"
    assert offset.measured == "3.000"

    wider = liner_strip_polygon_mm(piece, "edge_width_top", 2, 3)
    width = compare_liner_path(wider, piece, "edge_width_top", 2, 1.5)
    assert width.code == LINER_WIDTH_MISMATCH
    assert width.expected == "1.500"
    assert width.measured == "3.000"

    bottom = liner_strip_polygon_mm(piece, "edge_width_bottom", 2, 1.5)
    side = compare_liner_path(bottom, piece, "edge_width_top", 2, 1.5)
    assert side.code == LINER_SIDE_MISMATCH
    assert side.expected == "edge_width_top"
    assert side.measured == "edge_width_bottom"

    line = [(0, 27.5), (400, 27.5)]
    missing_width = compare_liner_path(line, piece, "edge_width_top", 2, 1.5)
    assert missing_width.code == LINER_WIDTH_NOT_MEASURABLE

    short = [(point[0], point[1]) for point in strip if point[0] <= 100]
    shape = compare_liner_path(short, piece, "edge_width_top", 2, 1.5)
    assert shape.code == LINER_SHAPE_MISMATCH


@pytest.mark.parametrize("position", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"])
def test_clipped_break_and_outer_sides(position):
    piece = _clipped(position)
    assert set(available_liner_sides(piece.piece_type)) == {
        "edge_width_top",
        "edge_width_bottom",
        "edge_long_left",
        "edge_long_right",
        "edge_break",
        "edge_break_only",
    }
    for side in available_liner_sides(piece.piece_type):
        assert validation_code(piece, side, 1, 0.8) == ""
        strip = liner_strip_polygon_mm(piece, side, 1, 0.8)
        assert compare_liner_path(strip, piece, side, 1, 0.8).ok


@pytest.mark.parametrize("position", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"])
def test_l_notch_sides(position):
    piece = _l_piece(position)
    assert "edge_break_only" not in available_liner_sides(piece.piece_type)
    assert "edge_break" in available_liner_sides(piece.piece_type)
    for side in available_liner_sides(piece.piece_type):
        strip = liner_strip_polygon_mm(piece, side, 1, 0.8)
        assert compare_liner_path(strip, piece, side, 1, 0.8).ok
    assert validation_code(piece, "edge_break_only", 1, 0.8) == "side_unavailable"


def test_rotation_and_mirror_round_trip():
    piece = _regular()
    strip = liner_strip_polygon_mm(piece, "edge_width_top", 2, 1.5)
    width, height = 400.0, 600.0
    placed = [
        transform_point(point, mirrored=True, quarter_turns=1, width=width, height=height)
        for point in strip
    ]
    restored = canonical_path(
        placed,
        mirrored=True,
        quarter_turns=1,
        width_mm=width,
        height_mm=height,
    )
    for original, recovered in zip(strip, restored):
        assert recovered == pytest.approx(original)
    measurement = compare_liner_path(restored, piece, "edge_width_top", 2, 1.5)
    assert measurement.ok


def test_plan_pieces_keep_one_liner_spec_without_touching_edges():
    from almdina_erp.almdina_erp.domain.cutting.primitives import (
        expand_piece_groups,
        make_placed_piece,
    )

    rows = expand_piece_groups([
        {
            "width_cm": 40,
            "length_cm": 60,
            "qty": 1,
            "piece_type": "Regular",
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 2,
            "liner_width_cm": 1.5,
            "edge_width_top": 1,
            "edge_break": 0,
        }
    ])
    assert rows[0]["liner_reference_side"] == "edge_width_top"
    assert rows[0]["edge_width_top"] == 1
    assert rows[0]["edge_break"] == 0
    placed = make_placed_piece(rows[0], 0, 0, 40, 60, False)
    assert placed["liner_offset_cm"] == 2
    assert placed["liner_width_cm"] == 1.5
    assert placed["edge_width_top"] == 1


def _round_points(points):
    return [(round(x, 3), round(y, 3)) for x, y in points]


def test_skewed_band_is_rejected_when_min_and_max_still_match():
    piece = _regular()
    skewed = [(20, 20), (380, 20), (400, 35), (0, 35)]
    measurement = compare_liner_path(skewed, piece, "edge_width_top", 2, 1.5)
    assert measurement.code == LINER_SHAPE_MISMATCH
    assert not measurement.ok


def test_start_shift_reversal_and_collinear_points_still_match():
    piece = _regular()
    strip = liner_strip_polygon_mm(piece, "edge_width_top", 2, 1.5)
    shifted = strip[1:] + strip[:1]
    assert compare_liner_path(shifted, piece, "edge_width_top", 2, 1.5).ok
    assert compare_liner_path(list(reversed(strip)), piece, "edge_width_top", 2, 1.5).ok
    midpoint = ((strip[0][0] + strip[1][0]) / 2, (strip[0][1] + strip[1][1]) / 2)
    with_extra = [strip[0], midpoint, *strip[1:]]
    assert compare_liner_path(with_extra, piece, "edge_width_top", 2, 1.5).ok


def test_l_break_miter_stays_inside_and_keeps_constant_width():
    piece = _l_piece("Top Right")
    assert validation_code(piece, "edge_break", 0, 0.8) == ""
    strip = liner_strip_polygon_mm(piece, "edge_break", 1, 0.8)
    assert _round_points(strip) == [
        (790, 0),
        (790, 310),
        (1000, 310),
        (1000, 318),
        (782, 318),
        (782, 0),
    ]
    assert not has_self_intersection(strip, GEOMETRY_TOLERANCE_MM)
    assert compare_liner_path(strip, piece, "edge_break", 1, 0.8).ok
    clipped = _clipped("Top Right")
    diagonal = liner_strip_polygon_mm(clipped, "edge_break", 1, 0.8)
    assert validation_code(clipped, "edge_break", 1, 0.8) == ""
    assert not has_self_intersection(diagonal, GEOMETRY_TOLERANCE_MM)
    assert compare_liner_path(diagonal, clipped, "edge_break", 1, 0.8).ok


def test_new_blank_liner_is_rejected_and_legacy_special_are_kept():
    assert liner_activation_error(
        enabled=True,
        piece_type="Regular",
        side="",
        offset_cm=0,
        width_cm=0,
        legacy_checkbox_only=False,
    ) == "liner_parameters_required"
    assert liner_activation_error(
        enabled=True,
        piece_type="Regular",
        side="",
        offset_cm=0,
        width_cm=0,
        legacy_checkbox_only=True,
    ) == ""
    assert liner_activation_error(
        enabled=True,
        piece_type="Special",
        side="edge_width_top",
        offset_cm=2,
        width_cm=1.5,
        legacy_checkbox_only=False,
    ) == ""
    assert liner_activation_error(
        enabled=True,
        piece_type="Regular",
        side="edge_width_top",
        offset_cm=0,
        width_cm=1.5,
        legacy_checkbox_only=False,
    ) == ""
    assert validation_code(_regular(), "edge_width_top", 0, 1.5) == ""


def test_l_inner_strap_uses_the_raw_notch_for_the_liner():
    raw_width, raw_length = contour_notch_cm(
        piece_type="L-Shaped Corner",
        finished_width_cm=40,
        finished_length_cm=60,
        notch_width_cm=8,
        notch_length_cm=16,
        position="Top Right",
        side_thickness_mm={"long_right": 3, "width_top": 2, "width_bottom": 1},
        edge_break=True,
        edge_break_thickness_mm=1,
    )
    assert (raw_width, raw_length) == pytest.approx((7.8, 15.9))
    unproven_width, unproven_length = contour_notch_cm(
        piece_type="L-Shaped Corner",
        finished_width_cm=40,
        finished_length_cm=60,
        notch_width_cm=8,
        notch_length_cm=16,
        position="Top Right",
        side_thickness_mm={"long_right": 3, "width_top": 2},
        edge_break=True,
        edge_break_thickness_mm=None,
    )
    assert (unproven_width, unproven_length) == pytest.approx((8, 16))
    raw_piece = LinerPiece("L-Shaped Corner", 40, 60, "Top Right", raw_width, raw_length)
    finished_piece = LinerPiece("L-Shaped Corner", 40, 60, "Top Right", 8, 16)
    strip = liner_strip_polygon_mm(raw_piece, "edge_break", 1, 0.8)
    assert compare_liner_path(strip, raw_piece, "edge_break", 1, 0.8).ok
    assert not compare_liner_path(strip, finished_piece, "edge_break", 1, 0.8).ok


def test_cutter_centers_cover_width_without_crossing_it():
    centers = cutter_center_offsets_mm(18, 5)
    assert centers == pytest.approx([2.5, 7.5, 10.5, 15.5])
    assert [right - left for left, right in zip(centers, centers[1:])] == pytest.approx([5, 3, 5])
    radius = 2.5
    for left, right in zip(centers, centers[1:]):
        assert right - left <= 5 + 1e-9
    assert centers[0] - radius == pytest.approx(0)
    assert centers[-1] + radius == pytest.approx(18)
    assert cutter_center_offsets_mm(15, 5) == pytest.approx([2.5, 7.5, 12.5])
    assert cutter_center_offsets_mm(5, 5) == pytest.approx([2.5])
    with pytest.raises(Exception):
        cutter_center_offsets_mm(4, 5)
    with pytest.raises(Exception):
        cutter_center_offsets_mm(18, 0)


def test_centerline_follows_the_middle_of_the_strip():
    piece = _regular()
    line = liner_centerline_mm(piece, "edge_width_top", 2, 1.5)
    assert line == pytest.approx([(0, 27.5), (400, 27.5)])
    shaped = _l_piece("Top Right")
    bent = liner_centerline_mm(shaped, "edge_break", 0, 1.8)
    assert len(bent) == 3
    assert _has_corner(bent)
    clipped = _clipped("Top Right")
    diagonal = liner_centerline_mm(clipped, "edge_break", 0, 1.8)
    assert any(point[0] != diagonal[0][0] and point[1] != diagonal[0][1] for point in diagonal)


def test_regular_toolpath_extends_by_the_tool_radius():
    piece = _regular()
    path = liner_toolpath_mm(piece, "edge_width_top", 0, 1.8, 5)
    ys = sorted({round(point[1], 3) for point in path})
    assert ys == pytest.approx([2.5, 7.5, 10.5, 15.5])
    xs = [point[0] for point in path]
    assert min(xs) == pytest.approx(-2.5)
    assert max(xs) == pytest.approx(402.5)
    assert compare_liner_path(path, piece, "edge_width_top", 0, 1.8, 5).ok
    short = [(max(point[0], 0), point[1]) for point in path]
    assert compare_liner_path(short, piece, "edge_width_top", 0, 1.8, 5).code == LINER_SHAPE_MISMATCH
    assert not compare_liner_path(path, piece, "edge_width_top", 0, 1.8, None).ok


def test_toolpath_follows_diameter_change_and_corner_breaks():
    piece = _regular()
    narrow = liner_toolpath_mm(piece, "edge_long_left", 0, 1.8, 6)
    assert sorted({round(point[0], 3) for point in narrow}) == pytest.approx([3, 9, 15])
    for side in ("edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right"):
        generated = liner_toolpath_mm(piece, side, 1, 1.5, 5)
        assert compare_liner_path(generated, piece, side, 1, 1.5, 5).ok
    shaped = _l_piece("Top Right")
    bent = liner_toolpath_mm(shaped, "edge_break", 1, 0.8, 4)
    assert any(abs(point[0] - 790) < 1 and abs(point[1] - 310) < 20 for point in bent) or any(
        point[0] < 800 and point[1] > 300 for point in bent
    )
    assert compare_liner_path(bent, shaped, "edge_break", 1, 0.8, 4).ok
    clipped = _clipped("Top Right")
    diagonal = liner_toolpath_mm(clipped, "edge_break", 1, 0.8, 4)
    assert compare_liner_path(diagonal, clipped, "edge_break", 1, 0.8, 4).ok
    turned = [
        transform_point(point, mirrored=True, quarter_turns=1, width=400, height=600)
        for point in liner_toolpath_mm(piece, "edge_width_top", 2, 1.5, 5)
    ]
    restored = canonical_path(
        turned,
        mirrored=True,
        quarter_turns=1,
        width_mm=400,
        height_mm=600,
    )
    assert compare_liner_path(restored, piece, "edge_width_top", 2, 1.5, 5).ok


def _has_corner(path):
    for first, middle, last in zip(path, path[1:], path[2:]):
        area = (middle[0] - first[0]) * (last[1] - first[1]) - (middle[1] - first[1]) * (last[0] - first[0])
        if abs(area) > 1:
            return True
    return False


def _edge_distance(point, polygon):
    import math

    best = math.inf
    ring = list(polygon) + [polygon[0]]
    for start, finish in zip(ring, ring[1:]):
        length = math.dist(start, finish) or 1.0
        area = abs(
            (point[0] - start[0]) * (finish[1] - start[1])
            - (point[1] - start[1]) * (finish[0] - start[0])
        )
        best = min(best, area / length)
    return best


def test_l_toolpath_follows_the_bend_and_extends_once():
    assert cutter_center_offsets_mm(12, 5) == pytest.approx([2.5, 7.5, 9.5])
    assert cutter_center_offsets_mm(23, 5) == pytest.approx([2.5, 7.5, 12.5, 15.5, 20.5])
    assert cutter_center_offsets_mm(18, 3)[0] == pytest.approx(1.5)
    assert cutter_center_offsets_mm(18, 6) == pytest.approx([3, 9, 15])
    raw_width, raw_length = contour_notch_cm(
        piece_type="L-Shaped Corner",
        finished_width_cm=40,
        finished_length_cm=60,
        notch_width_cm=8,
        notch_length_cm=16,
        position="Top Right",
        side_thickness_mm={"long_right": 3, "width_top": 2},
        edge_break=True,
        edge_break_thickness_mm=1,
    )
    raw_piece = LinerPiece("L-Shaped Corner", 40, 60, "Top Right", raw_width, raw_length)
    strapped = liner_toolpath_mm(raw_piece, "edge_break", 1, 0.8, 4)
    assert compare_liner_path(strapped, raw_piece, "edge_break", 1, 0.8, 4).ok
    for position in ("Top Right", "Top Left", "Bottom Right", "Bottom Left"):
        piece = _l_piece(position)
        path = liner_toolpath_mm(piece, "edge_break", 0, 1.8, 5)
        polygon = piece_polygon_mm(piece)
        assert len(path) == 12
        assert _has_corner(path)
        assert compare_liner_path(path, piece, "edge_break", 0, 1.8, 5).ok
        for end in (path[0], path[-1]):
            assert not point_in_polygon(end, polygon, tolerance=GEOMETRY_TOLERANCE_MM)
            assert _edge_distance(end, polygon) == pytest.approx(2.5, abs=0.05)


def test_partial_liner_uses_a_flat_end_and_keeps_the_full_edge():
    piece = LinerPiece("Regular", 50, 50)
    center = liner_centerline_mm(piece, "edge_long_right", 10, 1.8, 10, 30)
    assert center == pytest.approx([(391.0, 100.0), (391.0, 400.0)])
    path = liner_toolpath_mm(piece, "edge_long_right", 10, 1.8, 5, 10, 30)
    assert min(point[1] for point in path) == pytest.approx(102.5)
    assert max(point[1] for point in path) == pytest.approx(397.5)
    assert compare_liner_path(path, piece, "edge_long_right", 10, 1.8, 5, 10, 30).ok
    assert not compare_liner_path(path, piece, "edge_long_right", 10, 1.8, 5, 10, 20).ok
    assert not compare_liner_path(path, piece, "edge_long_right", 10, 1.8, 5, 12, 30).ok
    full = liner_toolpath_mm(piece, "edge_long_right", 10, 1.8, 5, 0, 0)
    assert min(point[1] for point in full) == pytest.approx(-2.5)
    assert max(point[1] for point in full) == pytest.approx(502.5)
    with pytest.raises(LinerGeometryError) as too_short:
        liner_toolpath_mm(piece, "edge_long_right", 10, 1.8, 5, 10, 0.3)
    assert too_short.value.code == "liner_flat_end_unmachinable"
    with pytest.raises(LinerGeometryError) as one_pass:
        liner_toolpath_mm(piece, "edge_long_right", 0, 0.5, 5, 10, 20)
    assert one_pass.value.code == "liner_flat_end_unmachinable"
    horizontal = liner_toolpath_mm(piece, "edge_width_top", 2, 1.8, 5, 5, 20)
    assert min(point[0] for point in horizontal) == pytest.approx(52.5)
    assert max(point[0] for point in horizontal) == pytest.approx(247.5)
    stops_inside = liner_toolpath_mm(piece, "edge_long_left", 0, 1.8, 5, 0, 20)
    assert min(point[1] for point in stops_inside) == pytest.approx(-2.5)
    assert max(point[1] for point in stops_inside) == pytest.approx(197.5)
    starts_inside = liner_toolpath_mm(piece, "edge_long_left", 0, 1.8, 5, 15, 35)
    assert min(point[1] for point in starts_inside) == pytest.approx(152.5)
    assert max(point[1] for point in starts_inside) == pytest.approx(502.5)


def test_partial_liner_follows_a_diagonal_and_an_l_before_the_bend():
    clipped = _clipped()
    diagonal = liner_toolpath_mm(clipped, "edge_break", 0, 1.8, 5, 2, 8)
    assert compare_liner_path(diagonal, clipped, "edge_break", 0, 1.8, 5, 2, 8).ok
    shaped = _l_piece()
    bent = liner_toolpath_mm(shaped, "edge_break", 0, 1.8, 5, 2, 8)
    assert compare_liner_path(bent, shaped, "edge_break", 0, 1.8, 5, 2, 8).ok
    with pytest.raises(LinerGeometryError) as on_corner:
        liner_toolpath_mm(shaped, "edge_break", 0, 1.8, 5, 0, 30)
    assert on_corner.value.code == "liner_span_on_corner"


def test_full_break_toolpath_covers_the_miter_and_a_gap_does_not():
    piece = LinerPiece("Clipped Corner", 84, 63, "Top Right", 54, 23)
    path = liner_toolpath_mm(piece, "edge_break", 10, 1.5, 3)
    assert compare_liner_path(path, piece, "edge_break", 10, 1.5, 3).ok
    assert compare_liner_path(path, piece, "edge_break", 10, 1.5, None).reason_code == (
        "path_does_not_follow_edge"
    )
    gapped = path[:7] + path[-7:]
    assert compare_liner_path(gapped, piece, "edge_break", 10, 1.5, 3).reason_code == (
        "coverage_gap"
    )


def test_changing_offset_and_width_moves_the_band():
    piece = _regular()
    first = _bbox(liner_strip_polygon_mm(piece, "edge_long_left", 2, 1))
    second = _bbox(liner_strip_polygon_mm(piece, "edge_long_left", 5, 3))
    assert first[0] == pytest.approx(20)
    assert second[0] == pytest.approx(50)
    assert second[2] - second[0] == pytest.approx(30)


def _straight_span(path, axis):
    best = 0.0
    run = [path[0]]
    for previous, point in zip(path, path[1:]):
        same = abs(point[axis] - previous[axis]) <= 0.05
        if same:
            run.append(point)
            continue
        if len(run) >= 2:
            best = max(best, abs(run[-1][1 - axis] - run[0][1 - axis]))
        run = [point]
    if len(run) >= 2:
        best = max(best, abs(run[-1][1 - axis] - run[0][1 - axis]))
    return best


def test_cut_path_closes_a_full_edge_and_an_internal_end_closes_itself():
    piece = _regular()
    full = liner_toolpath_mm(piece, "edge_width_top", 0, 1.8, 5)
    assert min(point[0] for point in full) == pytest.approx(-2.5)
    assert max(point[0] for point in full) == pytest.approx(402.5)
    assert compare_liner_path(full, piece, "edge_width_top", 0, 1.8, 5).ok
    stopped_on_the_edge = [(min(400, max(0, point[0])), point[1]) for point in full]
    assert not compare_liner_path(stopped_on_the_edge, piece, "edge_width_top", 0, 1.8, 5).ok

    wide = LinerPiece("Regular", 122, 50)
    board_edge = liner_toolpath_mm(wide, "edge_width_top", 0, 1.8, 5)
    assert min(point[0] for point in board_edge) == pytest.approx(-2.5)
    assert max(point[0] for point in board_edge) == pytest.approx(1222.5)
    assert compare_liner_path(board_edge, wide, "edge_width_top", 0, 1.8, 5).ok

    partial = liner_toolpath_mm(piece, "edge_width_top", 0, 1.8, 5, 5, 20)
    assert _straight_span(partial, 0) == pytest.approx(13)
    assert compare_liner_path(partial, piece, "edge_width_top", 0, 1.8, 5, 5, 20).ok
    without_close = partial[3:]
    assert compare_liner_path(
        without_close, piece, "edge_width_top", 0, 1.8, 5, 5, 20
    ).reason_code == "end_not_closed"

    starts_inside = liner_toolpath_mm(piece, "edge_width_top", 0, 1.8, 5, 5, None)
    assert min(point[0] for point in starts_inside) == pytest.approx(52.5)
    assert max(point[0] for point in starts_inside) == pytest.approx(402.5)
    assert _straight_span(starts_inside, 0) == pytest.approx(13)
    assert compare_liner_path(starts_inside, piece, "edge_width_top", 0, 1.8, 5, 5, None).ok
    ends_inside = liner_toolpath_mm(piece, "edge_width_top", 0, 1.8, 5, 0, 20)
    assert min(point[0] for point in ends_inside) == pytest.approx(-2.5)
    assert max(point[0] for point in ends_inside) == pytest.approx(197.5)
    assert compare_liner_path(ends_inside, piece, "edge_width_top", 0, 1.8, 5, 0, 20).ok

    for shaped in (_clipped("Top Right"), _l_piece("Top Right")):
        generated = liner_toolpath_mm(shaped, "edge_break", 1, 0.8, 4)
        assert compare_liner_path(generated, shaped, "edge_break", 1, 0.8, 4).ok
        internal = liner_toolpath_mm(shaped, "edge_width_bottom", 0, 1.8, 5, 4, 12)
        assert compare_liner_path(internal, shaped, "edge_width_bottom", 0, 1.8, 5, 4, 12).ok
        assert _straight_span(internal, 0) > 10


def test_an_uncut_board_edge_closes_the_liner_and_a_real_cut_does_not():
    board = (0.0, 0.0, 1220.0, 2440.0)
    full = LinerPiece("Regular", 122, 244)
    assert sawn_liner_ends(
        full, "edge_width_top", origin_mm=(0.0, 0.0), mirrored=False, quarter_turns=0, board=board
    ) == (False, False)
    closed = liner_toolpath_mm(
        full, "edge_width_top", 0, 1.8, 5, start_sawn=False, end_sawn=False
    )
    assert min(point[0] for point in closed) == pytest.approx(2.5)
    assert max(point[0] for point in closed) == pytest.approx(1217.5)
    assert _straight_span(closed, 0) == pytest.approx(13)
    assert compare_liner_path(
        closed, full, "edge_width_top", 0, 1.8, 5, start_sawn=False, end_sawn=False
    ).ok
    extended = liner_toolpath_mm(full, "edge_width_top", 0, 1.8, 5)
    assert compare_liner_path(
        extended, full, "edge_width_top", 0, 1.8, 5, start_sawn=False, end_sawn=False
    ).reason_code == "end_not_closed"

    inside = LinerPiece("Regular", 40, 50)
    assert sawn_liner_ends(
        inside, "edge_width_top", origin_mm=(50.0, 50.0), mirrored=False, quarter_turns=0, board=board
    ) == (True, True)
    assert sawn_liner_ends(
        inside, "edge_width_top", origin_mm=(0.0, 0.0), mirrored=False, quarter_turns=0, board=board
    ) == (False, True)
    mixed = liner_toolpath_mm(
        inside, "edge_width_top", 0, 1.8, 5, start_sawn=False, end_sawn=True
    )
    assert min(point[0] for point in mixed) == pytest.approx(2.5)
    assert max(point[0] for point in mixed) == pytest.approx(402.5)
    assert _straight_span(mixed, 0) == pytest.approx(13)
    assert compare_liner_path(
        mixed, inside, "edge_width_top", 0, 1.8, 5, start_sawn=False, end_sawn=True
    ).ok

    partial = liner_toolpath_mm(full, "edge_width_top", 0, 1.8, 5, 10, 20, start_sawn=False, end_sawn=False)
    assert min(point[0] for point in partial) == pytest.approx(102.5)
    assert max(point[0] for point in partial) == pytest.approx(297.5)
    assert compare_liner_path(
        partial, full, "edge_width_top", 0, 1.8, 5, 10, 20, start_sawn=False, end_sawn=False
    ).ok

    trim_board = (-10.0, -10.0, 1210.0, 2430.0)
    assert sawn_liner_ends(
        full, "edge_width_top", origin_mm=(0.0, 0.0), mirrored=False, quarter_turns=0, board=trim_board
    ) == (True, True)
    assert sawn_liner_ends(
        inside, "edge_width_top", origin_mm=(0.0, 0.0), mirrored=False, quarter_turns=0, board=board
    )[1] is True
    assert sawn_liner_ends(
        inside, "edge_width_top", origin_mm=(405.0, 0.0), mirrored=False, quarter_turns=0, board=board
    ) == (True, True)

    clipped_start, clipped_end = sawn_liner_ends(
        _clipped("Top Right"),
        "edge_width_top",
        origin_mm=(0.0, 0.0),
        mirrored=False,
        quarter_turns=0,
        board=board,
    )
    assert clipped_start is False
    assert clipped_end is True
    break_start, break_end = sawn_liner_ends(
        _l_piece("Top Right"),
        "edge_break",
        origin_mm=(0.0, 0.0),
        mirrored=False,
        quarter_turns=0,
        board=board,
    )
    assert break_start is False
    assert break_end is True
