"""Corner DXF contours bind edge bands by geometry, not by the rotated flag."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from frappe import _

from almdina_erp.almdina_erp.domain.cutting.corner_contour_rotation import (
    _corner_polygon_mm,
    classify_corner_contour_type,
    match_corner_contour,
    measure_corner_remainings_cm,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
    present_issues,
    render_error_cards_html,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import OrderPieceCutSpec
from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
    _apply_strict_dimension_contract,
    _contour_notch_cm,
    _l_corner_cut,
)

WIDTH_MM = 400.0
HEIGHT_MM = 800.0
CUT_X_MM = 80.0
CUT_Y_MM = 160.0

_POLYGONS = {
    ("L-Shaped Corner", "Top Right"): [
        (0.0, 0.0),
        (320.0, 0.0),
        (320.0, 160.0),
        (400.0, 160.0),
        (400.0, 800.0),
        (0.0, 800.0),
    ],
    ("L-Shaped Corner", "Bottom Left"): [
        (0.0, 0.0),
        (400.0, 0.0),
        (400.0, 800.0),
        (80.0, 800.0),
        (80.0, 640.0),
        (0.0, 640.0),
    ],
    ("Clipped Corner", "Top Right"): [
        (0.0, 0.0),
        (320.0, 0.0),
        (400.0, 160.0),
        (400.0, 800.0),
        (0.0, 800.0),
    ],
    ("Clipped Corner", "Bottom Left"): [
        (0.0, 0.0),
        (400.0, 0.0),
        (400.0, 800.0),
        (80.0, 800.0),
        (0.0, 640.0),
    ],
}


def _rotate_clockwise(points, width, height):
    return [(height - y, x) for x, y in points], height, width


def _turned(points, turns):
    current = list(points)
    width, height = WIDTH_MM, HEIGHT_MM
    for _ in range(turns):
        current, width, height = _rotate_clockwise(current, width, height)
    return current, width, height


def _reflect_x(points, width=WIDTH_MM):
    return [(width - x, y) for x, y in points]


def _reflect_y(points, height=HEIGHT_MM):
    return [(x, height - y) for x, y in points]


def _mirror_then_turn(points, turns):
    reflected = _reflect_x(points)
    return _turned(reflected, turns)


def _disturb(points):
    """Shift the start vertex, reverse the winding, and split one edge."""
    shifted = list(points[2:] + points[:2])
    reversed_ring = list(reversed(shifted))
    start, end = reversed_ring[0], reversed_ring[1]
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    with_midpoint = [reversed_ring[0], midpoint, *reversed_ring[1:]]
    return [[x + 30.0, y + 50.0] for x, y in with_midpoint]


@pytest.mark.parametrize("piece_type", ["L-Shaped Corner", "Clipped Corner"])
@pytest.mark.parametrize("position", ["Top Right", "Bottom Left"])
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_contour_match_is_independent_of_vertex_order(piece_type, position, turns):
    rotated, _width, _height = _turned(_POLYGONS[(piece_type, position)], turns)

    match = match_corner_contour(
        _disturb(rotated),
        piece_type=piece_type,
        position=position,
        width_cm=40,
        length_cm=80,
        cut_width_cm=8,
        cut_length_cm=16,
    )

    assert match.reason == "unique"
    assert match.quarter_turns == turns
    assert match.mirrored is False


@pytest.mark.parametrize("piece_type", ["L-Shaped Corner", "Clipped Corner"])
@pytest.mark.parametrize("position", ["Top Right", "Bottom Left"])
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_mirrored_contour_matches_one_reflection_then_rotation(piece_type, position, turns):
    transformed, _width, _height = _mirror_then_turn(_POLYGONS[(piece_type, position)], turns)

    match = match_corner_contour(
        _disturb(transformed),
        piece_type=piece_type,
        position=position,
        width_cm=40,
        length_cm=80,
        cut_width_cm=8,
        cut_length_cm=16,
    )

    assert match.reason == "unique"
    assert match.mirrored is True
    assert match.quarter_turns == turns


def test_vertical_reflection_collapses_to_one_horizontal_mirror():
    reflected = _reflect_y(_POLYGONS[("L-Shaped Corner", "Top Right")])

    match = match_corner_contour(
        reflected,
        piece_type="L-Shaped Corner",
        position="Top Right",
        width_cm=40,
        length_cm=80,
        cut_width_cm=8,
        cut_length_cm=16,
    )

    assert match.reason == "unique"
    assert match.mirrored is True
    assert match.quarter_turns == 2


def test_wrong_cavity_is_not_a_rotation_or_a_mirror():
    match = match_corner_contour(
        _POLYGONS[("L-Shaped Corner", "Top Right")],
        piece_type="L-Shaped Corner",
        position="Top Right",
        width_cm=40,
        length_cm=80,
        cut_width_cm=12,
        cut_length_cm=16,
    )

    assert match.reason == "none"
    assert match.quarter_turns is None
    assert match.mirrored is False


@pytest.mark.parametrize("piece_type", ["L-Shaped Corner", "Clipped Corner"])
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
@pytest.mark.parametrize("mirrored", [False, True])
def test_corner_remaining_measurement_returns_to_order_frame(piece_type, turns, mirrored):
    ring = _mm_ring(piece_type, "Top Right", 900, 800, 600, 400)
    if mirrored:
        ring = _reflect_x(ring, width=900)
    transformed = ring
    width_mm, height_mm = 900, 800
    for _ in range(turns):
        transformed, width_mm, height_mm = _rotate_clockwise(
            transformed,
            width_mm,
            height_mm,
        )

    measured = measure_corner_remainings_cm(
        _disturb(transformed),
        piece_type=piece_type,
        rotated=bool(turns % 2),
    )

    assert measured == pytest.approx((30, 40))


@pytest.mark.parametrize(
    ("ring_type", "expected_type"),
    [
        ("L-Shaped Corner", "L-Shaped Corner"),
        ("Clipped Corner", "Clipped Corner"),
    ],
)
def test_corner_topology_classification_ignores_extra_collinear_vertices(
    ring_type,
    expected_type,
):
    ring = _disturb(_mm_ring(ring_type, "Top Right", 684, 684, 284, 284))

    assert classify_corner_contour_type(ring) == expected_type


def test_mirrored_or_rectangular_contour_is_not_a_guessed_rotation():
    mirrored = [
        (80.0, 0.0),
        (400.0, 0.0),
        (400.0, 800.0),
        (0.0, 800.0),
        (0.0, 160.0),
        (80.0, 160.0),
    ]
    mirror = match_corner_contour(
        mirrored,
        piece_type="L-Shaped Corner",
        position="Top Right",
        width_cm=40,
        length_cm=80,
        cut_width_cm=8,
        cut_length_cm=16,
    )
    rectangle = match_corner_contour(
        [(0.0, 0.0), (400.0, 0.0), (400.0, 800.0), (0.0, 800.0)],
        piece_type="Clipped Corner",
        position="Top Right",
        width_cm=40,
        length_cm=80,
        cut_width_cm=8,
        cut_length_cm=16,
    )
    square = [
        (0.0, 0.0),
        (400.0, 0.0),
        (400.0, 320.0),
        (320.0, 320.0),
        (320.0, 400.0),
        (0.0, 400.0),
    ]
    ambiguous = match_corner_contour(
        square,
        piece_type="L-Shaped Corner",
        position="Bottom Right",
        width_cm=40,
        length_cm=40,
        cut_width_cm=8,
        cut_length_cm=8,
    )
    equivalent = match_corner_contour(
        square,
        piece_type="L-Shaped Corner",
        position="Bottom Right",
        width_cm=40,
        length_cm=40,
        cut_width_cm=8,
        cut_length_cm=8,
        edge_bands={
            "top": "band",
            "bottom": "band",
            "left": "band",
            "right": "band",
            "inner_horizontal": "notch",
            "inner_vertical": "notch",
            "chord": "notch",
        },
    )

    assert mirror.reason == "unique" and mirror.mirrored is True and mirror.quarter_turns == 0
    assert rectangle.reason == "none" and rectangle.quarter_turns is None and rectangle.mirrored is False
    assert ambiguous.reason == "ambiguous" and ambiguous.quarter_turns is None and ambiguous.mirrored is False
    assert equivalent.reason == "unique" and equivalent.mirrored is False and equivalent.quarter_turns == 0


def _spec(**overrides) -> OrderPieceCutSpec:
    values = dict(
        row_index=1,
        finished_width_cm=Decimal("40"),
        finished_length_cm=Decimal("80"),
        cut_width_cm=Decimal("40"),
        cut_length_cm=Decimal("80"),
        width_deduction_mm=Decimal("0"),
        length_deduction_mm=Decimal("0"),
        allow_rotation=1,
        piece_type="L-Shaped Corner",
        qty=1,
        side_profiles=(
            {
                "side": "width_top",
                "side_label": "العرض العلوي",
                "edge_type": "PVC",
                "thickness_mm": Decimal("1"),
            },
            {
                "side": "long_left",
                "side_label": "الطول الأيسر",
                "edge_type": "PVC",
                "thickness_mm": Decimal("1"),
            },
        ),
        edge_break=1,
        edge_break_only=0,
        clipped_corner_position="Top Right",
        clipped_corner_width_cm=Decimal("8"),
        clipped_corner_length_cm=Decimal("16"),
    )
    values.update(overrides)
    return OrderPieceCutSpec(**values)


def _order(count=1):
    return SimpleNamespace(
        pieces=[
            SimpleNamespace(
                piece_instance_id=f"piece:corner-{index + 1}",
                extra_full_door_double=0,
                qty=1,
            )
            for index in range(count)
        ]
    )


def _snapshot(outer, *, width_cm, height_cm):
    return {
        "sheets": [
            {
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "w": width_cm,
                        "h": height_cm,
                        "piece_type": "Regular",
                        "geometry": {
                            "schema_version": 1,
                            "unit": "mm",
                            "coordinate_space": "usable_sheet",
                            "outer": outer,
                            "holes": [],
                        },
                    }
                ]
            }
        ]
    }


@pytest.mark.parametrize("piece_type", ["L-Shaped Corner", "Clipped Corner"])
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_snapshot_keeps_corner_contract_and_geometric_quarter_turns(piece_type, turns):
    rotated, width_mm, height_mm = _turned(_POLYGONS[(piece_type, "Top Right")], turns)
    snapshot = _snapshot(
        _disturb(rotated),
        width_cm=width_mm / 10.0,
        height_cm=height_mm / 10.0,
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(piece_type=piece_type, edge_break_only=1 if piece_type == "Clipped Corner" else 0)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert errors == []
    assert piece["clipped_corner_position"] == "Top Right"
    assert piece["clipped_corner_width_cm"] == 8
    assert piece["clipped_corner_length_cm"] == 16
    assert piece["edge_width_top"] == 1
    assert piece["edge_long_left"] == 1
    assert piece["edge_break"] == 1
    assert piece["edge_break_only"] == (1 if piece_type == "Clipped Corner" else 0)
    assert piece["corner_rotation_quarter_turns"] == turns
    assert piece["corner_mirrored"] == 0
    assert piece["rotated"] is (turns % 2 == 1)
    assert piece["geometry"]["outer"] == _disturb(rotated)


def test_half_turn_without_rotation_permission_is_rejected():
    rotated, width_mm, height_mm = _turned(_POLYGONS[("L-Shaped Corner", "Top Right")], 2)
    snapshot = _snapshot(_disturb(rotated), width_cm=width_mm / 10.0, height_cm=height_mm / 10.0)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(allow_rotation=0)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert [error.code for error in errors] == ["FORBIDDEN_ROTATION"]
    assert "corner_rotation_quarter_turns" not in piece


def test_unresolved_corner_contour_returns_a_clear_error_and_does_not_guess():
    snapshot = _snapshot(
        [[0.0, 0.0], [400.0, 0.0], [400.0, 800.0], [0.0, 800.0]],
        width_cm=40,
        height_cm=80,
    )

    errors = _apply_strict_dimension_contract(snapshot, [_spec()], order=_order())

    piece = snapshot["sheets"][0]["pieces"][0]
    assert [error.code for error in errors] == ["CORNER_EDGE_UNRESOLVED"]
    assert errors[0].params["reason"] == "none"
    assert "corner_rotation_quarter_turns" not in piece
    card = present_issue(errors[0])
    assert "قشاط الزاوية" in card.problem
    assert "0 أو 90 أو 180 أو 270" in card.action


def test_corner_without_edge_markers_keeps_fields_and_skips_binding():
    snapshot = _snapshot(
        [[0.0, 0.0], [400.0, 0.0], [400.0, 800.0], [0.0, 800.0]],
        width_cm=40,
        height_cm=80,
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(side_profiles=(), edge_break=0, edge_break_only=0)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert errors == []
    assert piece["clipped_corner_width_cm"] == 8
    assert piece["clipped_corner_length_cm"] == 16
    assert "corner_rotation_quarter_turns" not in piece


def test_regular_dxf_piece_does_not_receive_corner_binding():
    snapshot = _snapshot(
        [[0.0, 0.0], [400.0, 0.0], [400.0, 800.0], [0.0, 800.0]],
        width_cm=40,
        height_cm=80,
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(piece_type="Regular", side_profiles=(), edge_break=0)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert errors == []
    assert piece["piece_type"] == "Regular"
    assert "clipped_corner_position" not in piece
    assert "corner_rotation_quarter_turns" not in piece
    assert "corner_mirrored" not in piece
    assert piece["rotated"] is False


@pytest.mark.parametrize("piece_type", ["L-Shaped Corner", "Clipped Corner"])
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_snapshot_accepts_a_reflected_corner_without_rewriting_dxf(piece_type, turns):
    transformed, width_mm, height_mm = _mirror_then_turn(
        _POLYGONS[(piece_type, "Top Right")],
        turns,
    )
    outer = _disturb(transformed)
    snapshot = _snapshot(outer, width_cm=width_mm / 10.0, height_cm=height_mm / 10.0)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(piece_type=piece_type)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert errors == []
    assert piece["corner_mirrored"] == 1
    assert piece["corner_rotation_quarter_turns"] == turns
    assert piece["geometry"]["outer"] == outer
    assert piece["edge_width_top"] == 1
    assert piece["edge_long_left"] == 1
    assert piece["edge_profiles"]["width_top"]["edge_type"] == "PVC"
    assert piece["edge_profiles"]["long_left"]["thickness_mm"] == 1.0


def test_reflection_does_not_bypass_a_forbidden_rotation():
    transformed, width_mm, height_mm = _mirror_then_turn(
        _POLYGONS[("L-Shaped Corner", "Top Right")],
        1,
    )
    snapshot = _snapshot(
        _disturb(transformed),
        width_cm=width_mm / 10.0,
        height_cm=height_mm / 10.0,
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(allow_rotation=0)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert "FORBIDDEN_ROTATION" in [error.code for error in errors]
    assert "corner_mirrored" not in piece
    assert "corner_rotation_quarter_turns" not in piece


def test_unrotated_reflection_is_allowed_when_rotation_is_off():
    transformed, width_mm, height_mm = _mirror_then_turn(
        _POLYGONS[("Clipped Corner", "Top Right")],
        0,
    )
    snapshot = _snapshot(
        _disturb(transformed),
        width_cm=width_mm / 10.0,
        height_cm=height_mm / 10.0,
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(piece_type="Clipped Corner", allow_rotation=0, edge_break_only=1)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert errors == []
    assert piece["corner_mirrored"] == 1
    assert piece["corner_rotation_quarter_turns"] == 0
    assert piece["rotated"] is False


def test_half_turn_reflection_still_requires_rotation_permission():
    transformed, width_mm, height_mm = _mirror_then_turn(
        _POLYGONS[("L-Shaped Corner", "Top Right")],
        2,
    )
    snapshot = _snapshot(
        _disturb(transformed),
        width_cm=width_mm / 10.0,
        height_cm=height_mm / 10.0,
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_spec(allow_rotation=0)],
        order=_order(),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert [error.code for error in errors] == ["FORBIDDEN_ROTATION"]
    assert "corner_mirrored" not in piece


def test_same_outer_size_does_not_bind_the_other_cavity():
    outer = _disturb(_POLYGONS[("L-Shaped Corner", "Top Right")])
    snapshot = _snapshot(outer, width_cm=40, height_cm=80)
    first = _spec(row_index=1, clipped_corner_width_cm=Decimal("12"))
    second = _spec(row_index=2, clipped_corner_width_cm=Decimal("8"))

    errors = _apply_strict_dimension_contract(
        snapshot,
        [first, second],
        order=_order(2),
    )

    piece = snapshot["sheets"][0]["pieces"][0]
    assert [error.code for error in errors] == ["PIECE_MISSING"]
    assert piece["label"] == "2.1"
    assert piece["source_piece_no"] == 2
    assert piece["clipped_corner_width_cm"] == 8
    assert piece["corner_mirrored"] == 0
    assert piece["corner_rotation_quarter_turns"] == 0


def _multi_corner_order(specs):
    rows = [
        SimpleNamespace(
            piece_instance_id=f"piece:corner-row-{row_index}",
            extra_full_door_double=0,
            qty=1,
        )
        for row_index in range(1, max(spec.row_index for spec in specs) + 1)
    ]
    for spec in specs:
        rows[spec.row_index - 1].qty = spec.qty
    return SimpleNamespace(pieces=rows)


def _multi_corner_snapshot(rings):
    pieces = []
    for contour_no, ring in enumerate(rings, start=1):
        width_mm = max(point[0] for point in ring) - min(point[0] for point in ring)
        height_mm = max(point[1] for point in ring) - min(point[1] for point in ring)
        pieces.append(
            {
                "id": contour_no,
                "label": f"legacy-{contour_no}",
                "w": width_mm / 10.0,
                "h": height_mm / 10.0,
                "piece_type": "Regular",
                "geometry": {
                    "schema_version": 1,
                    "unit": "mm",
                    "coordinate_space": "usable_sheet",
                    "outer": ring,
                    "holes": [],
                },
            }
        )
    return {"sheets": [{"pieces": pieces}]}


def test_repeated_l_and_clipped_rows_with_the_same_outer_size_keep_their_identity():
    l_spec = _spec(row_index=1, qty=5)
    clipped_spec = _spec(
        row_index=2,
        qty=2,
        piece_type="Clipped Corner",
        edge_break_only=1,
    )
    l_ring = _disturb(_POLYGONS[("L-Shaped Corner", "Top Right")])
    clipped_ring = _disturb(_POLYGONS[("Clipped Corner", "Top Right")])
    snapshot = _multi_corner_snapshot(
        [clipped_ring, l_ring, l_ring, clipped_ring, l_ring, l_ring, l_ring]
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [l_spec, clipped_spec],
        order=_multi_corner_order([l_spec, clipped_spec]),
    )

    pieces = snapshot["sheets"][0]["pieces"]
    assert errors == []
    assert [(piece["source_piece_no"], piece["copy_no"]) for piece in pieces] == [
        (2, 1),
        (1, 1),
        (1, 2),
        (2, 2),
        (1, 3),
        (1, 4),
        (1, 5),
    ]
    assert [piece["piece_type"] for piece in pieces] == [
        "Clipped Corner",
        "L-Shaped Corner",
        "L-Shaped Corner",
        "Clipped Corner",
        "L-Shaped Corner",
        "L-Shaped Corner",
        "L-Shaped Corner",
    ]
    assert len({piece["piece_instance_id"] for piece in pieces}) == 7


def test_real_order_corner_groups_keep_row_and_copy_identity_when_mixed():
    specs = [
        _spec(
            row_index=3,
            qty=5,
            finished_width_cm=Decimal("68.4"),
            finished_length_cm=Decimal("68.4"),
            cut_width_cm=Decimal("68.4"),
            cut_length_cm=Decimal("68.4"),
            side_profiles=(),
            edge_break=0,
            clipped_corner_width_cm=Decimal("13.68"),
            clipped_corner_length_cm=Decimal("13.68"),
        ),
        _spec(
            row_index=8,
            qty=5,
            finished_width_cm=Decimal("66.8"),
            finished_length_cm=Decimal("68.4"),
            cut_width_cm=Decimal("66.8"),
            cut_length_cm=Decimal("68.4"),
            side_profiles=(),
            edge_break_thickness_mm=Decimal("1"),
            clipped_corner_width_cm=Decimal("26.8"),
            clipped_corner_length_cm=Decimal("28.4"),
        ),
        _spec(
            row_index=10,
            qty=2,
            piece_type="Clipped Corner",
            edge_break_only=1,
            finished_width_cm=Decimal("68.4"),
            finished_length_cm=Decimal("68.4"),
            cut_width_cm=Decimal("68.4"),
            cut_length_cm=Decimal("68.4"),
            side_profiles=(),
            edge_break=0,
            clipped_corner_width_cm=Decimal("18.4"),
            clipped_corner_length_cm=Decimal("18.4"),
        ),
        _spec(
            row_index=14,
            qty=2,
            piece_type="Clipped Corner",
            edge_break_only=1,
            finished_width_cm=Decimal("66.8"),
            finished_length_cm=Decimal("68.4"),
            cut_width_cm=Decimal("66.8"),
            cut_length_cm=Decimal("68.4"),
            side_profiles=(),
            edge_break=0,
            clipped_corner_width_cm=Decimal("16.8"),
            clipped_corner_length_cm=Decimal("18.4"),
        ),
    ]
    rings = {
        3: _mm_ring("L-Shaped Corner", "Top Right", 684, 684, 136.8, 136.8),
        8: _mm_ring("L-Shaped Corner", "Top Right", 668, 684, 269, 285),
        10: _mm_ring("Clipped Corner", "Top Right", 684, 684, 184, 184),
        14: _mm_ring("Clipped Corner", "Top Right", 668, 684, 168, 184),
    }
    mixed_rows = [10, 3, 8, 14, 3, 8, 10, 8, 3, 14, 3, 8, 3, 8]
    snapshot = _multi_corner_snapshot([_disturb(rings[row]) for row in mixed_rows])

    errors = _apply_strict_dimension_contract(
        snapshot,
        specs,
        order=_multi_corner_order(specs),
    )

    pieces = snapshot["sheets"][0]["pieces"]
    assert errors == []
    assert [piece["source_piece_no"] for piece in pieces] == mixed_rows
    for row_index, quantity in ((3, 5), (8, 5), (10, 2), (14, 2)):
        copies = [
            piece["copy_no"]
            for piece in pieces
            if piece["source_piece_no"] == row_index
        ]
        assert copies == list(range(1, quantity + 1))


def test_identical_corner_rows_are_rejected_as_genuinely_ambiguous():
    first = _spec(row_index=1)
    second = _spec(row_index=2)
    snapshot = _multi_corner_snapshot(
        [_disturb(_POLYGONS[("L-Shaped Corner", "Top Right")])]
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [first, second],
        order=_multi_corner_order([first, second]),
    )

    assert [error.code for error in errors] == [
        "PIECE_IDENTITY_AMBIGUOUS",
        "PIECE_MISSING",
    ]
    assert errors[0].params["candidate_source_piece_nos"] == [1, 2]
    piece = snapshot["sheets"][0]["pieces"][0]
    assert piece["piece_type"] == "Regular"
    assert "source_piece_no" not in piece


def test_repeated_corner_candidates_do_not_fall_back_when_no_shape_matches():
    l_spec = _spec(row_index=1, qty=2)
    clipped_spec = _spec(
        row_index=2,
        qty=2,
        piece_type="Clipped Corner",
        edge_break_only=1,
    )
    snapshot = _multi_corner_snapshot(
        [[[0.0, 0.0], [400.0, 0.0], [400.0, 800.0], [0.0, 800.0]]]
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [l_spec, clipped_spec],
        order=_multi_corner_order([l_spec, clipped_spec]),
    )

    assert [error.code for error in errors] == [
        "CORNER_EDGE_UNRESOLVED",
        "PIECE_MISSING",
    ]
    assert errors[0].params["reason"] == "none"
    assert errors[0].params["candidate_source_piece_nos"] == [1, 2]
    assert errors[0].target.source_piece_no is None
    ambiguous_card = present_issue(errors[0])
    assert "1" in ambiguous_card.target and "2" in ambiguous_card.target
    assert "مسار القص رقم 1" in ambiguous_card.target
    piece = snapshot["sheets"][0]["pieces"][0]
    assert piece["piece_type"] == "Regular"
    assert "source_piece_no" not in piece


def test_repeated_l_copies_with_wrong_remainings_are_present_not_missing():
    spec = _spec(
        row_index=3,
        qty=5,
        finished_width_cm=Decimal("90"),
        finished_length_cm=Decimal("90"),
        cut_width_cm=Decimal("90"),
        cut_length_cm=Decimal("90"),
        side_profiles=(),
        edge_break=1,
        edge_break_thickness_mm=Decimal("0"),
        clipped_corner_width_cm=Decimal("40"),
        clipped_corner_length_cm=Decimal("40"),
    )
    wrong = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 900, 900, 500, 500))
    snapshot = _multi_corner_snapshot([wrong] * 5)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [spec],
        order=_multi_corner_order([spec]),
    )

    assert [error.code for error in errors] == ["L_CORNER_NOTCH_MISMATCH"] * 5
    assert [error.target.source_piece_no for error in errors] == [3] * 5
    assert [error.target.copy_no for error in errors] == [1, 2, 3, 4, 5]
    assert all(error.params["expected_finished_remaining_cm"] == {
        "width": "50.000",
        "length": "50.000",
    } for error in errors)
    assert all(error.params["actual_raw_remaining_cm"] == {
        "width": "40.000",
        "length": "40.000",
    } for error in errors)
    assert "PIECE_MISSING" not in [error.code for error in errors]

    cards = present_issues(errors)
    assert len(cards) == 1
    assert cards[0].target == _("Door {0} — copies {1} through {2}.").format(3, 1, 5)
    assert "50 × 50" in cards[0].highlight
    assert "40 × 40" in cards[0].highlight


def test_l_geometry_excludes_same_bbox_clipped_candidate_before_dimension_diagnosis():
    l_spec = _spec(
        row_index=3,
        qty=5,
        finished_width_cm=Decimal("68.4"),
        finished_length_cm=Decimal("68.4"),
        cut_width_cm=Decimal("68.4"),
        cut_length_cm=Decimal("68.4"),
        side_profiles=(),
        edge_break=1,
        edge_break_thickness_mm=Decimal("0"),
        clipped_corner_width_cm=Decimal("18.4"),
        clipped_corner_length_cm=Decimal("18.4"),
    )
    clipped_spec = _spec(
        row_index=10,
        qty=5,
        piece_type="Clipped Corner",
        edge_break=0,
        edge_break_only=1,
        side_profiles=(),
        finished_width_cm=Decimal("68.4"),
        finished_length_cm=Decimal("68.4"),
        cut_width_cm=Decimal("68.4"),
        cut_length_cm=Decimal("68.4"),
        clipped_corner_width_cm=Decimal("18.4"),
        clipped_corner_length_cm=Decimal("18.4"),
    )
    wrong_l = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 684, 684, 284, 284))
    right_clipped = _disturb(
        _mm_ring("Clipped Corner", "Top Right", 684, 684, 184, 184)
    )
    snapshot = _multi_corner_snapshot([wrong_l] * 5 + [right_clipped] * 5)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [l_spec, clipped_spec],
        order=_multi_corner_order([l_spec, clipped_spec]),
    )

    assert [error.code for error in errors] == ["L_CORNER_NOTCH_MISMATCH"] * 5
    assert {error.target.source_piece_no for error in errors} == {3}
    assert {error.target.copy_no for error in errors} == {1, 2, 3, 4, 5}
    cards = present_issues(errors)
    assert len(cards) == 1
    assert cards[0].target == _("Door {0} — copies {1} through {2}.").format(3, 1, 5)
    assert "50 × 50" in cards[0].highlight
    assert "40 × 40" in cards[0].highlight


def test_one_wrong_l_copy_is_identified_without_marking_valid_siblings_missing():
    spec = _spec(
        row_index=3,
        qty=5,
        finished_width_cm=Decimal("68.4"),
        finished_length_cm=Decimal("68.4"),
        cut_width_cm=Decimal("68.4"),
        cut_length_cm=Decimal("68.4"),
        side_profiles=(),
        edge_break=1,
        edge_break_thickness_mm=Decimal("0"),
        clipped_corner_width_cm=Decimal("18.4"),
        clipped_corner_length_cm=Decimal("18.4"),
    )
    wrong = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 684, 684, 284, 284))
    correct = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 684, 684, 184, 184))
    snapshot = _multi_corner_snapshot([wrong, correct, correct, correct, correct])

    errors = _apply_strict_dimension_contract(
        snapshot,
        [spec],
        order=_multi_corner_order([spec]),
    )

    assert [error.code for error in errors] == ["L_CORNER_NOTCH_MISMATCH"]
    assert errors[0].target.source_piece_no == 3
    assert errors[0].target.copy_no == 1
    assert "PIECE_MISSING" not in [error.code for error in errors]


def test_clipped_geometry_excludes_same_bbox_l_candidate_before_dimension_diagnosis():
    l_spec = _spec(
        row_index=3,
        qty=5,
        finished_width_cm=Decimal("68.4"),
        finished_length_cm=Decimal("68.4"),
        cut_width_cm=Decimal("68.4"),
        cut_length_cm=Decimal("68.4"),
        side_profiles=(),
        edge_break=1,
        edge_break_thickness_mm=Decimal("0"),
        clipped_corner_width_cm=Decimal("18.4"),
        clipped_corner_length_cm=Decimal("18.4"),
    )
    clipped_spec = _spec(
        row_index=10,
        qty=5,
        piece_type="Clipped Corner",
        edge_break=0,
        edge_break_only=1,
        side_profiles=(),
        finished_width_cm=Decimal("68.4"),
        finished_length_cm=Decimal("68.4"),
        cut_width_cm=Decimal("68.4"),
        cut_length_cm=Decimal("68.4"),
        clipped_corner_width_cm=Decimal("18.4"),
        clipped_corner_length_cm=Decimal("18.4"),
    )
    right_l = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 684, 684, 184, 184))
    wrong_clipped = _disturb(
        _mm_ring("Clipped Corner", "Top Right", 684, 684, 284, 284)
    )
    snapshot = _multi_corner_snapshot([right_l] * 5 + [wrong_clipped] * 5)

    errors = _apply_strict_dimension_contract(
        snapshot,
        [l_spec, clipped_spec],
        order=_multi_corner_order([l_spec, clipped_spec]),
    )

    assert [error.code for error in errors] == [
        "CLIPPED_CORNER_DIMENSIONS_MISMATCH"
    ] * 5
    assert {error.target.source_piece_no for error in errors} == {10}
    assert {error.target.copy_no for error in errors} == {1, 2, 3, 4, 5}
    cards = present_issues(errors)
    assert len(cards) == 1
    assert cards[0].target == _("Door {0} — copies {1} through {2}.").format(10, 1, 5)
    assert "50 × 50" in cards[0].highlight
    assert "40 × 40" in cards[0].highlight


def test_repeated_clipped_copies_report_inner_dimensions_without_missing():
    spec = _spec(
        qty=2,
        piece_type="Clipped Corner",
        edge_break=0,
        edge_break_only=1,
        side_profiles=(),
        finished_width_cm=Decimal("90"),
        finished_length_cm=Decimal("90"),
        cut_width_cm=Decimal("90"),
        cut_length_cm=Decimal("90"),
        clipped_corner_width_cm=Decimal("40"),
        clipped_corner_length_cm=Decimal("40"),
    )
    wrong = _disturb(_mm_ring("Clipped Corner", "Top Right", 900, 900, 500, 500))
    snapshot = _multi_corner_snapshot([wrong, wrong])

    errors = _apply_strict_dimension_contract(
        snapshot,
        [spec],
        order=_multi_corner_order([spec]),
    )

    assert [error.code for error in errors] == [
        "CLIPPED_CORNER_DIMENSIONS_MISMATCH",
        "CLIPPED_CORNER_DIMENSIONS_MISMATCH",
    ]
    assert [error.target.copy_no for error in errors] == [1, 2]
    assert "PIECE_MISSING" not in [error.code for error in errors]
    cards = present_issues(errors)
    assert len(cards) == 1
    assert cards[0].target == _("Door {0} — copies {1} through {2}.").format(1, 1, 2)
    assert "50 × 50" in cards[0].highlight
    assert "40 × 40" in cards[0].highlight


def test_repeated_l_copies_with_unknown_inner_band_are_present_not_missing():
    spec = _spec(
        qty=2,
        edge_break=1,
        edge_break_thickness_mm=None,
    )
    recognizable_l = _disturb(
        _mm_ring("L-Shaped Corner", "Top Right", 400, 800, 80, 161)
    )
    snapshot = _multi_corner_snapshot([recognizable_l, recognizable_l])

    errors = _apply_strict_dimension_contract(
        snapshot,
        [spec],
        order=_multi_corner_order([spec]),
    )

    assert [error.code for error in errors] == [
        "CORNER_EDGE_UNRESOLVED",
        "CORNER_EDGE_UNRESOLVED",
    ]
    assert [error.target.source_piece_no for error in errors] == [1, 1]
    assert [error.target.copy_no for error in errors] == [1, 2]
    assert all(error.params["reason"] == "break_thickness_unknown" for error in errors)
    assert "PIECE_MISSING" not in [error.code for error in errors]


def test_different_corner_measurements_on_one_row_are_not_grouped_together():
    spec = _spec(
        qty=2,
        side_profiles=(),
        edge_break=1,
        edge_break_thickness_mm=Decimal("0"),
        finished_width_cm=Decimal("90"),
        finished_length_cm=Decimal("90"),
        cut_width_cm=Decimal("90"),
        cut_length_cm=Decimal("90"),
        clipped_corner_width_cm=Decimal("40"),
        clipped_corner_length_cm=Decimal("40"),
    )
    remaining_40 = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 900, 900, 500, 500))
    remaining_45 = _disturb(_mm_ring("L-Shaped Corner", "Top Right", 900, 900, 450, 450))
    snapshot = _multi_corner_snapshot([remaining_40, remaining_45])

    errors = _apply_strict_dimension_contract(
        snapshot,
        [spec],
        order=_multi_corner_order([spec]),
    )

    cards = present_issues(errors)
    assert len(cards) == 2
    assert {card.highlight for card in cards} == {
        _("Order dimensions: {0}. DXF dimensions: {1}.").format(
            "\u206650 × 50\u2069 سم",
            "\u206640 × 40\u2069 سم",
        ),
        _("Order dimensions: {0}. DXF dimensions: {1}.").format(
            "\u206650 × 50\u2069 سم",
            "\u206645 × 45\u2069 سم",
        ),
    }


_SQUARE_L = [
    [0.0, 0.0],
    [400.0, 0.0],
    [400.0, 320.0],
    [320.0, 320.0],
    [320.0, 400.0],
    [0.0, 400.0],
]


def _square_spec(**overrides):
    return _spec(
        finished_width_cm=Decimal("40"),
        finished_length_cm=Decimal("40"),
        cut_width_cm=Decimal("40"),
        cut_length_cm=Decimal("40"),
        clipped_corner_position="Bottom Right",
        clipped_corner_width_cm=Decimal("8"),
        clipped_corner_length_cm=Decimal("8"),
        **overrides,
    )


def test_symmetric_corner_accepts_one_transform_when_swapped_bands_match():
    snapshot = _snapshot(_SQUARE_L, width_cm=40, height_cm=40)

    errors = _apply_strict_dimension_contract(snapshot, [_square_spec()], order=_order())

    piece = snapshot["sheets"][0]["pieces"][0]
    assert errors == []
    assert piece["corner_mirrored"] == 0
    assert piece["corner_rotation_quarter_turns"] == 0


def test_symmetric_corner_rejects_when_swapped_edges_have_different_bands():
    snapshot = _snapshot(_SQUARE_L, width_cm=40, height_cm=40)
    top_only = (
        {
            "side": "width_top",
            "side_label": "العرض العلوي",
            "edge_type": "PVC",
            "thickness_mm": Decimal("1"),
        },
    )

    errors = _apply_strict_dimension_contract(
        snapshot,
        [_square_spec(side_profiles=top_only)],
        order=_order(),
    )

    assert [error.code for error in errors] == ["CORNER_EDGE_UNRESOLVED"]
    assert errors[0].params["reason"] == "ambiguous"
    assert "corner_rotation_quarter_turns" not in snapshot["sheets"][0]["pieces"][0]


def _mm_ring(piece_type, position, width_mm, height_mm, cut_x_mm, cut_y_mm):
    polygon = _corner_polygon_mm(
        piece_type=piece_type,
        position=position,
        width_mm=width_mm,
        height_mm=height_mm,
        cut_x_mm=cut_x_mm,
        cut_y_mm=cut_y_mm,
    )
    assert polygon is not None
    return [[point[0], point[1]] for point in polygon]


def _l_contract(**overrides):
    values = dict(
        side_profiles=(),
        edge_break=0,
        edge_break_thickness_mm=None,
        clipped_corner_position="Bottom Right",
        clipped_corner_width_cm=Decimal("8"),
        clipped_corner_length_cm=Decimal("16"),
        allow_rotation=1,
    )
    values.update(overrides)
    return _spec(**values)


def _import_l(outer, spec, *, width_cm, height_cm):
    snapshot = _snapshot(outer, width_cm=width_cm, height_cm=height_cm)
    errors = _apply_strict_dimension_contract(snapshot, [spec], order=_order())
    return errors, snapshot["sheets"][0]["pieces"][0]


def test_l_without_inner_band_accepts_the_raw_notch_and_keeps_finished_fields():
    spec = _l_contract(
        cut_width_cm=Decimal("39.9"),
        width_deduction_mm=Decimal("1"),
        side_profiles=(
            {
                "side": "long_left",
                "side_label": "الطول الأيسر",
                "edge_type": "PVC",
                "thickness_mm": Decimal("1"),
            },
        ),
    )
    errors, piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 800, 80, 160),
        spec,
        width_cm=39.9,
        height_cm=80,
    )
    assert errors == []
    assert piece["clipped_corner_width_cm"] == 8
    assert piece["clipped_corner_length_cm"] == 16
    assert piece["corner_mirrored"] == 0
    assert piece["corner_rotation_quarter_turns"] == 0


def test_l_with_one_millimetre_inner_band_accepts_the_raw_cavity():
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=Decimal("1"))
    errors, piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 81, 161),
        spec,
        width_cm=40,
        height_cm=80,
    )
    assert errors == []
    assert piece["corner_rotation_quarter_turns"] == 0
    assert piece["clipped_corner_width_cm"] == 8


def test_l_inner_band_rejects_a_cavity_that_ignores_its_thickness():
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=Decimal("1"))
    errors, piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 80, 161),
        spec,
        width_cm=40,
        height_cm=80,
    )
    assert [error.code for error in errors] == ["L_CORNER_NOTCH_MISMATCH"]
    assert "corner_rotation_quarter_turns" not in piece
    axis = errors[0].params["axes"]
    assert [item["axis"] for item in axis] == ["width"]
    assert axis[0]["finished_remaining_cm"] == "32.000"
    assert axis[0]["band_mm"] == "1"
    assert axis[0]["expected_raw_cm"] == "31.900"
    assert axis[0]["actual_raw_cm"] == "32.000"
    card = present_issue(errors[0])
    html = render_error_cards_html(errors)
    copy_target = _("Door {0} — copy {1}.").format(1, 1)
    assert card.target == _("{0} — L corner.").format(copy_target[:-1])
    assert card.problem == _("The L-corner dimensions in the DXF do not match the order.")
    assert "32 سم" in card.details[1]
    assert "1 مم" in card.details[2]
    assert "31.9 سم" in card.details[3]
    assert "32 سم" in card.details[4]
    assert "1 مم" in card.details[5]
    assert "زيادة" in card.details[5]
    assert "32" in card.highlight
    assert "31.9" in card.highlight
    assert "تفاصيل الاختلاف" in html
    assert "ما المشكلة؟" in html


def test_two_millimetre_inner_band_uses_its_own_thickness():
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=Decimal("2"))
    accepted, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 82, 162),
        spec,
        width_cm=40,
        height_cm=80,
    )
    rejected, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 80, 162),
        spec,
        width_cm=40,
        height_cm=80,
    )
    assert accepted == []
    assert rejected[0].params["axes"][0]["band_mm"] == "2"
    assert rejected[0].params["axes"][0]["expected_raw_cm"] == "31.800"
    assert "2 مم" in present_issue(rejected[0]).details[2]


def test_two_bands_on_one_axis_are_added_and_the_other_axis_is_not():
    spec = _l_contract(
        edge_break=1,
        edge_break_thickness_mm=Decimal("1"),
        cut_width_cm=Decimal("39.9"),
        width_deduction_mm=Decimal("1"),
        side_profiles=(
            {
                "side": "long_left",
                "side_label": "الطول الأيسر",
                "edge_type": "PVC",
                "thickness_mm": Decimal("1"),
            },
        ),
    )
    accepted, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 800, 81, 161),
        spec,
        width_cm=39.9,
        height_cm=80,
    )
    rejected, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 800, 80, 161),
        spec,
        width_cm=39.9,
        height_cm=80,
    )
    assert accepted == []
    axes = rejected[0].params["axes"]
    assert [item["axis"] for item in axes] == ["width"]
    assert axes[0]["band_mm"] == "2"
    assert axes[0]["expected_raw_cm"] == "31.800"
    assert axes[0]["actual_raw_cm"] == "31.900"


def test_bands_on_different_axes_are_not_added_onto_one_dimension():
    spec = _l_contract(
        cut_width_cm=Decimal("39.9"),
        cut_length_cm=Decimal("79.8"),
        width_deduction_mm=Decimal("1"),
        length_deduction_mm=Decimal("2"),
        side_profiles=(
            {
                "side": "long_left",
                "side_label": "الطول الأيسر",
                "edge_type": "PVC",
                "thickness_mm": Decimal("1"),
            },
            {
                "side": "width_top",
                "side_label": "العرض العلوي",
                "edge_type": "PVC",
                "thickness_mm": Decimal("2"),
            },
        ),
    )
    accepted, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 798, 80, 160),
        spec,
        width_cm=39.9,
        height_cm=79.8,
    )
    rejected, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 798, 83, 160),
        spec,
        width_cm=39.9,
        height_cm=79.8,
    )
    assert accepted == []
    card = present_issue(rejected[0])
    assert rejected[0].params["axes"][0]["axis"] == "width"
    assert rejected[0].params["axes"][0]["band_mm"] == "1"
    assert "على الطول" not in " ".join(card.details)
    assert "1 مم" in card.details[2]


def test_outer_notch_band_and_inner_band_are_not_deducted_twice():
    spec = _l_contract(
        edge_break=1,
        edge_break_thickness_mm=Decimal("1"),
        cut_width_cm=Decimal("39.9"),
        width_deduction_mm=Decimal("1"),
        side_profiles=(
            {
                "side": "long_right",
                "side_label": "الطول الأيمن",
                "edge_type": "PVC",
                "thickness_mm": Decimal("1"),
            },
        ),
    )
    accepted, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 800, 80, 161),
        spec,
        width_cm=39.9,
        height_cm=80,
    )
    rejected, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 399, 800, 81, 161),
        spec,
        width_cm=39.9,
        height_cm=80,
    )
    assert accepted == []
    assert rejected[0].params["axes"][0]["band_mm"] == "1"
    assert rejected[0].params["axes"][0]["expected_raw_cm"] == "31.900"
    assert "نقصان" in present_issue(rejected[0]).details[5]


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_raw_l_notch_matches_after_each_quarter_turn(turns):
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=Decimal("1"))
    ring = _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 81, 161)
    rotated, width_mm, height_mm = _turned(ring, turns)
    errors, piece = _import_l(
        rotated,
        spec,
        width_cm=width_mm / 10.0,
        height_cm=height_mm / 10.0,
    )
    assert errors == []
    assert piece["corner_mirrored"] == 0
    assert piece["corner_rotation_quarter_turns"] == turns


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_raw_l_notch_matches_after_a_mirror_and_each_quarter_turn(turns):
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=Decimal("1"))
    ring = [(point[0], point[1]) for point in _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 81, 161)]
    transformed, width_mm, height_mm = _mirror_then_turn(ring, turns)
    errors, piece = _import_l(
        transformed,
        spec,
        width_cm=width_mm / 10.0,
        height_cm=height_mm / 10.0,
    )
    assert errors == []
    assert piece["corner_mirrored"] == 1
    assert piece["corner_rotation_quarter_turns"] == turns


def test_unmatchable_corner_shape_keeps_the_geometric_error():
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=Decimal("1"))
    clipped = _mm_ring("Clipped Corner", "Bottom Right", 400, 800, 81, 161)
    errors, _piece = _import_l(clipped, spec, width_cm=40, height_cm=80)
    assert [error.code for error in errors] == ["CORNER_EDGE_UNRESOLVED"]
    assert errors[0].params["reason"] == "none"
    card = present_issue(errors[0])
    assert "دوران أو انعكاس" in card.problem
    assert card.details == ()
    assert "مقاس القص الخام" not in card.problem


def test_unproven_inner_thickness_does_not_show_a_guessed_deduction():
    spec = _l_contract(edge_break=1, edge_break_thickness_mm=None)
    errors, _piece = _import_l(
        _mm_ring("L-Shaped Corner", "Bottom Right", 400, 800, 80, 161),
        spec,
        width_cm=40,
        height_cm=80,
    )
    assert [error.code for error in errors] == ["CORNER_EDGE_UNRESOLVED"]
    assert errors[0].params["reason"] == "break_thickness_unknown"
    card = present_issue(errors[0])
    assert "غير معروفة" in card.problem
    assert card.details == ()
    assert "31.9" not in card.problem
    assert "1 مم" not in card.action


def test_failed_dxf_import_throws_before_replacing_the_saved_plan():
    root = Path(__file__).resolve().parents[1]
    source = (root / "almdina_erp" / "services" / "shop_floor_dxf_service.py").read_text(
        encoding="utf-8"
    )
    upload = source.split("def upload_production_dxf", 1)[1].split(
        "def recalculate_drawing_plan",
        1,
    )[0]
    rejected = upload.index("_throw_dxf_validation_errors(issues=getattr(error, \"issues\", None))")
    invalid = upload.index("if not validation.get(\"is_valid\")")
    persisted = upload.index("save_uploaded_dxf_plan(")
    assert rejected < persisted
    assert invalid < persisted


def test_clipped_regular_and_special_do_not_use_the_l_raw_notch():
    clipped = _l_contract(
        piece_type="Clipped Corner",
        edge_break=1,
        edge_break_thickness_mm=Decimal("2"),
    )
    regular = _l_contract(piece_type="Regular", edge_break=0)
    special = _l_contract(piece_type="Special", edge_break=1, edge_break_thickness_mm=Decimal("2"))
    assert _l_corner_cut(clipped) is None
    assert _l_corner_cut(regular) is None
    assert _l_corner_cut(special) is None
    assert _contour_notch_cm(clipped) == (8.0, 16.0)

    errors, piece = _import_l(
        _mm_ring("Clipped Corner", "Bottom Right", 400, 800, 80, 160),
        clipped,
        width_cm=40,
        height_cm=80,
    )
    assert errors == []
    assert piece["piece_type"] == "Clipped Corner"
    assert piece["clipped_corner_width_cm"] == 8
    assert piece["corner_rotation_quarter_turns"] == 0
