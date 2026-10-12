from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import has_self_intersection
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LINER_OFFSET_MISMATCH,
    LINER_SHAPE_MISMATCH,
    LINER_SIDE_MISMATCH,
    LINER_WIDTH_MISMATCH,
    LINER_WIDTH_NOT_MEASURABLE,
    LinerPiece,
    available_liner_sides,
    canonical_path,
    compare_liner_path,
    contour_notch_cm,
    liner_activation_error,
    liner_strip_polygon_mm,
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


def test_changing_offset_and_width_moves_the_band():
    piece = _regular()
    first = _bbox(liner_strip_polygon_mm(piece, "edge_long_left", 2, 1))
    second = _bbox(liner_strip_polygon_mm(piece, "edge_long_left", 5, 3))
    assert first[0] == pytest.approx(20)
    assert second[0] == pytest.approx(50)
    assert second[2] - second[0] == pytest.approx(30)
