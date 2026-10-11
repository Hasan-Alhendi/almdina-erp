"""Corner DXF contours bind edge bands by geometry, not by the rotated flag."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting.corner_contour_rotation import (
    match_corner_contour,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import OrderPieceCutSpec
from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
    _apply_strict_dimension_contract,
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
    ambiguous = match_corner_contour(
        _POLYGONS[("L-Shaped Corner", "Top Right")],
        piece_type="L-Shaped Corner",
        position="Top Right",
        width_cm=40,
        length_cm=80,
        cut_width_cm=8,
        cut_length_cm=16,
        tolerance_mm=100,
    )

    assert mirror.reason == "none" and mirror.quarter_turns is None
    assert rectangle.reason == "none" and rectangle.quarter_turns is None
    assert ambiguous.reason == "ambiguous" and ambiguous.quarter_turns is None


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


def _order():
    return SimpleNamespace(
        pieces=[
            SimpleNamespace(
                piece_instance_id="piece:corner-1",
                extra_full_door_double=0,
                qty=1,
            )
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
    assert piece["rotated"] is (turns % 2 == 1)


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
    assert piece["rotated"] is False
