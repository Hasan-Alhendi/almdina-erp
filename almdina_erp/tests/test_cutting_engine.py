from almdina_erp.almdina_erp.domain.cutting.evaluation import evaluate_plan
from almdina_erp.almdina_erp.services.cutting_engine import (
    PACKING_OPTIONS,
    choose_best_plan,
    expand_piece_groups,
    run_single_method,
    validate_plan,
)


def _sample_pieces():
    return expand_piece_groups(
        [
            {
                "width_cm": 50,
                "length_cm": 90,
                "qty": 3,
                "allow_rotation": 0,
            },
            {
                "width_cm": 30,
                "length_cm": 70,
                "qty": 2,
                "allow_rotation": 1,
            },
        ]
    )


def test_piece_expansion_labels_are_stable():
    pieces = _sample_pieces()
    assert [piece["label"] for piece in pieces] == ["1.1", "1.2", "1.3", "2.1", "2.2"]


def test_every_baseline_algorithm_returns_geometrically_valid_plan():
    pieces = _sample_pieces()
    for method in PACKING_OPTIONS[1:]:
        plan = run_single_method(pieces, 206, 279, 0.3, method)
        assert not plan["unplaced"], method
        assert not validate_plan(plan, pieces, 206, 279), method


def test_auto_is_deterministic_for_same_input():
    pieces = _sample_pieces()
    first = choose_best_plan(pieces, 206, 279, 0.3, "Auto")
    second = choose_best_plan(pieces, 206, 279, 0.3, "Auto")
    assert first["method_key"] == second["method_key"]
    assert first["score"] == second["score"]
    assert first["sheets"] == second["sheets"]


def test_rotation_is_never_used_when_not_allowed():
    pieces = expand_piece_groups(
        [
            {
                "width_cm": 80,
                "length_cm": 120,
                "qty": 2,
                "allow_rotation": 0,
            }
        ]
    )
    plan = choose_best_plan(pieces, 100, 250, 0.3, "Auto")
    for sheet in plan["sheets"]:
        for piece in sheet["pieces"]:
            assert piece["rotated"] is False
            assert piece["w"] == 80
            assert piece["h"] == 120


def test_validator_rejects_positive_area_overlap():
    pieces = expand_piece_groups(
        [
            {"width_cm": 50, "length_cm": 50, "qty": 2, "allow_rotation": 0},
        ]
    )
    plan = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {**pieces[0], "x": 0, "y": 0, "w": 50, "h": 50, "rotated": False},
                    {**pieces[1], "x": 25, "y": 25, "w": 50, "h": 50, "rotated": False},
                ],
            }
        ],
        "unplaced": [],
    }
    errors = validate_plan(plan, pieces, 100, 100)
    assert any("overlap" in error.lower() for error in errors)


def test_validator_rejects_piece_outside_usable_bounds():
    pieces = expand_piece_groups(
        [{"width_cm": 60, "length_cm": 60, "qty": 1, "allow_rotation": 0}]
    )
    plan = {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {**pieces[0], "x": 50, "y": 50, "w": 60, "h": 60, "rotated": False},
                ],
            }
        ],
        "unplaced": [],
    }
    errors = validate_plan(plan, pieces, 100, 100)
    assert any("bounds" in error.lower() or "exceeds" in error.lower() for error in errors)


def test_piece_larger_than_board_is_reported_unplaced():
    pieces = expand_piece_groups(
        [{"width_cm": 150, "length_cm": 120, "qty": 1, "allow_rotation": 1}]
    )
    plan = choose_best_plan(pieces, 100, 100, 0.3, "Auto")
    assert len(plan["unplaced"]) == 1
    errors = validate_plan(plan, pieces, 100, 100)
    assert errors


def test_edge_snapshot_survives_expansion_for_every_copy():
    pieces = expand_piece_groups(
        [
            {
                "width_cm": 40,
                "length_cm": 80,
                "qty": 2,
                "allow_rotation": 1,
                "edge_long_right": 1,
                "edge_long_left": 0,
                "edge_width_top": 1,
                "edge_width_bottom": 0,
                "edge_type": "قشاط 2سم عادي",
            }
        ]
    )
    assert len(pieces) == 2
    for piece in pieces:
        assert piece["edge_long_right"] == 1
        assert piece["edge_long_left"] == 0
        assert piece["edge_width_top"] == 1
        assert piece["edge_width_bottom"] == 0
        assert piece["edge_type"] == "قشاط 2سم عادي"


def test_special_door_raw_rectangles_and_preliminary_edges_survive_cutting_plan():
    pieces = expand_piece_groups(
        [
            {
                "width_cm": 75,
                "length_cm": 205,
                "qty": 2,
                "piece_type": "Special",
                "allow_rotation": 1,
                "edge_long_right": 1,
                "edge_long_left": 1,
                "edge_width_top": 1,
                "edge_width_bottom": 0,
                "edge_type": "قشاط 2سم عادي يدوي",
            }
        ]
    )

    assert len(pieces) == 2
    assert all(piece["piece_type"] == "Special" for piece in pieces)
    assert all(piece["edge_long_right"] == 1 for piece in pieces)
    assert all(piece["edge_long_left"] == 1 for piece in pieces)
    assert all(piece["edge_width_top"] == 1 for piece in pieces)

    plan = choose_best_plan(pieces, 206, 279, 0.3, "Auto")
    placed = [piece for sheet in plan["sheets"] for piece in sheet["pieces"]]

    assert len(placed) == 2
    assert all(piece["piece_type"] == "Special" for piece in placed)
    assert all(piece["edge_type"] == "قشاط 2سم عادي يدوي" for piece in placed)
    assert not plan["unplaced"]
    assert not validate_plan(plan, pieces, 206, 279)


def test_clipped_corner_geometry_survives_expansion_placement_and_rotation():
    pieces = expand_piece_groups(
        [
            {
                "width_cm": 80,
                "length_cm": 200,
                "qty": 1,
                "piece_type": "Clipped Corner",
                "clipped_corner_position": "Top Left",
                "clipped_corner_width_cm": 18,
                "clipped_corner_length_cm": 32,
                "allow_rotation": 1,
            }
        ]
    )
    assert pieces[0]["piece_type"] == "Clipped Corner"
    assert pieces[0]["clipped_corner_position"] == "Top Left"
    assert pieces[0]["clipped_corner_width_cm"] == 18
    assert pieces[0]["clipped_corner_length_cm"] == 32

    plan = choose_best_plan(pieces, 210, 90, 0.3, "Auto")
    placed = [piece for sheet in plan["sheets"] for piece in sheet["pieces"]]
    assert len(placed) == 1
    assert placed[0]["rotated"] is True
    assert placed[0]["clipped_corner_position"] == "Top Left"
    assert placed[0]["clipped_corner_width_cm"] == 18
    assert placed[0]["clipped_corner_length_cm"] == 32
    assert not validate_plan(plan, pieces, 210, 90)


def test_evaluated_plan_keeps_waste_at_the_top_and_shows_last_sheet_first():
    pieces = expand_piece_groups(
        [
            {"width_cm": 50, "length_cm": 80, "qty": 1, "allow_rotation": 0},
            {"width_cm": 40, "length_cm": 60, "qty": 1, "allow_rotation": 0},
        ]
    )
    raw = {
        "sheets": [
            {
                "sheet_no": 1,
                "w": 100,
                "h": 200,
                "pieces": [
                    {
                        **pieces[0],
                        "x": 0,
                        "y": 0,
                        "w": 50,
                        "h": 80,
                        "rotated": False,
                    }
                ],
                "free_rects": [{"x": 0, "y": 80, "w": 100, "h": 120}],
            },
            {
                "sheet_no": 2,
                "w": 100,
                "h": 200,
                "pieces": [
                    {
                        **pieces[1],
                        "x": 0,
                        "y": 0,
                        "w": 40,
                        "h": 60,
                        "rotated": False,
                    }
                ],
            },
        ],
        "unplaced": [],
    }

    plan = evaluate_plan(raw, pieces, 100, 200, "Test", "Test")

    assert [sheet["sheet_no"] for sheet in plan["sheets"]] == [2, 1]
    assert plan["sheets"][0]["pieces"][0]["y"] == 140
    assert plan["sheets"][1]["pieces"][0]["y"] == 120
    assert plan["sheets"][1]["free_rects"][0] == {"x": 0, "y": 0, "w": 100, "h": 120}
    assert not validate_plan(plan, pieces, 100, 200)


def test_packed_doors_sit_on_the_bottom_edge_of_the_usable_board():
    pieces = expand_piece_groups(
        [{"width_cm": 50, "length_cm": 40, "qty": 1, "allow_rotation": 0}]
    )
    plan = run_single_method(pieces, 100, 100, 0, "MaxRects Best Area")
    placed = plan["sheets"][0]["pieces"][0]

    assert placed["x"] == 0
    assert placed["y"] == 60
    assert placed["w"] == 50
    assert placed["h"] == 40
    assert not validate_plan(plan, pieces, 100, 100)


def test_last_opened_board_is_the_first_sheet_in_the_plan():
    pieces = expand_piece_groups(
        [{"width_cm": 90, "length_cm": 90, "qty": 2, "allow_rotation": 0}]
    )
    plan = run_single_method(pieces, 100, 100, 0, "MaxRects Best Area")

    assert [sheet["sheet_no"] for sheet in plan["sheets"]] == [2, 1]
    assert all(sheet["pieces"][0]["y"] == 10 for sheet in plan["sheets"])
    assert not validate_plan(plan, pieces, 100, 100)
