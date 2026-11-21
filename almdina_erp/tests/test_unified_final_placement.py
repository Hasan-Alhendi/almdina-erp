"""Unified objectives and isolated read-only production geometry regressions."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting import edge_protection as edge, expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy
from almdina_erp.tests.test_geometry_aware_final_placement import witness, finish, METRICS
from almdina_erp.tests.test_final_placement_budget import gallery_witness_outcome


def production_witness(order="26-00345", *, saved=False):
    data = json.loads((Path(__file__).parent / "fixtures/unified_placement" / (order+".json")).read_text())
    sources = expand_piece_groups(data["rows"])
    width, height = data["dimensions"]
    tx, ty = data["trim"]
    sheets = [dict(sheet_no=i+1, resource_kind="FULL_BOARD", w=width-2*tx, h=height-2*ty,
        full_width_cm=width, full_length_cm=height, applied_trim_width_cm=tx, applied_trim_length_cm=ty,
        pieces=[make_placed_piece(sources[pid-1],x,y,w,h,r) for pid,x,y,w,h,r in placements])
        for i,placements in enumerate(data["saved" if saved else "entry"])]
    plan = dict(method_key="Shelf First Fit", machine_type="Auto", kerf_cm=data["kerf"],
                sheets=sheets, unplaced=[])
    assert not validate_plan(plan,sources,width-2*tx,height-2*ty,kerf_cm=data["kerf"])
    return enrich_plan_metrics(plan,plan["method_key"],"Auto",**METRICS),sources


def production_projection(order="26-00345", *, application=None, budget=None, gallery=False,prepared=None):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as current
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    app = application or current
    if prepared is None:
        raw,sources = production_witness(order)
        data = json.loads((Path(__file__).parent/"fixtures/unified_placement"/(order+".json")).read_text())
    else:
        raw,sources,data = prepared
    class SavedGeometry(DomainCuttingEngineAdapter):
        def optimize(self,*args,**kwargs):
            return {**deepcopy(raw),**({"smart_candidates":[deepcopy(raw) for _ in range(5)]} if gallery else {})}
    command = app.OptimizeOrderPlanCommand("isolated-replay","unchanged",app.BoardGeometry(122,244,0,.5),
        app.OptimizerOptions("smart","Auto",120,40,30,30,.09,
            edge_protection=EdgeProtectionPolicy(15,20),alignment_search_budget_sec=30,
            max_centerable_edge_gap_cm=7),tuple(data["rows"]))
    if budget is None:
        return app.optimize_order_plan(command,engine=SavedGeometry())
    trim = app.AppliedTrim(0,0)
    quality = app.PlanQuality(0,len(raw["sheets"]))
    decision = app.AdaptiveTrimDecision(preferred=trim,applied=trim,preferred_quality=quality,applied_quality=quality)
    if callable(budget):
        budget = budget(command)
    return app._snapshot_outcome(command,SavedGeometry(),raw,sources,trim,decision,
        app._canonical_trace_settings(command),alignment_budget=budget)


def test_physical_objectives_partition_pieces_instead_of_weighting_overlapping_candidates():
    plan,sources = witness([(0,0,39,50),(39.5,0,39,50),(79,0,39,50),(0,80,96,30)])
    sheet = plan["sheets"][0]
    goals = edge._placement_goals(sheet,{p["id"] for p in sources},EdgeProtectionPolicy(15,20),7,.5)
    for axis in ("x","y"):
        ids = [i for g in goals if g[0]==axis for i in g[1]]
        assert sorted(ids) == sorted(p["id"] for p in sources)


def test_candidate_group_multiplicity_cannot_change_physical_objectives(monkeypatch):
    plan,sources = witness([(0,0,96,20),(0,50,75,20)],width=100,height=100)
    args = (plan["sheets"][0],{p["id"] for p in sources},EdgeProtectionPolicy(15,20),7,.5)
    goals = edge._placement_goals(*args)
    monkeypatch.setattr(edge,"_movement_groups",lambda *args: [(1,2),(1,),(1,),(2,)])
    assert edge._placement_goals(*args) == goals


def test_positive_policy_has_one_centering_stage(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    calls = []
    old = app.realize_sheet_edge_trim
    def center(*args,**kwargs):
        calls.append(kwargs)
        return old(*args,**kwargs)
    monkeypatch.setattr(app,"realize_sheet_edge_trim",center)
    gallery_witness_outcome(2)
    assert not calls


def test_a_later_accepted_move_cannot_give_back_already_achieved_cutter_quality(monkeypatch):
    plan,sources = witness([(0,0,96,20)],width=100,height=100)
    goals = edge._placement_goals(plan["sheets"][0],{1},EdgeProtectionPolicy(15,0),7,.5)
    diag = dict(tested=0,accepted=0,rejected={},sheets=[dict(tested=0,accepted=0,seconds={})],seconds={},calls={})
    search = edge._SheetSearch(0,plan["sheets"][0],{1},goals,.5,diag)
    search.before, search.current_profile = (100,4,10),(90,4,10)
    monkeypatch.setattr(edge,"sheet_cut_line_quality",lambda *args: (95,4,10))
    assert search.trial(plan,(("x",(1,),2),),sources,100,100,{**METRICS,"machine_type":"Auto"},False) is None
    assert diag["rejected"] == {"shared_cutter_network":1}


@pytest.mark.parametrize("stage",["alns","pattern"])
def test_positive_refinement_projection_uses_fair_remaining_stage_time_not_150ms(monkeypatch,stage):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    from almdina_erp.almdina_erp.domain.cutting import system_layout_refinement,pattern_layout_search
    from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import AppliedTrim
    raw,sources = witness([(0,0,75,75)])
    changed = deepcopy(raw)
    changed["sheets"][0]["pieces"][0]["x"] = 1
    module,name = ((system_layout_refinement,"refine_system_layout") if stage=="alns"
                   else (pattern_layout_search,"refine_pattern_layout"))
    monkeypatch.setattr(module,name,lambda *args,**kwargs: ([raw,changed],{}))
    monkeypatch.setattr(app,"time",SimpleNamespace(monotonic=lambda:0))
    budgets = []
    def project(*args,**kwargs):
        budgets.append(kwargs["alignment_budget"])
        return SimpleNamespace(snapshot={**raw,"validation":{"is_valid":True}})
    monkeypatch.setattr(app,"_snapshot_outcome",project)
    command = SimpleNamespace(board=app.BoardGeometry(122,244,0,.5),allow_piece_mirroring=False,
        optimizer=SimpleNamespace(machine_type="Auto",min_remnant_width_cm=30,min_remnant_length_cm=30,
            min_remnant_area_m2=.09,alignment_search_budget_sec=30,edge_protection=EdgeProtectionPolicy(15,20)))
    args = (command,SimpleNamespace(),sources)
    if stage=="alns":
        app._refine_smart_gallery(*args,raw,raw,AppliedTrim(0,0),None,None,10)
    else:
        app._refine_pattern_gallery(*args,[raw],raw,AppliedTrim(0,0),None,None,10)
    assert budgets and .15 < budgets[0]["deadline"] <= 10


@pytest.mark.parametrize("slack_mm,protection_mm,expected",[(29,15,14.5),(30,15,15),
    (31,15,15.5),(32,20,16),(35,15,17.5),(73,15,15),(235,20,20)])
def test_slack_boundary_selects_center_or_minimum_inset(slack_mm,protection_mm,expected):
    plan,sources = witness([(0,0,100-slack_mm/10,20)],width=100,height=100)
    result,_ = finish(plan,sources,policy=EdgeProtectionPolicy(protection_mm,0))
    assert result["sheets"][0]["pieces"][0]["x"]*10 == pytest.approx(expected)


def test_real_17_board_entry_gets_coverage_and_balanced_35mm_gap():
    plan,sources = production_witness()
    diag = {}
    result,_ = finish(plan,sources,diagnostics=diag)
    assert diag["sheets_reached"] == 17
    assert diag["tested"] <= 24
    assert edge.physical_edge_margins_mm(result["sheets"][7])["left"] == pytest.approx(17.5)
    assert not validate_plan(result,sources,122,244,kerf_cm=.5)


@pytest.mark.parametrize("order",["26-00331","26-00344","26-00345","26-00346","26-00347"])
def test_real_orders_snapshot_dxf_strict_reimport_and_source_identity(tmp_path,order):
    from almdina_erp.tests.test_final_placement_budget import assert_snapshot_dxf_roundtrip
    data = json.loads((Path(__file__).parent/"fixtures/unified_placement"/(order+".json")).read_text())
    outcome = production_projection(order)
    before,sources = production_witness(order)
    after = outcome.snapshot
    assert len(before["sheets"]) == len(after["sheets"])
    for old,new in zip(before["sheets"],after["sheets"],strict=True):
        assert [{k:v for k,v in p.items() if k not in {"x","y"}} for p in old["pieces"]] == [
            {k:v for k,v in p.items() if k not in {"x","y"}} for p in new["pieces"]]
    assert_snapshot_dxf_roundtrip(tmp_path,outcome,rows=data["order_rows"],edge_profiles=data["edge_profiles"])


def test_per_candidate_and_sheet_entry_budget_is_observable_without_reset():
    outcome = production_projection(gallery=True)
    diag = outcome.snapshot["final_placement_diagnostics"]
    assert 0 < diag["remaining_at_entry_sec"] <= diag["allocated_slice_sec"] <= 6
    assert diag["shared_remaining_at_entry_sec"] <= 30
    assert diag["budget_source"] == "native_gallery"
    assert len(diag["sheets"]) == diag["sheets_reached"] == 17
    assert all(s["remaining_at_entry_sec"] is not None and s["preparation_sec"] >= 0
               and "search_status" in s and "margins_mm" in s for s in diag["sheets"])


def test_small_configured_projection_budget_is_shared_not_restarted_per_candidate(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    clock = [0.0]
    monkeypatch.setattr(app,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    command = SimpleNamespace(optimizer=SimpleNamespace(alignment_search_budget_sec=.2,
                                edge_protection=EdgeProtectionPolicy(15,20)))
    first = app._projection_placement_budget(command,10,.15,2,"test")
    clock[0] = .1
    second = app._projection_placement_budget(command,10,.15,1,"test",previous=first)
    assert first["deadline"] == second["deadline"] == .2
    assert first["remaining_candidates"] == 2 and second["remaining_candidates"] == 1


def test_one_rejected_precheck_at_expiry_does_not_classify_the_axis_as_unsafe(monkeypatch):
    plan,sources = witness([(0,0,75,75)])
    clock = [0.0]
    def blocked(*args,**kwargs):
        clock[0] = 30
        return None
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(edge,"_translate_group_moves_if_clear",blocked)
    _,decisions = finish(plan,sources,deadline_monotonic=30)
    assert {d["reason"] for d in decisions} == {"NOT_EVALUATED_TIME_BUDGET"}
    assert all(d["rejected"].get("bounds_kerf_or_swept_clearance") for d in decisions)
