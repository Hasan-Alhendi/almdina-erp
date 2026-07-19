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
