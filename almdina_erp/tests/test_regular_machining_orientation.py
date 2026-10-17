"""Pure tests for machining-driven rectangular DXF orientation."""
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece, liner_strip_polygon_mm, transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.regular_machining_orientation import (
    match_regular_machining_orientation,
    physical_edge_tokens,
)


def test_physical_edge_tokens_all_quarter_turns():
    bands = {"left": "L", "top": "T", "right": "R", "bottom": "B"}
    assert physical_edge_tokens(bands, 0) == ("L", "T", "R", "B")
    assert physical_edge_tokens(bands, 1) == ("B", "L", "T", "R")
    assert physical_edge_tokens(bands, 2) == ("R", "B", "L", "T")
    assert physical_edge_tokens(bands, 3) == ("T", "R", "B", "L")


def test_all_three_addons_share_all_four_rotations():
    door = LinerPiece("Regular", 54.9, 100)
    specs = {
        "liner": {"enabled": True, "side": "edge_long_right", "offset_cm": 10, "width_cm": 1.8},
        "back_groove": {"enabled": True, "side": "edge_long_left", "offset_cm": 0.5, "width_cm": 0.7},
        "recessed_handle_cutout": {"enabled": True, "side": "edge_width_bottom", "offset_cm": 13, "width_cm": 2},
    }
    originals = {
        kind: liner_strip_polygon_mm(door, value["side"], value["offset_cm"], value["width_cm"])
        for kind, value in specs.items()
    }
    for turns in range(4):
        rotated = {
            kind: [
                transform_point(p, mirrored=False, quarter_turns=turns, width=549, height=1000)
                for p in path
            ]
            for kind, path in originals.items()
        }
        matched = match_regular_machining_orientation(
            piece=door,
            overlay_paths=rotated,
            settings=specs,
            candidate_turns=(0, 2) if turns % 2 == 0 else (1, 3),
            edge_bands={"left": "0", "top": "0", "right": "PVC:1", "bottom": "0"},
            cutter_diameter_mm=5,
        )
        assert matched.reason == "unique", (turns, matched)
        assert matched.quarter_turns == turns


def test_one_extra_rotated_differently_rejects_combination():
    door = LinerPiece("Regular", 54.9, 100)
    specs = {
        "liner": {"enabled": True, "side": "edge_long_right", "offset_cm": 10, "width_cm": 1.8},
        "back_groove": {"enabled": True, "side": "edge_long_left", "offset_cm": 0.5, "width_cm": 0.7},
    }
    original = {
        kind: liner_strip_polygon_mm(door, value["side"], value["offset_cm"], value["width_cm"])
        for kind, value in specs.items()
    }
    rotated = {
        "liner": [transform_point(p, mirrored=False, quarter_turns=1, width=549, height=1000) for p in original["liner"]],
        "back_groove": original["back_groove"],
    }
    result = match_regular_machining_orientation(
        piece=door, overlay_paths=rotated, settings=specs,
        candidate_turns=(1, 3), edge_bands={}, cutter_diameter_mm=5,
    )
    assert result.reason == "invalid"
    assert result.quarter_turns is None


def test_no_machining_evidence_does_not_invent_half_turn():
    result = match_regular_machining_orientation(
        piece=LinerPiece("Regular", 40, 60), overlay_paths={},
        settings={}, candidate_turns=(0, 2),
        edge_bands={"left": "PVC", "right": "0"},
        cutter_diameter_mm=5,
    )
    assert result.reason == "no_machining_evidence"
    assert result.quarter_turns is None
