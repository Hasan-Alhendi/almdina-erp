from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

from almdina_erp.almdina_erp.domain.cutting import (
    AUTO_PRO,
    DEEP_SEARCH,
    OPTIMAL_SEARCH,
    expand_piece_groups,
    optimize_plan,
    validate_plan,
)
from almdina_erp.almdina_erp.domain.cutting import optimizer
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece


def _selection_pieces():
    return expand_piece_groups([
        {"width_cm": 10, "length_cm": 20, "qty": 8, "allow_rotation": 0},
    ])


def _selection_plan(pieces, counts, *, scattered=False, label="baseline"):
    sheets = []
    cursor = 0
    for sheet_no, count in enumerate(counts, 1):
        placed = [
            make_placed_piece(
                source, (40 if scattered else 0) + index * 10.5,
                40 if scattered else 0, source["width_cm"], source["length_cm"], False,
            )
            for index, source in enumerate(pieces[cursor:cursor + count])
        ]
        cursor += count
        sheets.append({"sheet_no": sheet_no, "w": 100, "h": 100, "pieces": placed})
    assert cursor == len(pieces)
    return {
        "sheets": sheets, "unplaced": [], "method_key": "MaxRects Best Short Side",
        "optimization_mode": AUTO_PRO, "attempts": 123,
        "solver_status": label, "industrial_rank": (0, 0),
        "shape_nesting_diagnostics": {"outcome": label},
    }


def _select_plans(pieces, baseline, nested, shaped, improved, **kwargs):
    # Inject only search results; use the real metrics and independent validators.
    with ExitStack() as stack:
        for target, plan in (
            ("optimizer.auto_fast", baseline),
            ("glass_opening_nesting.nest_glass_openings", nested),
            ("shape_aware_nesting.apply_shape_aware_nesting", shaped),
            ("plan_search.improve_plan_search", improved),
        ):
            stack.enter_context(patch(
                "almdina_erp.almdina_erp.domain.cutting." + target, return_value=plan,
            ))
        return optimize_plan(pieces, 100, 100, 0.3, **kwargs)


def test_final_selection_never_trades_four_boards_for_five():
    pieces = _selection_pieces()
    baseline = _selection_plan(pieces, [2, 2, 2, 2])
    worse = _selection_plan(pieces, [2, 2, 2, 1, 1], label="rejected_quad")
    result = _select_plans(pieces, baseline, baseline, worse, worse)
    assert len(result["sheets"]) == 4
    assert result["industrial_metrics"]["board_count"] == 4
    assert result["solver_status"] == "baseline"
    assert result["shape_nesting_diagnostics"] == {"outcome": "baseline"}


def test_search_recovers_three_boards_from_the_best_previous_valid_plan():
    pieces = _selection_pieces()
    baseline = _selection_plan(pieces, [2, 2, 2, 2])
    shaped = _selection_plan(pieces, [2, 2, 2, 1, 1], label="shaped")
    recovered = _selection_plan(pieces, [3, 3, 2], label="recovered")
    prefix = "almdina_erp.almdina_erp.domain.cutting."

    def search(plan, *args, **kwargs):
        return shaped if len(plan["sheets"]) == 5 else recovered

    with patch(prefix + "optimizer.auto_fast", return_value=baseline), patch(
        prefix + "glass_opening_nesting.nest_glass_openings", return_value=baseline,
    ), patch(prefix + "shape_aware_nesting.apply_shape_aware_nesting", return_value=shaped), patch(
        prefix + "plan_search.improve_plan_search", side_effect=search,
    ) as searches:
        result = optimize_plan(pieces, 100, 100, 0.3)
    assert len(result["sheets"]) == 3
    assert result["solver_status"] == "recovered"
    assert not validate_plan(result, pieces, 100, 100, kerf_cm=0.3)
    assert searches.call_count == 2
    assert [len(call.args[0]["sheets"]) for call in searches.call_args_list] == [5, 4]
    assert 0 < searches.call_args_list[1].kwargs["time_limit_sec"] <= 1


def test_board_cancellation_tries_a_second_destination_order():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search

    pieces = expand_piece_groups([
        {"width_cm": width, "length_cm": height, "qty": 1, "allow_rotation": 0}
        for width, height in ((100, 38.5), (38.5, 61), (100, 38.5), (58.5, 61), (40, 60), (60, 30))
    ])
    sheets = []
    for sheet_no, (sources, spots) in enumerate((
        (pieces[:2], ((0, 0), (0, 38.8))),
        (pieces[2:4], ((0, 0), (0, 38.8))),
        (pieces[4:], ((0, 0), (0, 60.3))),
    ), 1):
        # The victim's two pieces need separate destination boards: putting
        # the 40x60 piece in the 61.2x61.2 gap blocks the later 60x30 piece.
        sheets.append({"sheet_no": sheet_no, "w": 100, "h": 100, "pieces": [
            make_placed_piece(piece, x, y, piece["width_cm"], piece["length_cm"], False)
            for piece, (x, y) in zip(sources, spots, strict=True)
        ]})
    plan = optimizer.enrich_plan_metrics(
        {"sheets": sheets, "unplaced": [], "method_key": "MaxRects Best Short Side"},
        "MaxRects Best Short Side", "CNC Router",
    )
    assert not validate_plan(plan, pieces, 100, 100, kerf_cm=0.3)
    result = improve_plan_search(
        plan, pieces, 100, 100, 0.3, machine_type="CNC Router", time_limit_sec=2,
        min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=0.09,
    )
    assert len(result["sheets"]) == 2
    assert not validate_plan(result, pieces, 100, 100, kerf_cm=0.3)
    assert not placement_permission_errors(result, pieces, mirroring_allowed=False)


def test_alternative_search_respects_budget_and_rejects_invalid_results():
    pieces = _selection_pieces()
    baseline = _selection_plan(pieces, [2, 2, 2, 2])
    shaped = _selection_plan(pieces, [2, 2, 2, 1, 1], label="shaped")
    invalid = _selection_plan(pieces, [3, 3, 2], label="invalid_alternative")
    invalid["sheets"][0]["pieces"][1]["x"] = 0
    prefix = "almdina_erp.almdina_erp.domain.cutting."
    for clock, expected_calls in (([100, 100, 100, 111], 1), ([100, 100, 100, 101, 101], 2)):
        with patch(prefix + "optimizer.auto_fast", return_value=baseline), patch(
            prefix + "glass_opening_nesting.nest_glass_openings", return_value=baseline,
        ), patch(prefix + "shape_aware_nesting.apply_shape_aware_nesting", return_value=shaped), patch(
            prefix + "plan_search.improve_plan_search", side_effect=[shaped, invalid],
        ) as searches, patch.object(optimizer.time, "monotonic", side_effect=clock):
            result = optimize_plan(pieces, 100, 100, 0.3)
        assert searches.call_count == expected_calls
        assert len(result["sheets"]) == 4
        assert result["solver_status"] == "baseline"
        assert not validate_plan(result, pieces, 100, 100, kerf_cm=0.3)


def test_expired_plan_search_deadline_does_not_start_work():
    from almdina_erp.almdina_erp.domain.cutting.plan_search import improve_plan_search

    pieces = _selection_pieces()
    plan = _selection_plan(pieces, [2, 2, 2, 2])
    with patch(
        "almdina_erp.almdina_erp.domain.cutting.nesting_consolidation.consolidate_nested_boards",
    ) as consolidate:
        result = improve_plan_search(
            plan, pieces, 100, 100, 0.3, machine_type="CNC Router", time_limit_sec=10,
            min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=0.09,
            deadline_monotonic=optimizer.time.monotonic() - 1,
        )
    assert result is plan
    consolidate.assert_not_called()


def test_final_selection_keeps_the_best_valid_result_from_every_stage():
    pieces = _selection_pieces()
    baseline = _selection_plan(pieces, [2, 2, 2, 2])
    better = _selection_plan(pieces, [3, 3, 2], label="three_boards")
    worse = _selection_plan(pieces, [2, 2, 2, 1, 1], label="five_boards")
    for winner in range(4):
        candidates = [baseline, worse, worse, worse]
        candidates[winner] = better
        result = _select_plans(pieces, *candidates)
        assert len(result["sheets"]) == 3
        assert not validate_plan(result, pieces, 100, 100, kerf_cm=0.3)
        assert result["solver_status"] == "three_boards"
        assert result["optimization_mode"] == AUTO_PRO
        assert result["attempts"] == 123


def test_final_selection_uses_reusable_offcut_and_configured_thresholds():
    pieces = _selection_pieces()
    scattered = _selection_plan(pieces, [2, 2, 2, 2], scattered=True)
    compact = _selection_plan(pieces, [2, 2, 2, 2], label="compact")
    for minimum, expected_area in ((30, 0.8), (90, 0.0)):
        result = _select_plans(
            pieces, scattered, compact, scattered, scattered,
            min_remnant_width_cm=minimum, min_remnant_length_cm=minimum,
        )
        assert len(result["sheets"]) == 4
        assert result["solver_status"] == "compact"
        assert result["industrial_metrics"]["largest_reusable_free_area_m2"] == expected_area


def test_final_selection_rejects_invalid_apparent_improvements():
    pieces = _selection_pieces()
    baseline = _selection_plan(pieces, [2, 2, 2, 2])
    for fault in ("overlap", "kerf", "missing", "duplicate", "unplaced", "rotation", "mirror"):
        invalid = _selection_plan(pieces, [3, 3, 2], label=fault)
        first, second = invalid["sheets"][0]["pieces"][:2]
        if fault == "overlap":
            second["x"] = first["x"]
        elif fault == "kerf":
            second["x"] = first["x"] + first["w"] + 0.1
        elif fault == "missing":
            invalid["sheets"][-1]["pieces"].pop()
        elif fault == "duplicate":
            second["id"] = first["id"]
        elif fault == "unplaced":
            invalid["unplaced"] = [pieces[0]]
        elif fault == "rotation":
            first.update(rotated=True, w=20, h=10)
            second["x"] = 25
        else:
            first["placement_mirrored"] = True
        assert validate_plan(invalid, pieces, 100, 100, kerf_cm=0.3) or placement_permission_errors(
            invalid, pieces, mirroring_allowed=False,
        )
        result = _select_plans(pieces, baseline, invalid, invalid, invalid)
        assert len(result["sheets"]) == 4, fault
        assert result["solver_status"] == "baseline", fault


def test_search_can_pass_through_a_worse_plan_without_mutating_saved_candidates():
    pieces = _selection_pieces()
    baseline = _selection_plan(pieces, [2, 2, 2, 2])
    original = deepcopy(baseline)

    def shape(plan, *args, **kwargs):
        plan["shape_nesting_diagnostics"] = {"outcome": "rejected"}
        return _selection_plan(pieces, [2, 2, 2, 1, 1])

    def search(plan, *args, **kwargs):
        assert len(plan["sheets"]) == 5
        return _selection_plan(pieces, [3, 3, 2], label="recovered")

    prefix = "almdina_erp.almdina_erp.domain.cutting."
    with patch(prefix + "optimizer.auto_fast", return_value=baseline), patch(
        prefix + "glass_opening_nesting.nest_glass_openings", side_effect=lambda plan, *a, **k: plan,
    ), patch(prefix + "shape_aware_nesting.apply_shape_aware_nesting", side_effect=shape), patch(
        prefix + "plan_search.improve_plan_search", side_effect=search,
    ):
        result = optimize_plan(pieces, 100, 100, 0.3)
    assert len(result["sheets"]) == 3
    assert baseline == original


def test_final_selection_does_not_trade_boards_for_glass_guests():
    pieces = expand_piece_groups([
        {"piece_type": "Glass", "width_cm": 40, "length_cm": 40,
         "glass_margin_mm": 50, "qty": 1, "allow_rotation": 0},
        {"width_cm": 20, "length_cm": 20, "qty": 1, "allow_rotation": 0},
        {"width_cm": 10, "length_cm": 10, "qty": 1, "allow_rotation": 0},
    ])
    baseline = {
        "method_key": "MaxRects Best Short Side", "unplaced": [],
        "sheets": [{"sheet_no": 1, "w": 100, "h": 100, "pieces": [
            make_placed_piece(source, x, 0, source["width_cm"], source["length_cm"], False)
            for source, x in zip(pieces, (0, 50, 80), strict=True)
        ]}],
    }
    nested = deepcopy(baseline)
    host, guest, other = nested["sheets"][0]["pieces"]
    guest.update(x=10, y=10, glass_host_piece_id=host["id"])
    nested["sheets"][0]["pieces"] = [host, guest]
    nested["sheets"].append({"sheet_no": 2, "w": 100, "h": 100, "pieces": [other]})
    nested["glass_nesting_diagnostics"] = {"outcome": "accepted"}
    assert not validate_plan(nested, pieces, 100, 100, kerf_cm=0.3)
    result = _select_plans(pieces, baseline, nested, nested, nested)
    assert len(result["sheets"]) == 1
    assert "glass_nesting_diagnostics" not in result


def test_final_selection_reuses_proven_identical_layout_and_keeps_ties():
    pieces = _selection_pieces()
    plans = [_selection_plan(pieces, [2, 2, 2, 2], label=str(i)) for i in range(4)]
    with patch.object(optimizer, "validate_plan", wraps=validate_plan) as validate:
        result = _select_plans(pieces, *plans)
    assert validate.call_count == 1
    assert result["solver_status"] == "3"


def test_final_selection_validates_all_four_distinct_tied_layouts():
    pieces = _selection_pieces()
    plans = [_selection_plan(pieces, [2, 2, 2, 2], label=str(i)) for i in range(4)]
    # These translations preserve the board count, largest free rectangle,
    # cut-line count/length and permissions, but each geometry is distinct.
    for index, plan in enumerate(plans):
        for sheet in plan["sheets"]:
            for piece in sheet["pieces"]:
                piece["x"] += 20 + index
    with patch.object(optimizer, "validate_plan", wraps=validate_plan) as validate:
        result = _select_plans(pieces, *plans)
    assert validate.call_count == 4
    assert result["solver_status"] == "3"


def test_no_valid_candidate_preserves_baseline_failure_for_adaptive_trim():
    pieces = _selection_pieces()
    incomplete = _selection_plan(pieces, [2, 2, 2, 2])
    incomplete["unplaced"] = [incomplete["sheets"][-1]["pieces"].pop()]
    result = _select_plans(pieces, incomplete, incomplete, incomplete, incomplete)
    assert result is incomplete
    assert validate_plan(result, pieces, 100, 100, kerf_cm=0.3)


def _pieces():
    return expand_piece_groups(
        [
            {"width_cm": 50, "length_cm": 90, "qty": 3, "allow_rotation": 0},
            {"width_cm": 30, "length_cm": 70, "qty": 2, "allow_rotation": 1},
            {"width_cm": 22, "length_cm": 40, "qty": 4, "allow_rotation": 1},
        ]
    )


def test_dimension_cycles_save_boards_in_final_plans():
    for counts, maximum in (((4, 3, 1), 1), ((36, 36, 48), 11)):
        pieces = expand_piece_groups([
            {"width_cm": w, "length_cm": h, "qty": n, "allow_rotation": rotation}
            for (w, h, rotation), n in zip(((50, 90, 0), (30, 70, 1), (22, 40, 1)), counts)
        ])
        plan = optimize_plan(
            pieces, 122, 244, 0.3, selected_mode=AUTO_PRO,
            machine_type="CNC Router", time_limit_sec=2,
        )
        assert len(plan["sheets"]) <= maximum
        assert not validate_plan(plan, pieces, 122, 244, kerf_cm=0.3)
        assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)
        assert sorted(p["id"] for s in plan["sheets"] for p in s["pieces"]) == [p["id"] for p in pieces]


def test_dimension_cycles_are_bounded_and_preserve_input_and_permissions():
    pieces = _pieces()
    original = deepcopy(pieces)
    cycles = [sequence for name, sequence in optimizer._local_sequences({"sheets": []}, pieces)
              if name.startswith("dimension_cycle_")]
    assert len(cycles) == 3
    expected = {p["id"]: p for p in original}
    for sequence in cycles:
        assert len(sequence) == len(original)
        assert {p["id"]: p for p in sequence} == expected
    assert pieces == original
    pieces[0]["piece_type"] = "L-Shaped Corner"
    assert not any(name.startswith("dimension_cycle_")
                   for name, _ in optimizer._local_sequences({"sheets": []}, pieces))


def test_auto_pro_is_valid_and_tracks_industrial_metrics():
    pieces = _pieces()
    plan = optimize_plan(pieces, 121, 243, 0.3, selected_mode=AUTO_PRO)
    assert not validate_plan(plan, pieces, 121, 243)
    assert plan["optimization_mode"] == AUTO_PRO
    assert plan["attempts"] > 17
    metrics = plan["industrial_metrics"]
    assert metrics["estimated_cut_count"] >= 0
    assert metrics["estimated_cut_length_cm"] >= 0
    assert metrics["largest_reusable_free_area_m2"] >= 0


def test_auto_pro_never_uses_more_boards_than_fast_auto_on_same_case():
    pieces = _pieces()
    fast = optimize_plan(pieces, 121, 243, 0.3, selected_mode="Auto")
    pro = optimize_plan(pieces, 121, 243, 0.3, selected_mode=AUTO_PRO)
    assert len(pro["unplaced"]) <= len(fast["unplaced"])
    if len(pro["unplaced"]) == len(fast["unplaced"]):
        assert len(pro["sheets"]) <= len(fast["sheets"])


def test_panel_saw_auto_pro_restricts_result_to_guillotine_family():
    pieces = _pieces()
    plan = optimize_plan(
        pieces,
        121,
        243,
        0.3,
        selected_mode=AUTO_PRO,
        machine_type="Panel Saw",
    )
    assert plan["method_key"].startswith("Guillotine")
    assert plan["industrial_metrics"]["panel_saw_non_guillotine_penalty"] == 0
    assert not validate_plan(plan, pieces, 121, 243)


def test_deep_search_is_valid_and_respects_time_budget_metadata():
    pieces = _pieces()
    plan = optimize_plan(
        pieces,
        121,
        243,
        0.3,
        selected_mode=DEEP_SEARCH,
        time_limit_sec=0.75,
    )
    assert plan["optimization_mode"] == DEEP_SEARCH
    assert plan["search_time_limit_sec"] == 0.75
    assert plan["attempts"] > 0
    assert not validate_plan(plan, pieces, 121, 243)


def test_optimal_search_returns_valid_plan_and_solver_status():
    pieces = expand_piece_groups(
        [
            {"width_cm": 50, "length_cm": 50, "qty": 4, "allow_rotation": 1},
        ]
    )
    plan = optimize_plan(
        pieces,
        100,
        100,
        0.3,
        selected_mode=OPTIMAL_SEARCH,
        machine_type="CNC Router",
        time_limit_sec=3,
        exact_piece_limit=20,
    )
    assert plan["optimization_mode"] == OPTIMAL_SEARCH
    assert plan.get("solver_status") in {"OPTIMAL", "FEASIBLE", "HEURISTIC_FALLBACK"}
    assert not validate_plan(plan, pieces, 100, 100)


def test_panel_saw_optimal_search_does_not_claim_non_guillotine_exactness():
    pieces = _pieces()
    plan = optimize_plan(
        pieces,
        121,
        243,
        0.3,
        selected_mode=OPTIMAL_SEARCH,
        machine_type="Panel Saw",
        time_limit_sec=0.75,
    )
    assert plan["solver_status"] == "GUILLOTINE_DEEP_SEARCH"
    assert plan["method_key"].startswith("Guillotine")
    assert not validate_plan(plan, pieces, 121, 243)
