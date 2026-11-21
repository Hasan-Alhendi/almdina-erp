"""Whole-board policy, industrial fallback and native finalization regressions."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting import final_sheet_positioning as positioning
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy, PlanSettingsValidationError
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece
from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter

METRICS = dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09)
ORDERS = ("26-00331", "26-00344", "26-00345", "26-00346", "26-00347")


def order_data(order):
    return json.loads((Path(__file__).parent / "fixtures/unified_placement" / (order + ".json")).read_text())


def captured_plan(order):
    data = order_data(order)
    sources = expand_piece_groups(data["rows"])
    width, height = data["dimensions"]
    tx, ty = data["trim"]
    sheets = [dict(sheet_no=i + 1, resource_kind="FULL_BOARD", w=width-2*tx, h=height-2*ty,
        full_width_cm=width, full_length_cm=height, applied_trim_width_cm=tx, applied_trim_length_cm=ty,
        pieces=[make_placed_piece(sources[pid-1], x, y, w, h, rotated)
                for pid, x, y, w, h, rotated in placements]) for i, placements in enumerate(data["entry"])]
    plan = dict(method_key="Shelf First Fit", machine_type="Auto", kerf_cm=data["kerf"], sheets=sheets, unplaced=[])
    return enrich_plan_metrics(plan, plan["method_key"], "Auto", **METRICS), sources


def finish(plan, sources, *, policy=EdgeProtectionPolicy(15, 20), center_limit=7, **kwargs):
    sheet = plan["sheets"][0]
    return positioning.position_final_sheets(plan, sources, sheet["w"], sheet["h"], plan["kerf_cm"],
        policy=policy, center_limit=center_limit, machine_type=kwargs.pop("machine_type", "Auto"),
        mirroring_allowed=False, metric_options=kwargs.pop("metric_options", METRICS), **kwargs)


def regular_plan(placements, *, trim=0):
    sources=expand_piece_groups([dict(width_cm=w,length_cm=h,qty=1,allow_rotation=False,
        piece_instance_id=f"rigid-{i}") for i,(_,_,w,h) in enumerate(placements)])
    sheet=dict(sheet_no=1,resource_kind="FULL_BOARD",w=100-2*trim,h=100-2*trim,
        full_width_cm=100,full_length_cm=100,applied_trim_width_cm=trim,applied_trim_length_cm=trim,
        pieces=[make_placed_piece(p,x,y,w,h,False) for p,(x,y,w,h) in zip(sources,placements)])
    return enrich_plan_metrics(dict(method_key="Shelf First Fit",kerf_cm=.5,sheets=[sheet],unplaced=[]),
        "Shelf First Fit","Auto",**METRICS),sources


@pytest.mark.parametrize("a,b,p,expected", [
    (0,9,15,4.5), (0,29,15,14.5), (0,30,15,15), (0,35,15,17.5),
    (0,70,15,35), (0,73,15,15), (0,119,15,15), (20,235,15,20),
    (60,60,15,60), (0,32,20,16), (0,235,20,20), (1415,0,20,1395),
])
def test_requested_axis_examples(a,b,p,expected):
    delta, _, _ = positioning.axis_offset(a,b,0,p,70)
    assert a+delta == pytest.approx(expected)


def test_trim_is_counted_once_and_zero_protection_keeps_centering():
    assert positioning.axis_offset(0,73,5,15,70)[0] == 10
    assert positioning.axis_offset(0,35,5,0,70)[0] == 17.5
    assert positioning.axis_offset(0,73,20,15,70)[0] == 0
    assert positioning.axis_offset(0,70.0001,0,15,70)[0] == 15
    assert positioning.axis_offset(0,29.999,0,15,70)[0] == pytest.approx(14.9995)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), "bad", None])
def test_invalid_policy_fails_closed(value):
    with pytest.raises(PlanSettingsValidationError):
        EdgeProtectionPolicy(value,0)


@pytest.mark.parametrize("order", ORDERS)
def test_captured_boards_are_all_processed_with_one_rigid_offset(order):
    plan,sources = captured_plan(order)
    original = deepcopy(plan)
    result,diag = finish(plan,sources)
    assert plan == original
    assert diag["sheets_processed"] == len(plan["sheets"])
    if order == "26-00345":
        assert diag["sheets_processed"] == 17
    assert len(result["sheets"]) == len(plan["sheets"])
    assert not validate_plan(result,sources,122,244,kerf_cm=.5)
    for before,after,report in zip(plan["sheets"],result["sheets"],diag["sheets"],strict=True):
        expected = positioning.translate_sheet(before,report["dx_mm"]/10,report["dy_mm"]/10)
        for actual,predicted in zip(after["pieces"],expected["pieces"],strict=True):
            assert actual["x"] == pytest.approx(predicted["x"],abs=1e-9)
            assert actual["y"] == pytest.approx(predicted["y"],abs=1e-9)
            assert {k:v for k,v in actual.items() if k not in {"x","y","placement_outline_cm"}} == {
                k:v for k,v in predicted.items() if k not in {"x","y","placement_outline_cm"}}
            if actual.get("placement_outline_cm"):
                for point,expected_point in zip(actual["placement_outline_cm"],predicted["placement_outline_cm"],strict=True):
                    assert point == pytest.approx(expected_point,abs=1e-9)
        assert [(p["id"],p["piece_instance_id"],p["w"],p["h"],p["rotated"]) for p in before["pieces"]] == [
            (p["id"],p["piece_instance_id"],p["w"],p["h"],p["rotated"]) for p in after["pieces"]]
        assert after["applied_trim_width_cm"] == before["applied_trim_width_cm"]
        assert after["applied_trim_length_cm"] == before["applied_trim_length_cm"]


def test_rejected_centering_uses_protection_without_recomputing_eligibility(monkeypatch):
    plan,sources = captured_plan("26-00331")
    # This board has 9 mm horizontal slack: centering is feasible, full H15 is not.
    before = deepcopy(plan)
    monkeypatch.setattr(positioning,"_remnants_preserved",lambda *args: False)
    result,diag = finish(plan,sources)
    assert result["sheets"] == before["sheets"]
    assert all(report["rejected"] for report in diag["sheets"])


def test_industrially_rejected_center_has_minimum_protection_fallback(monkeypatch):
    plan,sources=regular_plan([(0,0,96.5,20)])
    monkeypatch.setattr(positioning,"_remnants_preserved",lambda before,after,dx,dy,options: dx<=1.5)
    result,diag=finish(plan,sources)
    piece=result["sheets"][0]["pieces"][0]
    assert (piece["x"],piece["y"]) == (1.5,2)
    assert diag["sheets"][0]["rejected"][0]["reason"] == "QUALIFIED_REMNANT_LOST"


def test_rejected_vertical_center_preserves_safe_horizontal_center(monkeypatch):
    plan,sources=regular_plan([(0,0,96.5,96.5)])
    monkeypatch.setattr(positioning,"_remnants_preserved",lambda before,after,dx,dy,options: dy<=1.5)
    result,_=finish(plan,sources,policy=EdgeProtectionPolicy(15,15))
    piece=result["sheets"][0]["pieces"][0]
    assert (piece["x"],piece["y"]) == (1.75,1.5)


def test_rejected_axis_does_not_block_safe_other_axis(monkeypatch):
    plan,sources=regular_plan([(0,0,96.5,20)])
    monkeypatch.setattr(positioning,"_remnants_preserved",lambda before,after,dx,dy,options: dx==0)
    result,_=finish(plan,sources)
    piece=result["sheets"][0]["pieces"][0]
    assert (piece["x"],piece["y"]) == (0,2)


def test_both_center_axes_rejected_together_still_try_safe_axis(monkeypatch):
    plan,sources=regular_plan([(0,0,96.5,96.5)])
    monkeypatch.setattr(positioning,"_remnants_preserved",lambda before,after,dx,dy,options: dx==0 or dy==0)
    result,_=finish(plan,sources,policy=EdgeProtectionPolicy())
    piece=result["sheets"][0]["pieces"][0]
    assert (piece["x"],piece["y"]) == (1.75,0)


def test_preview_merge_never_repositions_saved_candidates(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import merge_preview_candidates
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    plan,sources=regular_plan([(0,0,92.7,20)])
    final,diag=finish(plan,sources)
    # 0/73 -> 15/58 must remain so when a prior Preview candidate is merged.
    assert final["sheets"][0]["pieces"][0]["x"] == 1.5
    final["final_sheet_positioning"]=diag
    candidate=dict(candidate_id="saved",geometry_fingerprint=geometry_signature(final),snapshot=final)
    previous=deepcopy(candidate)
    monkeypatch.setattr(positioning,"position_final_sheets",lambda *a,**kw: pytest.fail("repositioned saved Preview"))
    assert merge_preview_candidates({}, {"saved":candidate}) == {"saved":previous}


@pytest.mark.parametrize("machine,attachment", [("Panel Saw",None),("Auto","overlays"),
    ("Auto","toolpaths"),("Auto","blank_reservation_cm"),("Auto","OFFCUT")])
def test_unsupported_geometry_keeps_entire_board(machine,attachment):
    plan,sources=regular_plan([(0,0,96.5,20),(0,20.5,80,20)])
    if attachment=="OFFCUT":
        plan["sheets"][0]["resource_kind"]="OFFCUT"
    elif attachment:
        plan["sheets"][0]["pieces"][0][attachment]=[{"x":0,"y":0}]
    result,diag=finish(plan,sources,machine_type=machine)
    assert result["sheets"] == plan["sheets"]
    assert diag["sheets"][0]["dx_mm"] == diag["sheets"][0]["dy_mm"] == 0


def test_whole_board_threshold_does_not_move_independent_row():
    plan,sources=regular_plan([(0,0,100,20),(0,40,96.5,20)])
    result,diag=finish(plan,sources,policy=EdgeProtectionPolicy(15,0))
    assert [p["x"] for p in result["sheets"][0]["pieces"]] == [0,0]
    assert diag["sheets"][0]["policies"][0] == "CENTERED"


def test_large_board_has_no_alignment_piece_or_trial_limit():
    plan,sources=regular_plan([(col*10.5,row*10.5,10,10) for col in range(8) for row in range(9)])
    result,diag=finish(plan,sources)
    assert len(result["sheets"][0]["pieces"]) == 72
    assert diag["sheets_processed"] == 1
    assert diag["sheets"][0]["reason"] == "POSITIONED"
    assert not validate_plan(result,sources,100,100,kerf_cm=.5)


def test_absolute_placement_outline_moves_with_owning_piece():
    plan,_=regular_plan([(0,0,96.5,20)])
    ring=[[0,0],[96.5,0],[96.5,20],[0,20]]
    sheet=plan["sheets"][0]
    sheet["pieces"][0]["placement_outline_cm"]=deepcopy(ring)
    moved=positioning.translate_sheet(sheet,1.75,2)["pieces"][0]
    assert moved["x"] == 1.75 and moved["y"] == 2
    assert moved["placement_outline_cm"] == [(x+1.75,y+2) for x,y in ring]
    assert sheet["pieces"][0]["placement_outline_cm"] == ring


def test_exact_special_polygon_keeps_local_definition_and_rigid_geometry():
    from almdina_erp.tests.test_glass_opening_nesting import _exact_special
    from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
    plan,_=regular_plan([(0,0,96.5,20)])
    definition=_exact_special(96.5,20,[[0,0],[96.5,0],[96.5,10],[90,20],[0,20]])
    sources=expand_piece_groups([dict(piece_type="Special",width_cm=96.5,length_cm=20,
        qty=1,allow_rotation=False,piece_instance_id="exact-special",special_shape_geometry_json=definition)])
    original=make_placed_piece(sources[0],0,0,96.5,20,False)
    plan["sheets"][0]["pieces"]=[original]
    result,diag=finish(plan,sources)
    moved=result["sheets"][0]["pieces"][0]
    assert diag["sheets"][0]["reason"] == "POSITIONED"
    assert moved["special_shape_geometry_json"] == definition
    for point,before in zip(material_outline_cm(moved),material_outline_cm(original),strict=True):
        assert point == pytest.approx((before[0]+1.75,before[1]+2))
    assert not validate_plan(result,sources,100,100,kerf_cm=.5)


def native_command(order, *, seconds=1, policy=EdgeProtectionPolicy(15,20), trim=0):
    data=order_data(order)
    return app.OptimizeOrderPlanCommand("simple-placement", "isolated-input", app.BoardGeometry(122,244,trim,.5),
        app.OptimizerOptions("smart","Auto",seconds,40,**METRICS,
            max_centerable_edge_gap_cm=7,alignment_search_budget_sec=0,edge_protection=policy),
        tuple(data["rows"]))


def test_native_gallery_positions_only_selected_plans_after_alignment(monkeypatch):
    from almdina_erp.almdina_erp.domain.cutting import final_cut_line_alignment as alignment
    events=[]
    real_position,real_align=positioning.position_final_sheets,alignment.align_regular_cut_lines
    def position(*args,**kwargs):
        events.append("position")
        return real_position(*args,**kwargs)
    def align(*args,**kwargs):
        events.append("align")
        return real_align(*args,**kwargs)
    monkeypatch.setattr(positioning,"position_final_sheets",position)
    monkeypatch.setattr(alignment,"align_regular_cut_lines",align)
    monkeypatch.setattr(app,"realize_sheet_edge_trim",lambda *args,**kwargs: pytest.fail("early centering"))
    command=native_command("26-00347")
    outcome=app.optimize_order_plan(command,engine=DomainCuttingEngineAdapter())
    selected=outcome.candidate_snapshots or (outcome.snapshot,)
    assert outcome.snapshot["validation"]["is_valid"]
    assert events.count("position") == len(selected) <= 5
    assert "align" not in events[events.index("position"):]
    assert all(s["final_sheet_positioning"]["sheets_processed"] == len(s["sheets"]) for s in selected)
    assert len(outcome.search_seeds) >= len(outcome.candidate_snapshots)


@pytest.mark.parametrize("order", ORDERS)
def test_captured_final_snapshot_actual_dxf_strict_reimport(tmp_path,order):
    from almdina_erp.tests.simple_placement_support import assert_snapshot_dxf_roundtrip
    plan,sources=captured_plan(order)
    command=native_command(order)
    trim=app.AppliedTrim(0,0)
    quality=app.PlanQuality(0,len(plan["sheets"]))
    decision=app.AdaptiveTrimDecision(trim,trim,quality,quality)
    outcome=app._snapshot_outcome(command,DomainCuttingEngineAdapter(),plan,sources,trim,decision,
        app._canonical_trace_settings(command),final_positioning=True)
    data=order_data(order)
    assert_snapshot_dxf_roundtrip(tmp_path,outcome,rows=data["order_rows"],edge_profiles=data["edge_profiles"])


@pytest.mark.parametrize("policy", [EdgeProtectionPolicy(),EdgeProtectionPolicy(15,20)])
def test_native_positive_trim_actual_persistence_dxf_roundtrip(tmp_path,policy):
    from almdina_erp.tests.simple_placement_support import assert_snapshot_dxf_roundtrip
    command=native_command("26-00347",trim=.5,policy=policy)
    outcome=app.optimize_order_plan(command,engine=DomainCuttingEngineAdapter())
    assert outcome.snapshot["validation"]["is_valid"]
    assert all(s["applied_trim_width_cm"] == s["applied_trim_length_cm"] == .5
               for s in outcome.snapshot["sheets"])
    data=order_data("26-00347")
    assert_snapshot_dxf_roundtrip(tmp_path,outcome,rows=data["order_rows"],edge_profiles=data["edge_profiles"])
