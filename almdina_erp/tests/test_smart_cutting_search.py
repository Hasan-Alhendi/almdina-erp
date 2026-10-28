"""Smart search compares completed, independently valid manufacturing plans."""
from copy import deepcopy

import pytest

from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.catalog import (
    DEFAULT_OPTIMIZATION_MODE_ID, persisted_mode_value, require_engine_mode,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import (
    placement_permission_errors, validate_plan,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups


def test_smart_catalog_preserves_historical_defaults():
    assert require_engine_mode("smart") == "Smart Search"
    assert persisted_mode_value("Smart Search") == "smart"
    assert DEFAULT_OPTIMIZATION_MODE_ID == "auto_pro"
    assert require_engine_mode("auto") == "Auto"


@pytest.mark.parametrize("machine", ["CNC Router", "Panel Saw"])
@pytest.mark.parametrize("kerf", [0, .3])
def test_smart_retains_valid_auto_seed_and_physics(machine, kerf):
    pieces = expand_piece_groups([
        dict(width_cm=20, length_cm=20, qty=4, allow_rotation=1,
             piece_type="L-Shaped Corner", clipped_corner_position="Top Right",
             clipped_corner_width_cm=8, clipped_corner_length_cm=8),
        dict(width_cm=10, length_cm=10, qty=1),
    ])
    if machine == "Panel Saw" and kerf == 0:
        # Touching irregular outlines are rejected by the existing validator;
        # rectangular zero-Kerf paths have the complete manufacturing contract.
        pieces = expand_piece_groups([dict(width_cm=20, length_cm=20, qty=4),
                                      dict(width_cm=10, length_cm=10, qty=1)])
    original = deepcopy(pieces)
    plan = opt.optimize_plan(pieces, 40.3, 40.3, kerf, selected_mode="Smart Search",
                             machine_type=machine, time_limit_sec=.4)
    assert not validate_plan(plan, pieces, 40.3, 40.3, kerf_cm=kerf)
    assert not placement_permission_errors(plan, pieces, mirroring_allowed=False)
    assert pieces == original
    assert tuple(plan["industrial_rank"]) <= tuple(plan["smart_search"]["auto_seed_rank"])
    assert plan["optimization_mode"] == "Smart Search"
    assert plan["smart_search"]["completed_candidates"] <= 6


def test_smart_deadline_preserves_seed_without_optional_runs(monkeypatch):
    pieces = expand_piece_groups([dict(width_cm=5, length_cm=5, qty=2)])
    baseline = opt.auto_fast(pieces, 10.3, 10, .3)
    monkeypatch.setattr(opt, "auto_fast", lambda *a, **kw: deepcopy(baseline))
    monkeypatch.setattr(opt.time, "monotonic", lambda: 100)
    monkeypatch.setattr(opt, "_run_preordered_method", lambda *a, **kw: pytest.fail("late packing"))
    plan = opt.smart_search(pieces, 10.3, 10, .3, time_limit_sec=0)
    assert not validate_plan(plan, pieces, 10.3, 10, kerf_cm=.3)
    assert plan["sheets"] == baseline["sheets"]
    assert plan["smart_search"]["completed_candidates"] == 1


def test_geometric_dedup_preserves_orientation_and_holes():
    plan = {"sheets": [{"w": 10, "h": 10, "pieces": [
        {"id": 1, "x": 0, "y": 0, "w": 3, "h": 4},
        {"id": 2, "x": 4, "y": 0, "w": 3, "h": 4},
    ]}], "unplaced": []}
    other = deepcopy(plan)
    other["sheets"][0]["pieces"].reverse()
    other["method_label"] = "irrelevant diagnostics"
    assert opt._layout_signature(plan) == opt._layout_signature(other)
    other["sheets"][0]["pieces"][0]["glass_hole_local_mm"] = [[1,1],[2,1],[2,2],[1,2]]
    assert opt._layout_signature(plan) != opt._layout_signature(other)


def test_worse_rectangle_seed_can_win_after_finishing(monkeypatch):
    pieces = expand_piece_groups([dict(width_cm=4, length_cm=4, qty=2)])
    packed = opt.auto_fast(pieces, 10, 10, .3)
    split = deepcopy(packed)
    one, two = split["sheets"][0]["pieces"]
    split["sheets"] = [dict(sheet_no=i+1, w=10, h=10, pieces=[p])
                       for i, p in enumerate((one, two))]
    split = opt.enrich_plan_metrics(split, split["method_key"])
    monkeypatch.setattr(opt, "auto_fast", lambda *a, **kw: deepcopy(packed))
    # A candidate's rectangle rank is deliberately worse, but its completed
    # result is better. The seed's finishing result is two valid boards.
    raw = deepcopy(split)
    raw["sheets"][0]["pieces"][0]["x"] = 1
    monkeypatch.setattr(opt, "_run_preordered_method", lambda *a, **kw: deepcopy(raw))
    def finish(raw, *args, **kwargs):
        return deepcopy(split if len(raw["sheets"]) == 1 else packed)
    monkeypatch.setattr(opt, "_finish_plan_search", finish)
    monkeypatch.setattr(opt, "_cp_sat_available", lambda: False)
    plan = opt.smart_search(pieces, 10, 10, .3, time_limit_sec=1)
    assert len(plan["sheets"]) == 1
    assert plan["smart_search"]["auto_seed_rank"][1] == 2


def test_invalid_lower_board_candidate_never_displaces_seed(monkeypatch):
    pieces = expand_piece_groups([dict(width_cm=4, length_cm=4, qty=2)])
    packed = opt.auto_fast(pieces, 10, 10, .3)
    invalid = deepcopy(packed)
    invalid["sheets"][0]["pieces"].pop()
    monkeypatch.setattr(opt, "_run_preordered_method", lambda *a, **kw: deepcopy(invalid))
    monkeypatch.setattr(opt, "_cp_sat_available", lambda: False)
    plan = opt.smart_search(pieces, 10, 10, .3, time_limit_sec=.2)
    assert not validate_plan(plan, pieces, 10, 10, kerf_cm=.3)
    assert len(plan["sheets"][0]["pieces"]) == 2


def test_smart_never_sends_irregular_geometry_to_cp_sat(monkeypatch):
    pieces = expand_piece_groups([dict(width_cm=9, length_cm=9, qty=2,
        piece_type="Glass", glass_margin_mm=10)])
    monkeypatch.setattr(opt, "_solve_cp_sat", lambda *a, **kw: pytest.fail("irregular exact solve"))
    plan = opt.smart_search(pieces, 10, 10, .3, time_limit_sec=.2)
    assert not validate_plan(plan, pieces, 10, 10, kerf_cm=.3)


def test_trim_probes_share_budget_without_changing_requested_settings(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    from almdina_erp.tests.test_cutting_plan_application import AdaptiveTrimGeometryEngine
    clock, budgets = [0.0], []
    class Engine(AdaptiveTrimGeometryEngine):
        def optimize(self, *args, **kwargs):
            budgets.append(kwargs["time_limit_sec"])
            clock[0] += .2
            return super().optimize(*args, **kwargs)
    monkeypatch.setattr(app.time, "monotonic", lambda: clock[0])
    command = app.OptimizeOrderPlanCommand(engine_version="test", input_fingerprint="test",
        board=app.BoardGeometry(100, 100, .5, .3),
        optimizer=app.OptimizerOptions("smart", "CNC Router", .5, 20, 30, 30, .09),
        piece_rows=({"id": 1, "width_cm": 100, "length_cm": 40, "qty": 1},))
    outcome = app.optimize_order_plan(command, engine=Engine())
    assert len(budgets) > 1
    assert budgets == sorted(budgets, reverse=True)
    assert budgets[0] == .5
    assert min(budgets) == 0
    assert command.optimizer.time_limit_sec == outcome.snapshot["search_time_limit_sec"] == .5
    assert outcome.snapshot["kerf_cm"] == .3
    assert outcome.snapshot["trim_cm"] == .5


def test_unproven_angled_import_never_becomes_smart_manufacturing_result():
    pieces = expand_piece_groups([
        dict(piece_type="Clipped Corner", width_cm=20, length_cm=20, qty=4, allow_rotation=1,
             clipped_corner_position="Top Right", clipped_corner_width_cm=8, clipped_corner_length_cm=8),
        dict(width_cm=8, length_cm=3, qty=1),
    ])
    legacy = opt.optimize_plan(pieces, 40.3, 40.3, .3, selected_mode="Auto", time_limit_sec=.4)
    smart = opt.optimize_plan(pieces, 40.3, 40.3, .3, selected_mode="Smart Search", time_limit_sec=.4)
    assert len(legacy["sheets"]) == 1  # Geometry-valid, strict-import-incompatible witness.
    assert len(smart["sheets"]) == 2
    assert not any(p.get("placement_rotation_deg") for s in smart["sheets"] for p in s["pieces"])
    assert not validate_plan(smart, pieces, 40.3, 40.3, kerf_cm=.3)
