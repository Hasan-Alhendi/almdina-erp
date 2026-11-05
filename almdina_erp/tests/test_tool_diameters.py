from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import generate_toolpath
from almdina_erp.almdina_erp.domain.cutting.tool_diameters import (
    ToolDiameterError,
    diameters_for_record,
    explicit_diameter,
    export_tool_errors,
    initial_diameters,
    snapshot_tool_errors,
)


def _piece() -> LinerPiece:
    return LinerPiece("Regular", 40, 80)


def _ys(path) -> list[float]:
    return sorted({round(point[1], 3) for point in path})


def test_missing_layer_diameter_inherits_the_plan_kerf():
    resolved = diameters_for_record({"kerf_mm": 6})
    assert resolved["kerf_mm"] == 6
    assert resolved["liner_tool_diameter_mm"] == 6
    assert resolved["handle_recess_tool_diameter_mm"] == 6
    assert resolved["rear_groove_tool_diameter_mm"] == 6


def test_explicit_layer_diameter_does_not_replace_the_others():
    resolved = diameters_for_record({
        "kerf_mm": 6,
        "liner_tool_diameter_mm": 3,
        "handle_recess_tool_diameter_mm": 8,
        "rear_groove_tool_diameter_mm": 5,
    })
    assert resolved["kerf_mm"] == 6
    assert resolved["liner"] == 3
    assert resolved["recessed_handle_cutout"] == 8
    assert resolved["back_groove"] == 5


def test_non_positive_stored_diameter_inherits_kerf():
    resolved = diameters_for_record({
        "kerf_mm": 4,
        "liner_tool_diameter_mm": 0,
        "handle_recess_tool_diameter_mm": None,
    })
    assert resolved["liner_tool_diameter_mm"] == 4
    assert resolved["handle_recess_tool_diameter_mm"] == 4


def test_explicit_diameter_rejects_zero_and_blank_inherits():
    assert explicit_diameter(None, "liner_tool_diameter_mm") is None
    assert explicit_diameter("", "liner_tool_diameter_mm") is None
    assert explicit_diameter(3.5, "liner_tool_diameter_mm") == 3.5
    with pytest.raises(ToolDiameterError):
        explicit_diameter(0, "liner_tool_diameter_mm")
    with pytest.raises(ToolDiameterError):
        explicit_diameter(-1, "rear_groove_tool_diameter_mm")


def test_first_plan_uses_factory_then_cutting_diameter():
    seeded = initial_diameters(
        kerf_mm=6,
        factory={
            "default_liner_tool_diameter_mm": 3,
            "default_handle_recess_tool_diameter_mm": None,
            "default_rear_groove_tool_diameter_mm": 5,
        },
    )
    assert seeded["liner_tool_diameter_mm"] == 3
    assert seeded["handle_recess_tool_diameter_mm"] == 6
    assert seeded["rear_groove_tool_diameter_mm"] == 5


def test_lineage_ignores_later_factory_defaults():
    seeded = initial_diameters(
        kerf_mm=9,
        lineage={"kerf_mm": 6, "liner_tool_diameter_mm": 3},
        factory={"default_liner_tool_diameter_mm": 12, "default_rear_groove_tool_diameter_mm": 11},
    )
    assert seeded["liner_tool_diameter_mm"] == 3
    assert seeded["handle_recess_tool_diameter_mm"] == 6
    assert seeded["rear_groove_tool_diameter_mm"] == 6


def test_each_layer_path_uses_its_own_diameter():
    piece = _piece()
    liner = generate_toolpath(
        kind="liner", piece=piece, reference_side="edge_width_top",
        offset_cm=0, width_cm=1.8, start_cm=0, length_cm=40, cutter_diameter_mm=3,
    )
    handle = generate_toolpath(
        kind="recessed_handle_cutout", piece=piece, reference_side="edge_width_top",
        offset_cm=0, width_cm=1.8, start_cm=0, length_cm=40, cutter_diameter_mm=8,
    )
    groove = generate_toolpath(
        kind="back_groove", piece=piece, reference_side="edge_width_top",
        offset_cm=0, width_cm=1.8, start_cm=0, length_cm=40, cutter_diameter_mm=5,
    )
    assert _ys(liner) != _ys(handle)
    assert _ys(handle) != _ys(groove)
    assert min(point[0] for point in liner) == pytest.approx(-1.5)
    assert min(point[0] for point in handle) == pytest.approx(-4)
    wider = generate_toolpath(
        kind="liner", piece=piece, reference_side="edge_width_top",
        offset_cm=0, width_cm=1.8, start_cm=0, length_cm=40, cutter_diameter_mm=4,
    )
    assert _ys(wider) != _ys(liner)
    assert _ys(handle) == _ys(generate_toolpath(
        kind="recessed_handle_cutout", piece=piece, reference_side="edge_width_top",
        offset_cm=0, width_cm=1.8, start_cm=0, length_cm=40, cutter_diameter_mm=8,
    ))


def test_bit_wider_than_the_pocket_is_rejected():
    piece = _piece()
    with pytest.raises(LinerGeometryError) as caught:
        generate_toolpath(
            kind="back_groove", piece=piece, reference_side="edge_long_left",
            offset_cm=1, width_cm=0.4, start_cm=0, length_cm=20, cutter_diameter_mm=6,
        )
    assert caught.value.code == "liner_narrower_than_cutter"


def test_l_shaped_piece_still_uses_the_layer_diameter():
    piece = LinerPiece("L-Shaped Corner", 100, 80, "Top Right", 20, 30)
    path = generate_toolpath(
        kind="liner", piece=piece, reference_side="edge_break",
        offset_cm=1, width_cm=0.8, start_cm=0, length_cm=None, cutter_diameter_mm=4,
    )
    assert len(path) >= 2
    assert any(point[0] < 800 and point[1] > 300 for point in path)


def test_export_skips_special_pieces_and_persisted_centers():
    special = {
        "piece_type": "Special",
        "label": "S1",
        "w": 40,
        "h": 80,
        "extra_liner": 1,
        "liner_reference_side": "edge_width_top",
        "liner_width_cm": 1.8,
    }
    assert export_tool_errors(special, {"kerf_mm": 6, "liner": 3}) == []
    persisted = {
        "piece_type": "Regular",
        "label": "D1",
        "original_w": 40,
        "original_h": 80,
        "extra_liner": 1,
        "liner_reference_side": "edge_width_top",
        "liner_offset_cm": 0,
        "liner_width_cm": 0.4,
        "overlays": [{
            "kind": "liner",
            "geometry": {"path": [[0, 0], [10, 0]]},
        }],
    }
    assert export_tool_errors(persisted, {"kerf_mm": 6, "liner": 12}) == []


def test_export_rejects_a_generated_pocket_narrower_than_its_bit():
    piece = {
        "piece_type": "Regular",
        "label": "D2",
        "w": 40,
        "h": 80,
        "extra_back_groove": 1,
        "back_groove_reference_side": "edge_long_left",
        "back_groove_offset_cm": 1,
        "back_groove_width_cm": 0.4,
        "back_groove_start_cm": 0,
        "back_groove_length_cm": 20,
    }
    errors = snapshot_tool_errors(
        {"sheets": [{"pieces": [piece]}]},
        {"kerf_mm": 3, "back_groove": 6, "rear_groove_tool_diameter_mm": 6},
    )
    assert errors == [{
        "code": "liner_narrower_than_cutter",
        "kind": "back_groove",
        "label": "D2",
    }]
