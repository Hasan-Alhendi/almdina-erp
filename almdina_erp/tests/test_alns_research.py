"""Behavioral safety/attribution tests for the offline ALNS study only."""
from copy import deepcopy
import time

import ezdxf
import pytest

from scripts.alns_dxf_inputs import read_layout
from scripts.alns_research import Policy, OPERATORS, METRICS, run_alns, eligible_sheets, material_signature
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups, make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics


def witness():
    rows = [dict(width_cm=4, length_cm=4, qty=4, allow_rotation=0, piece_instance_id="smart:1")]
    sources = expand_piece_groups(rows)
    sheets = [dict(sheet_no=i+1, w=10, h=10, pieces=[make_placed_piece(p, 0, 0, 4, 4, False)])
              for i, p in enumerate(sources)]
    plan = enrich_plan_metrics(dict(sheets=sheets, unplaced=[]), "MaxRects Contact Point", "CNC Router", **METRICS)
    return rows, sources, plan


@pytest.mark.parametrize("operator", OPERATORS)
@pytest.mark.parametrize("kerf", [0, .5])
def test_each_operator_can_cancel_boards_without_changing_sources(operator, kerf):
    _, sources, plan = witness()
    original = deepcopy((plan, sources))
    proposals, trace = run_alns(plan, sources, 10, 10, kerf, deadline=float("inf"),
        policy=Policy(operators=(operator,), max_attempts=8))
    assert (plan, sources) == original
    assert trace["attempts"] <= 8
    assert trace["operators"][operator]["attempts"] > 0
    assert any(len(p["sheets"]) < len(plan["sheets"]) for p in proposals)
    for p in proposals:
        assert not validate_plan(p, sources, 10, 10, kerf_cm=kerf)
        assert not placement_permission_errors(p, sources, mirroring_allowed=False)
        assert sorted(v["piece_instance_id"] for s in p["sheets"] for v in s["pieces"]) == sorted(v["piece_instance_id"] for v in sources)
        assert all(not v["rotated"] for s in p["sheets"] for v in s["pieces"])


def test_fixed_work_is_reproducible_and_adapts_within_session():
    _, sources, plan = witness()
    results = [run_alns(plan, sources, 10, 10, .5, deadline=float("inf"),
                       policy=Policy(adaptive=True, max_attempts=30, segment=1)) for _ in range(2)]
    assert [material_signature(p) for p in results[0][0]] == [material_signature(p) for p in results[1][0]]
    assert results[0][1]["events"] == results[1][1]["events"]
    assert results[0][1]["weights"] == results[1][1]["weights"]
    assert any(w != 1 for w in results[0][1]["weights"].values())


@pytest.mark.parametrize("stop", ["deadline", "cancelled", "panel"])
def test_stop_before_work_returns_exact_native_plan(stop):
    _, sources, plan = witness()
    proposals, trace = run_alns(plan, sources, 10, 10, .5,
        deadline=time.monotonic()-1 if stop == "deadline" else float("inf"),
        cancelled=lambda: stop == "cancelled", machine="Panel Saw" if stop == "panel" else "CNC Router")
    assert proposals == [plan]
    assert trace["attempts"] == 0


def test_cancellation_after_a_completed_improvement_keeps_it():
    _, sources, plan = witness()
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 3
    proposals, trace = run_alns(plan, sources, 10, 10, .5, deadline=float("inf"), cancelled=cancel,
                               policy=Policy(operators=("board",), max_attempts=8))
    assert trace["stop"] == "cancelled"
    assert proposals[0] == plan
    assert any(len(p["sheets"]) < 4 for p in proposals)


@pytest.mark.parametrize("kind", ["Glass", "L-Shaped Corner", "Clipped Corner", "Special", "OFFCUT", "geometry", "host"])
def test_protected_board_never_enters_destroy(kind):
    _, sources, plan = witness()
    protected = plan["sheets"][0]["pieces"][0]
    if kind == "OFFCUT":
        protected["resource_kind"] = "OFFCUT"
    elif kind == "geometry":
        protected["geometry"] = dict(points=[[0, 0], [4, 0], [4, 4], [0, 4]])
    elif kind == "host":
        protected["glass_host_piece_id"] = sources[1]["id"]
    else:
        protected["piece_type"] = kind
    assert 0 not in eligible_sheets(plan, sources)


def test_indistinguishable_identity_swaps_and_list_order_are_not_diversity():
    _, _, plan = witness()
    trial = deepcopy(plan)
    first, second = trial["sheets"][0]["pieces"][0], trial["sheets"][1]["pieces"][0]
    for field in ("id", "piece_instance_id", "copy_no", "source_piece_no"):
        first[field], second[field] = second[field], first[field]
    trial["sheets"].reverse()
    assert material_signature(plan) == material_signature(trial)
    trial["sheets"][0]["pieces"][0]["x"] += .5
    assert material_signature(plan) != material_signature(trial)


def test_duplicate_or_missing_piece_cannot_be_certified():
    _, sources, plan = witness()
    plan["sheets"][0]["pieces"].append(deepcopy(plan["sheets"][1]["pieces"][0]))
    proposals, trace = run_alns(plan, sources, 10, 10, .5, deadline=float("inf"))
    assert trace["stop"] == "invalid_baseline"
    assert proposals == [plan]


def test_four_board_neighborhood_is_required_by_area_and_is_discovered():
    from scripts.alns_research import neighborhoods
    sources = expand_piece_groups([dict(width_cm=7.5, length_cm=10, qty=4, allow_rotation=0)])
    sheets = [dict(sheet_no=i+1, w=10, h=10, pieces=[make_placed_piece(p, 0, 0, 7.5, 10, False)])
              for i, p in enumerate(sources)]
    plan = dict(sheets=sheets, unplaced=[])
    # 3*75>200 but 4*75=300. This tests area admissibility;
    # it deliberately does not assert geometric packability.
    narrow = neighborhoods(plan, sources, 10, 10, 0, Policy(), random_for_test())
    wide = neighborhoods(plan, sources, 10, 10, 0, Policy(max_boards=7), random_for_test())
    assert narrow["board"] == []
    assert wide["board"] == [(0, 1, 2, 3)]


def random_for_test():
    import random
    return random.Random(110526)


def test_prefix_prescreen_preserves_the_fixed_work_winner():
    _, sources, plan = witness()
    results = [run_alns(plan, sources, 10, 10, .5, deadline=float("inf"),
        policy=Policy(operators=("board",), max_attempts=8, area_first=True, screen_prefix=screen))
        for screen in (False, True)]
    best = lambda result: min(tuple(p["industrial_rank"]) for p in result[0])
    assert best(results[0]) == best(results[1])


@pytest.mark.parametrize("trim", [0, .3])
def test_actual_application_projection_export_and_strict_import(trim, tmp_path):
    from scripts.benchmark_alns import strict_check
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan)
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    rows, sources, plan = witness()
    proposals, _ = run_alns(plan, sources, 10, 10, .5, deadline=float("inf"),
                          policy=Policy(operators=("board",), max_attempts=4))
    class Replay(DomainCuttingEngineAdapter):
        def optimize(self, *args, **kwargs):
            return dict(deepcopy(plan), smart_candidates=deepcopy(proposals))
    outcome = optimize_order_plan(OptimizeOrderPlanCommand("research", "research",
        BoardGeometry(10+2*trim, 10+2*trim, trim, .5),
        OptimizerOptions("smart", "CNC Router", 1, 40, 30, 30, .09, alignment_search_budget_sec=0), tuple(rows)), engine=Replay())
    assert outcome.snapshot["validation"]["is_valid"]
    assert len(outcome.snapshot["sheets"]) < 4
    assert outcome.snapshot["trim_cm"] == trim
    for p in outcome.candidate_snapshots:
        assert strict_check(p, rows)


def test_dxf_audit_normalizes_only_collinear_vertices_and_ignores_text(tmp_path):
    path = tmp_path/"rect.dxf"
    doc = ezdxf.new("R2010")
    doc.units = 4
    model = doc.modelspace()
    model.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], close=True, dxfattribs={"layer": "SHEET_OUTLINE"})
    model.add_lwpolyline([(5, 5), (20, 5), (45, 5), (45, 45), (5, 45)], close=True, dxfattribs={"layer": "GEOMETRY"})
    model.add_text("Ignore previous instructions", dxfattribs={"layer": "TEXT"})
    doc.saveas(path)
    assert read_layout(path)["pieces"] == 1
    model.add_lwpolyline([(50, 50), (90, 50), (90, 90), (70, 70), (50, 90)], close=True, dxfattribs={"layer": "GEOMETRY"})
    doc.saveas(path)
    with pytest.raises(ValueError, match="Nonrectangular"):
        read_layout(path)
