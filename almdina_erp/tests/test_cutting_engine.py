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
