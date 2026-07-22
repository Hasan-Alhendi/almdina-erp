from __future__ import annotations

from almdina_erp.almdina_erp.services.advanced_cutting_optimizer import (
    AUTO_PRO,
    DEEP_SEARCH,
    OPTIMAL_SEARCH,
    optimize_plan,
)
from almdina_erp.almdina_erp.services.cutting_engine import expand_piece_groups, validate_plan


def _pieces():
    return expand_piece_groups(
        [
            {"width_cm": 50, "length_cm": 90, "qty": 3, "allow_rotation": 0},
            {"width_cm": 30, "length_cm": 70, "qty": 2, "allow_rotation": 1},
            {"width_cm": 22, "length_cm": 40, "qty": 4, "allow_rotation": 1},
        ]
    )


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
