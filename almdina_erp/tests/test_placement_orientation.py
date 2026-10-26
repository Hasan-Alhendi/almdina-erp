"""Phase 2: in-plane mirror and quarter turns stay compatible with ``rotated``."""

from __future__ import annotations

import math

from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import glass_hole_ring_mm
from almdina_erp.almdina_erp.domain.cutting.placement_orientation import (
    PlacementOrientation,
    PlacementOrientationError,
    assert_orientation_allowed,
    inverse_ring,
    physical_edge_bands,
    resolve_placement_orientation,
    transform_ring,
)
from almdina_erp.almdina_erp.domain.cutting.regular_machining_orientation import (
    physical_edge_tokens,
)


L_OUTLINE = (
    (0.0, 0.0),
    (280.0, 0.0),
    (280.0, 120.0),
    (400.0, 120.0),
    (400.0, 800.0),
    (0.0, 800.0),
)


def _lengths(points):
    ring = list(points)
    return tuple(sorted(
        round(math.dist(ring[index], ring[(index + 1) % len(ring)]), 6)
        for index in range(len(ring))
    ))


def test_historical_rotated_flag_is_not_a_mirror():
    turned = resolve_placement_orientation({"rotated": True})
    plain = resolve_placement_orientation({"rotated": False})
    missing = resolve_placement_orientation({})

    assert turned == PlacementOrientation(False, 1)
    assert turned.rotated is True
    assert turned.rotation_deg == 90
    assert plain == PlacementOrientation(False, 0)
    assert missing.mirrored is False
    assert missing.quarter_turns == 0


def test_explicit_mirror_and_half_turn_do_not_replace_the_rotated_flag():
    orientation = resolve_placement_orientation({
        "rotated": False,
        "corner_mirrored": 1,
        "rotation_quarter_turns": 2,
    })

    assert orientation.mirrored is True
    assert orientation.quarter_turns == 2
    assert orientation.rotated is False
    assert orientation.rotation_deg == 180


def test_horizontal_mirror_swaps_left_and_right_only():
    bands = {"left": "L", "top": "T", "right": "R", "bottom": "B"}
    orientation = PlacementOrientation(True, 0)

    assert physical_edge_bands(bands, orientation) == ("R", "T", "L", "B")
    assert physical_edge_tokens(bands, 0, mirrored=True) == ("R", "T", "L", "B")
    assert physical_edge_tokens(bands, 1) == ("B", "L", "T", "R")


def test_mirror_and_quarter_turn_keep_the_real_outline_measurements():
    orientation = PlacementOrientation(True, 1)
    moved = transform_ring(L_OUTLINE, orientation, width=400.0, height=800.0)

    assert _lengths(moved) == _lengths(L_OUTLINE)
    assert inverse_ring(moved, orientation, width=400.0, height=800.0) == list(L_OUTLINE)
    moved_top = dict(zip(L_OUTLINE, moved))
    assert moved_top[(0.0, 0.0)][1] != 0.0
    assert moved_top[(280.0, 0.0)][1] != 0.0


def test_mirror_without_a_turn_keeps_the_top_edge_on_top():
    orientation = PlacementOrientation(True, 0)
    moved = transform_ring(L_OUTLINE, orientation, width=400.0, height=800.0)
    top = [point for point in moved if abs(point[1]) < 1e-9]

    assert len(top) == 2
    assert {point[0] for point in top} == {120.0, 400.0}


def test_order_policy_blocks_mirror_and_keeps_rotation_rules():
    mirror = PlacementOrientation(True, 0)
    try:
        assert_orientation_allowed(mirror, mirroring_allowed=False, allow_rotation=0)
    except PlacementOrientationError as error:
        assert error.code == "FORBIDDEN_MIRRORING"
    else:
        raise AssertionError("mirror was accepted")

    assert_orientation_allowed(mirror, mirroring_allowed=True, allow_rotation=0)
    try:
        assert_orientation_allowed(
            PlacementOrientation(False, 1),
            mirroring_allowed=True,
            allow_rotation=0,
        )
    except PlacementOrientationError as error:
        assert error.code == "FORBIDDEN_ROTATION"
    else:
        raise AssertionError("rotation was accepted")


def test_glass_opening_follows_the_same_quarter_turn_without_changing_size():
    hole = glass_hole_ring_mm(
        cut_width_mm=400,
        cut_length_mm=800,
        margin_mm=20,
        long_left_mm=2,
        long_right_mm=4,
        width_bottom_mm=3,
        width_top_mm=1,
        rotated=False,
    )
    historical = glass_hole_ring_mm(
        cut_width_mm=400,
        cut_length_mm=800,
        margin_mm=20,
        long_left_mm=2,
        long_right_mm=4,
        width_bottom_mm=3,
        width_top_mm=1,
        rotated=True,
    )
    moved = transform_ring(
        hole,
        PlacementOrientation(False, 1),
        width=400.0,
        height=800.0,
    )

    def box(points):
        return (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )

    assert box(moved) == box(historical)
    mirrored = transform_ring(hole, PlacementOrientation(True, 0), width=400.0, height=800.0)
    assert box(mirrored)[2] - box(mirrored)[0] == box(hole)[2] - box(hole)[0]
    assert box(mirrored)[3] - box(mirrored)[1] == box(hole)[3] - box(hole)[1]
    assert min(point[0] for point in mirrored) != min(point[0] for point in hole)
