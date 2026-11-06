"""Opt-in ABC: real geometry, bounded work, native fallback and final ranking."""
from copy import deepcopy
import time

import pytest

from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.abc_search import (
    ABCSearchPolicy, ABCSearchSession, LocalPackingBudget,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.regular_templates import regular_template_candidates


METRICS = dict(min_remnant_width_cm=50, min_remnant_length_cm=50, min_remnant_area_m2=.25)


def grid_problem():
    sources = expand_piece_groups([dict(width_cm=29.9, length_cm=78.8, qty=8,
                                        piece_instance_id="smart:1", allow_rotation=0)])
    plan = dict(sheets=[dict(sheet_no=i+1, w=122, h=244, marker=i,
        pieces=[make_placed_piece(p, 0, 0, 29.9, 78.8, False)]) for i, p in enumerate(sources)], unplaced=[])
    return sources, opt.enrich_plan_metrics(plan, "MaxRects Contact Point", "CNC Router", **METRICS)


def session(policy, sources, width, height, kerf=.5, deadline=None):
    return ABCSearchSession(policy, sources, width, height, kerf, "CNC Router", False,
                            METRICS, time.monotonic()+60 if deadline is None else deadline)


@pytest.mark.parametrize("kerf", [0, .3, .5])
def test_templates_discover_grid_from_dimensions_only_without_double_kerf(kerf):
    sources, original = grid_problem()
    frozen, source_copy = deepcopy(original), deepcopy(sources)
    budget = LocalPackingBudget()
    generated = list(regular_template_candidates(original, sources, 122, 244, kerf,
                                                budget=budget, deadline=time.monotonic()+5))
    plans = [p for p in generated if p is not None]
    assert plans and budget.counts["templates"] <= 6
    grid = plans[0]
    assert len(grid["sheets"]) == 1
    pieces = grid["sheets"][0]["pieces"]
    assert len({round(p["x"], 6) for p in pieces}) == 4
    assert len({round(p["y"], 6) for p in pieces}) == 2
    assert max(p["x"]+p["w"] for p in pieces) == pytest.approx(4*29.9+3*kerf)
    assert max(p["y"] for p in pieces)-min(p["y"] for p in pieces) == pytest.approx(78.8+kerf)
    assert not validate_plan(grid, sources, 122, 244, kerf_cm=kerf)
    assert not placement_permission_errors(grid, sources, mirroring_allowed=False)
    assert grid["used_area_m2"] == pytest.approx(sum(p["area_m2"] for p in sources))
    assert {p["piece_instance_id"] for p in pieces} == {p["piece_instance_id"] for p in sources}
    assert all(not p["rotated"] for p in pieces)
    assert original == frozen and sources == source_copy
    assert grid["sheets"][0]["marker"] == 0


@pytest.mark.parametrize("key,value", [("piece_type", "Glass"), ("resource_kind", "OFFCUT"),
    ("extra_liner", True), ("geometry", {"version": 2}), ("overlays", [{}]),
    ("placement_mirrored", True)])
def test_protected_sources_do_not_start_optional_packing(key, value):
    sources, plan = grid_problem()
    sources[0][key] = value
    state = session(ABCSearchPolicy(True, True, True), sources, 122, 244)
    state.run(plan, lambda _: pytest.fail("protected proposal published"), 5)
    assert sum(state.budget.counts.values()) == 0
    assert state.trace["reason"] == "unsupported"


def route_problem():
    sources = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=1),
                                  dict(width_cm=30, length_cm=30, qty=1)])
    def plan(x, y):
        value = dict(sheets=[dict(sheet_no=1, w=40, h=100, pieces=[
            make_placed_piece(p, x, y+dy, p["width_cm"], 30, False)
            for p, dy in zip(sources, [0, 30.5])])], unplaced=[], complexity=3)
        return opt.enrich_plan_metrics(value, "MaxRects Bottom Left", "CNC Router", **METRICS)
    return sources, [plan(0, i) for i in range(5)], plan(.65, 0)


def test_side_pool_keeps_real_route_despite_worse_legacy_estimate_and_is_detached():
    sources, native, route = route_problem()
    assert all(p["industrial_rank"] < route["industrial_rank"] for p in native)
    state = session(ABCSearchPolicy(retention=True), sources, 40, 100)
    for p in native:
        assert not validate_plan(p, sources, 40, 100, kerf_cm=.5)
        state.observe_valid(p)
    state.observe_valid(route)
    result = state.nominee(native)
    assert result is not None and geometry_signature(result) == geometry_signature(route)
    route["sheets"][0]["pieces"][0]["x"] = 999
    assert result["sheets"][0]["pieces"][0]["x"] == .65
    assert len(state.pool) <= 3 and state.profiles <= 12


@pytest.mark.parametrize("fault", ["missing", "duplicate", "kerf", "rotation", "unplaced", "extra_board"])
def test_invalid_proposals_never_enter_side_pool(fault):
    sources, native, route = route_problem()
    state = session(ABCSearchPolicy(retention=True), sources, 40, 100)
    state.observe_valid(native[0])
    if fault == "missing": route["sheets"][0]["pieces"].pop()
    elif fault == "duplicate": route["sheets"][0]["pieces"][1]["id"] = sources[0]["id"]
    elif fault == "kerf": route["sheets"][0]["pieces"][1]["y"] = 20
    elif fault == "rotation": route["sheets"][0]["pieces"][1]["rotated"] = True
    elif fault == "unplaced": route["unplaced"] = [sources[0]]
    else: route["sheets"].append(dict(sheet_no=2, w=40, h=100, pieces=[]))
    assert state.consider(route, deadline=state.deadline) is None
    assert state.nominee(native) is None


def test_expired_validation_does_not_certify_a_proposal():
    sources, native, route = route_problem()
    state = session(ABCSearchPolicy(retention=True), sources, 40, 100)
    state.observe_valid(native[0])
    assert state.consider(route, deadline=0) is None
    assert state.nominee(native) is None


def test_local_budget_is_shared_between_actual_regroup_and_templates():
    from almdina_erp.tests.test_board_regrouping import golden
    sources_plan, sources, _, case = golden()
    state = session(ABCSearchPolicy(True, True, True), sources, case["width"], case["height"])
    state.observe_valid(sources_plan)
    state.run(sources_plan, lambda _: None, 30)
    assert 0 < state.budget.counts["regroup"]
    assert 0 < state.budget.counts["templates"] <= 6
    assert sum(state.budget.counts.values()) <= 24


def test_default_and_disabled_policy_keep_identical_fixed_work_search(monkeypatch):
    sources = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=4)])
    original = opt._run_preordered_method
    work = [0]
    def counted(*args, **kwargs):
        result = original(*args, **kwargs)
        work[0] += 1
        return result
    monkeypatch.setattr(opt, "_run_preordered_method", counted)
    monkeypatch.setattr(time, "monotonic", lambda: 1000+work[0]*.05)
    baseline = opt.smart_search(sources, 80, 80, .5, time_limit_sec=.4, exact_piece_limit=0)
    work[0] = 0
    disabled = opt.smart_search(sources, 80, 80, .5, time_limit_sec=.4, exact_piece_limit=0,
                                research_abc=ABCSearchPolicy())
    assert disabled == baseline
    assert "abc_research" not in disabled["smart_search"]


def test_research_starts_at_first_valid_kernel_not_after_all_auto_methods(monkeypatch):
    sources = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=2)])
    real_pack, real_run = opt.run_single_method, ABCSearchSession.run
    calls, checkpoints = [0], []
    def counted(*args, **kwargs):
        result = real_pack(*args, **kwargs)
        calls[0] += 1
        return result
    def checkpoint(self, *args, **kwargs):
        checkpoints.append(calls[0])
        return real_run(self, *args, **kwargs)
    monkeypatch.setattr(opt, "run_single_method", counted)
    monkeypatch.setattr(ABCSearchSession, "run", checkpoint)
    monkeypatch.setattr(time, "monotonic", lambda: 1000+calls[0]*.05)
    result = opt.smart_search(sources, 80, 80, .5, time_limit_sec=.1, exact_piece_limit=0,
                             research_abc=ABCSearchPolicy(templates=True))
    assert checkpoints == [1]
    assert calls[0] == 2  # research-only cooperative Auto seed deadline
    assert not validate_plan(result, sources, 80, 80, kerf_cm=.5)


def test_retention_observations_do_not_replace_native_finalists(monkeypatch):
    sources = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=4)])
    original = opt._run_preordered_method
    work = [0]
    def counted(*args, **kwargs):
        result = original(*args, **kwargs)
        work[0] += 1
        return result
    monkeypatch.setattr(opt, "_run_preordered_method", counted)
    monkeypatch.setattr(time, "monotonic", lambda: 1000+work[0]*.05)
    baseline = opt.smart_search(sources, 80, 80, .5, time_limit_sec=.4, exact_piece_limit=0)
    work[0] = 0
    retained = opt.smart_search(sources, 80, 80, .5, time_limit_sec=.4, exact_piece_limit=0,
                                research_abc=ABCSearchPolicy(retention=True))
    assert retained["industrial_rank"] == baseline["industrial_rank"]
    assert [geometry_signature(p) for p in retained["smart_candidates"]] == [
        geometry_signature(p) for p in baseline["smart_candidates"]]


def test_zero_budget_keeps_native_fallback_without_optional_work():
    sources = expand_piece_groups([dict(width_cm=20, length_cm=30, qty=2)])
    baseline = opt.smart_search(sources, 80, 80, .5, time_limit_sec=0, exact_piece_limit=0)
    experiment = opt.smart_search(sources, 80, 80, .5, time_limit_sec=0, exact_piece_limit=0,
                                  research_abc=ABCSearchPolicy(True, True, True))
    assert geometry_signature(experiment) == geometry_signature(baseline)
    assert experiment["industrial_rank"] == baseline["industrial_rank"]
    assert "abc_research" not in experiment["smart_search"]


def test_research_nominee_reaches_actual_application_ranking_without_losing_native_views():
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    sources, native, route = route_problem()
    class Frozen:
        def expand_pieces(self, rows): return deepcopy(sources)
        def optimize(self, *args, **kwargs):
            return dict(deepcopy(native[0]), smart_candidates=deepcopy(native),
                        smart_research_candidates=[deepcopy(route)])
        def validate(self, plan, requested, width, height):
            return validate_plan(plan, requested, width, height, kerf_cm=.5)
    outcome = optimize_order_plan(OptimizeOrderPlanCommand("abc-fixture", "unchanged",
        BoardGeometry(40, 100, 0, .5), OptimizerOptions("smart", "CNC Router", 5, 40,
        50, 50, .25, alignment_search_budget_sec=0, research_abc=ABCSearchPolicy(retention=True)), ()),
        engine=Frozen())
    assert outcome.snapshot["validation"]["is_valid"]
    assert outcome.snapshot["sheets"][0]["pieces"][0]["x"] > 0
    assert 1 <= len(outcome.candidate_snapshots) <= 5
    assert len(outcome.search_seeds) == 6
    assert geometry_signature(outcome.snapshot) == geometry_signature(route)
    assert "smart_research_candidates" not in outcome.snapshot


@pytest.mark.parametrize("share", [0, -.1, .21, float("nan"), float("inf")])
def test_invalid_research_budget_is_rejected(share):
    with pytest.raises(ValueError): ABCSearchPolicy(share=share)


@pytest.mark.parametrize("trim", [0, .3])
def test_template_snapshot_survives_actual_js_export_and_strict_import(tmp_path, trim):
    import json
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    rows = [dict(width_cm=29.9, length_cm=78.8, qty=8,
                 piece_instance_id="smart:1", allow_rotation=0)]
    sources, initial = grid_problem()
    width, height = 122-2*trim, 244-2*trim
    candidate = next(p for p in regular_template_candidates(initial, sources, width, height, .5,
        budget=LocalPackingBudget(), deadline=time.monotonic()+5) if p is not None)
    class Frozen:
        def expand_pieces(self, _rows): return deepcopy(sources)
        def optimize(self, *args, **kwargs): return deepcopy(candidate)
        def validate(self, plan, requested, w, h):
            return validate_plan(plan, requested, w, h, kerf_cm=.5)
    outcome = optimize_order_plan(OptimizeOrderPlanCommand("abc-grid", "input",
        BoardGeometry(122, 244, trim, .5), OptimizerOptions("smart", "CNC Router", 2,
        40, 30, 30, .09), tuple(rows)), engine=Frozen())
    snapshot = json.loads(json.dumps(outcome.snapshot))
    assert snapshot["validation"]["is_valid"]
    imported = import_saved_plan(snapshot, rows, export_real_js(snapshot, tmp_path))
    def material(plan):
        # Strict DXF import may rebind interchangeable copies within one source
        # family. Preserve the complete identity set and family geometry, not
        # an invented per-copy pose correspondence (the existing import contract).
        return sorted((p["source_piece_no"], *(round(p[k], 5) for k in ("x", "y", "w", "h")))
                      for s in plan["sheets"] for p in s["pieces"])
    assert material(imported) == material(snapshot)
    assert sorted(p["piece_instance_id"] for s in imported["sheets"] for p in s["pieces"]) == sorted(
        p["piece_instance_id"] for s in snapshot["sheets"] for p in s["pieces"])
