"""Fixed-count remnant geometry, partial native repair and real DXF evidence."""
from copy import deepcopy
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import same_count_layout_search as search
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics, _largest_reusable_free_area
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, make_placed_piece, rect_intersects
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import plan_cut_line_quality

METRICS = dict(min_remnant_width_cm=1, min_remnant_length_cm=1, min_remnant_area_m2=.0001)


def fixture(kind="exchange", kerf=.5):
    if kind == "exchange":
        dims = [(4, 4), (4, 4), (2, 2), (5.5, 5.5)]
        positions = [[(0, 0, 0), (1, 0, 4.5)], [(2, 6, 6), (3, 0, 0)]]
    elif kind == "frontier":
        dims = [(4, 4), (2, 2), (4, 4), (4, 4)]
        positions = [[(0, 0, 0), (1, 6, 0)], [(2, 0, 0), (3, 4.5, 0)]]
    else:
        dims = [(1, 8), (3, 3), (3, 3)]
        positions = [[(0, 0, 0)], [(1, 0, 0), (2, 4, 0)]]
    rows = [dict(width_cm=w, length_cm=h, qty=1, piece_type="Regular", allow_rotation=0,
                 piece_instance_id=f"smart:{i}") for i, (w, h) in enumerate(dims, 1)]
    # Combine equal grid sources so the native family generator sees copies.
    if kind == "grid":
        rows = [rows[0], dict(rows[1], qty=2)]
    sources = expand_piece_groups(rows)
    sheets = [dict(sheet_no=j, w=10, h=10,
        pieces=[make_placed_piece(sources[i], x, y, sources[i]["width_cm"], sources[i]["length_cm"], False)
                for i, x, y in entries]) for j, entries in enumerate(positions, 1)]
    plan = enrich_plan_metrics(dict(sheets=sheets, unplaced=[]), "MaxRects Contact Point", "CNC Router", **METRICS)
    plan.update(kerf_cm=kerf, machine_type="CNC Router")
    assert not validate_plan(plan, sources, 10, 10, kerf_cm=kerf)
    return rows, sources, plan


def run(plan, sources, operator, **kwargs):
    return search.improve_fixed_board_layout(plan, sources, 10, 10, plan["kerf_cm"],
        deadline=float("inf"), policy=search.FixedBoardSearchPolicy(operators=(operator,), max_attempts=32),
        metric_kwargs=METRICS, **kwargs)


@pytest.mark.parametrize("operator", ["exchange", "frontier"])
def test_partial_neighborhood_grows_remnant_without_changing_board_count(operator):
    kerf = .5
    _, sources, plan = fixture(operator, kerf)
    original = deepcopy((sources, plan))
    candidates, trace = run(plan, sources, operator)
    before = plan["industrial_metrics"]["largest_reusable_free_area_m2"]
    assert any(p["industrial_metrics"]["largest_reusable_free_area_m2"] > before+1e-6 for p in candidates)
    assert trace["operators"][operator]["improvements"] > 0
    assert (sources, plan) == original
    for candidate in candidates:
        assert len(candidate["sheets"]) == len(plan["sheets"]) == 2
        assert not validate_plan(candidate, sources, 10, 10, kerf_cm=kerf)
        assert not placement_permission_errors(candidate, sources, mirroring_allowed=False)
        assert all(not p["rotated"] for s in candidate["sheets"] for p in s["pieces"])
        assert sorted(p["piece_instance_id"] for s in candidate["sheets"] for p in s["pieces"]) == sorted(p["piece_instance_id"] for p in sources)


def test_zero_kerf_native_touching_repair_fails_closed_with_original_spacing():
    # Existing independent geometry rejects this native zero-gap T-contact.
    # Keep the valid spaced incumbent; never certify touching proposals or
    # silently replace the caller's zero Kerf with a positive setting.
    _, sources, plan = fixture("exchange", 0)
    candidates, trace = run(plan, sources, "exchange")
    assert candidates == [plan]
    assert trace["operators"]["exchange"]["rejects"]["validation_failed"] > 0
    assert candidates[0]["kerf_cm"] == 0
    assert not validate_plan(candidates[0], sources, 10, 10, kerf_cm=0)


def test_grid_joins_real_cut_network_and_preserves_the_protected_rectangle():
    _, sources, plan = fixture("grid")
    region = search.largest_remnant_region(plan, machine_type="CNC Router", metric_kwargs=METRICS)
    candidates, trace = run(plan, sources, "grid")
    best = min(candidates, key=lambda p: plan_cut_line_quality(p, .5)[0])
    assert plan_cut_line_quality(best, .5)[0] < plan_cut_line_quality(plan, .5)[0]
    assert plan_cut_line_quality(best, .5)[1] <= plan_cut_line_quality(plan, .5)[1]
    assert best["sheets"][region.sheet_index]["pieces"] == plan["sheets"][region.sheet_index]["pieces"]
    assert not any(rect_intersects(p, region.rectangle()) for p in best["sheets"][region.sheet_index]["pieces"])
    assert trace["operators"]["grid"]["improvements"] > 0


@pytest.mark.parametrize("operator", search.OPERATORS)
def test_caps_and_incumbent_survive_failed_proposals(operator):
    _, sources, plan = fixture()
    candidates, trace = run(plan, sources, operator)
    assert candidates[0] == plan
    assert trace["attempts"] <= 32
    assert len(candidates) <= 5
    for candidate in candidates:
        assert len(candidate["sheets"]) == 2
        assert not validate_plan(candidate, sources, 10, 10, kerf_cm=.5)


def test_expired_deadline_cannot_start_repair(monkeypatch):
    _, sources, plan = fixture()
    monkeypatch.setattr(search, "find_best_position_maxrects", lambda *a, **k: pytest.fail("Packing after deadline"))
    candidates, trace = search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=time.monotonic()-1, metric_kwargs=METRICS)
    assert candidates == [plan]
    assert trace["attempts"] == 0


def test_completed_improvement_survives_cancellation():
    _, sources, plan = fixture()
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 3
    candidates, trace = run(plan, sources, "exchange", cancelled=cancel)
    assert trace["stop"] == "cancelled"
    assert any(p["industrial_metrics"]["largest_reusable_free_area_m2"] > .006 for p in candidates)


@pytest.mark.parametrize("marker", ["Glass", "L-Shaped Corner", "Clipped Corner", "Special", "OFFCUT", "geometry", "extra_liner"])
def test_protected_manufacturing_cohorts_are_not_moved(marker):
    _, sources, plan = fixture()
    p = plan["sheets"][0]["pieces"][0]
    if marker == "OFFCUT":
        p["resource_kind"] = marker
    elif marker in {"geometry", "extra_liner"}:
        p[marker] = {"points": [[0, 0], [4, 0], [4, 4]]} if marker == "geometry" else 1
    else:
        p["piece_type"] = marker
    candidates, trace = run(plan, sources, "exchange")
    assert candidates == [plan]
    assert trace["stop"] == "unsupported_cohort"


def test_panel_saw_is_exact_native_fallback():
    _, sources, plan = fixture()
    candidates, trace = run(plan, sources, "exchange", machine_type="Panel Saw")
    assert candidates == [plan]
    assert trace["stop"] == "unsupported_cohort"


def test_material_identity_ignores_equal_copy_swaps_but_validation_retains_ids():
    _, sources, plan = fixture("grid")
    trial = deepcopy(plan)
    a, b = trial["sheets"][1]["pieces"]
    for key in ("id", "piece_instance_id", "copy_no"):
        a[key], b[key] = b[key], a[key]
    assert search.material_signature(plan) == search.material_signature(trial)
    trial["sheets"][1]["pieces"][0]["x"] += .1
    assert search.material_signature(plan) != search.material_signature(trial)


def test_fixed_work_adaptive_trace_is_reproducible():
    _, sources, plan = fixture()
    policy = search.FixedBoardSearchPolicy(max_attempts=48, segment=2)
    results = [search.improve_fixed_board_layout(plan, sources, 10, 10, .5,
        deadline=float("inf"), policy=policy, metric_kwargs=METRICS) for _ in range(2)]
    assert [search.material_signature(p) for p in results[0][0]] == [search.material_signature(p) for p in results[1][0]]
    assert results[0][1]["events"] == results[1][1]["events"]
    assert results[0][1]["weights"] == results[1][1]["weights"]


@pytest.mark.parametrize("trim", [0, .3])
def test_partial_search_actual_application_export_strict_import(trim):
    from scripts.benchmark_alns import strict_check
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan)
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    rows, sources, plan = fixture()
    candidates, _ = run(plan, sources, "exchange")
    class Engine(DomainCuttingEngineAdapter):
        def optimize(self, *args, **kwargs):
            return dict(deepcopy(plan), smart_candidates=deepcopy(candidates))
    outcome = optimize_order_plan(OptimizeOrderPlanCommand("fixed-board", "fixed-board",
        BoardGeometry(10+2*trim, 10+2*trim, trim, .5),
        OptimizerOptions("smart", "CNC Router", 1, 40, 1, 1, .0001, alignment_search_budget_sec=0),
        tuple(rows)), engine=Engine())
    assert outcome.snapshot["validation"]["is_valid"]
    assert len(outcome.snapshot["sheets"]) == 2
    assert outcome.snapshot["trim_cm"] == trim
    assert outcome.snapshot["industrial_metrics"]["largest_reusable_free_area_m2"] >= .008-1e-8
    for candidate in outcome.candidate_snapshots:
        assert strict_check(candidate, rows)
