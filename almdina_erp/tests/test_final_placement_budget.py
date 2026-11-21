"""Multi-board scheduling witnesses; not a capture of order 26-00345."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting import edge_protection as edge
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy
from almdina_erp.almdina_erp.domain.cutting.primitives import make_placed_piece

METRICS = dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09)


def multi_board_witness(count, *, dense=False):
    cells = [(col*18.5, row*22.5, 18, 22) for row in range(8) for col in range(6)] if dense else [(0,0,75,75)]
    sources = expand_piece_groups([
        dict(width_cm=w, length_cm=h, qty=1, allow_rotation=False,
             piece_instance_id=f"budget-witness-{board}-{i}")
        for board in range(count) for i, (_,_,w,h) in enumerate(cells)])
    sheets = [dict(sheet_no=board+1, resource_kind="FULL_BOARD", w=122, h=244,
        full_width_cm=122, full_length_cm=244, applied_trim_width_cm=0, applied_trim_length_cm=0,
        pieces=[make_placed_piece(sources[board*len(cells)+i],x,y,w,h,False)
                for i,(x,y,w,h) in enumerate(cells)]) for board in range(count)]
    used = sum(p["w"]*p["h"] for s in sheets for p in s["pieces"])/10000
    plan = dict(method_key="MaxRects Best Short Side", machine_type="CNC Router", kerf_cm=.5,
        sheets=sheets,unplaced=[],used_area_m2=used,total_board_area_m2=count*2.9768,
        waste_area_m2=count*2.9768-used)
    return enrich_plan_metrics(plan,plan["method_key"],"CNC Router",**METRICS),sources


def finish(plan,sources,**kwargs):
    return edge.protect_plan_edges(plan,sources,122,244,.5,
        policy=EdgeProtectionPolicy(15,20),max_centerable_edge_gap_cm=7,
        machine_type="CNC Router",mirroring_allowed=False,metric_options=METRICS,**kwargs)


@pytest.mark.parametrize("count", [1,2,8,17])
def test_basic_protection_reaches_every_board_before_expensive_alignment_generation(monkeypatch,count):
    plan,sources = multi_board_witness(count)
    original = deepcopy(plan)
    clock, reached = [0.0],set()
    translate = edge._translate_group_moves_if_clear
    def tracked(plan,index,*args,**kwargs):
        reached.add(index)
        return translate(plan,index,*args,**kwargs)
    # Deterministic pathological generator: the old caller invokes it before
    # *any* trial. Actual proposal validators and geometry remain unmocked.
    def expensive(*args,**kwargs):
        clock[0] += 30
        return []
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(edge,"_candidate_moves",expensive)
    monkeypatch.setattr(edge,"_translate_group_moves_if_clear",tracked)
    result,_ = finish(plan,sources,deadline_monotonic=30)
    assert reached == set(range(count))
    assert all(s["pieces"][0]["x"] >= 1.5 and s["pieces"][0]["y"] >= 2 for s in result["sheets"])
    assert not validate_plan(result,sources,122,244,kerf_cm=.5)
    assert plan == original


@pytest.mark.parametrize("count", [1,2,8,17])
def test_global_24_trials_cover_boards_with_atomic_xy_and_full_safety(count):
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
    plan,sources = multi_board_witness(count)
    diagnostics = {}
    result,decisions = finish(plan,sources,diagnostics=diagnostics)
    assert diagnostics["sheets_reached"] == count
    assert diagnostics["tested"] <= 24
    assert diagnostics["accepted"] == count
    assert {d["reason"] for d in decisions} == {"EDGE_PROTECTED"}
    assert len(result["sheets"]) == count
    assert not validate_plan(result,sources,122,244,kerf_cm=.5)
    for before,after in zip(plan["sheets"],result["sheets"],strict=True):
        assert sheet_cut_line_quality(before,.5)[0] == sheet_cut_line_quality(after,.5)[0]
        for first,last in zip(before["pieces"],after["pieces"],strict=True):
            assert {k:v for k,v in first.items() if k not in {"x","y"}} == {k:v for k,v in last.items() if k not in {"x","y"}}


def test_unexamined_boards_report_trial_budget_instead_of_geometric_failure():
    plan,sources = multi_board_witness(25)
    diagnostics = {}
    _,decisions = finish(plan,sources,diagnostics=diagnostics)
    assert diagnostics["tested"] == diagnostics["sheets_reached"] == 24
    assert [d["reason"] for d in decisions if d["sheet_no"] == 25] == ["TRIAL_BUDGET"]*2


def test_expired_budget_is_not_reported_as_unsafe_geometry():
    plan,sources = multi_board_witness(17)
    diagnostics = {}
    result,decisions = finish(plan,sources,deadline_monotonic=0,diagnostics=diagnostics)
    assert result is plan and diagnostics["tested"] == 0
    assert {d["reason"] for d in decisions} == {"NOT_EVALUATED_TIME_BUDGET"}


def test_generation_scoring_stops_inside_a_board_without_eating_other_slices(monkeypatch):
    plan,sources = multi_board_witness(8,dense=True)
    clock = [0.0]
    score = edge._projected_axis_gain
    def expensive(*args,**kwargs):
        clock[0] += .1
        return score(*args,**kwargs)
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(edge,"_projected_axis_gain",expensive)
    diagnostics = {}
    result,_ = finish(plan,sources,deadline_monotonic=3,diagnostics=diagnostics)
    assert diagnostics["sheets_reached"] == 8
    assert clock[0] <= 3.1  # one bounded scorer may complete at its deadline
    assert all(s["pieces"][0]["x"]>=1.5 and s["pieces"][0]["y"]>=2 for s in result["sheets"])


def test_completed_candidate_is_kept_when_validation_finishes_at_deadline(monkeypatch):
    plan,sources = multi_board_witness(2)
    clock = [0.0]
    validate = edge.validate_plan
    def expire(candidate,*args,**kwargs):
        errors = validate(candidate,*args,**kwargs)
        if candidate["sheets"][0]["pieces"][0]["x"] > 0:
            clock[0] = 30
        return errors
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(edge,"validate_plan",expire)
    diagnostics = {}
    result,decisions = finish(plan,sources,deadline_monotonic=30,diagnostics=diagnostics)
    assert result["sheets"][0]["pieces"][0]["x"] == 1.5
    assert result["sheets"][1] == plan["sheets"][1]
    assert diagnostics["accepted"] == 1
    assert {d["reason"] for d in decisions if d["sheet_no"] == 2} == {"NOT_EVALUATED_TIME_BUDGET"}


def gallery_witness_outcome(count, *, dense=False, seconds=30, application=None):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as current
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    app = application or current
    raw,sources = multi_board_witness(count,dense=dense)
    rows = tuple(dict(width_cm=s["width_cm"],length_cm=s["length_cm"],qty=1,allow_rotation=False,
                      piece_instance_id=s["piece_instance_id"].rsplit(":",1)[0]) for s in sources)
    class GalleryPacking(DomainCuttingEngineAdapter):
        def optimize(self,*args,**kwargs):
            alternatives = []
            for variant in range(5):
                plan = deepcopy(raw)
                for sheet in plan["sheets"]:
                    for piece in sheet["pieces"]:
                        if not dense or piece["y"] >= 7*22.5:
                            piece["y"] += variant*(.1 if dense else 10)
                alternatives.append(plan)
            return {**deepcopy(alternatives[0]),"smart_candidates":alternatives}
    command = app.OptimizeOrderPlanCommand("budget-gallery","unchanged",app.BoardGeometry(122,244,0,.5),
        app.OptimizerOptions("smart","CNC Router",120,40,30,30,.09,
            edge_protection=EdgeProtectionPolicy(15,20),alignment_search_budget_sec=seconds,
            max_centerable_edge_gap_cm=7),rows)
    return app.optimize_order_plan(command,engine=GalleryPacking())


def test_five_17_board_candidates_share_time_including_finalization(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    from almdina_erp.almdina_erp.domain.cutting import final_cut_line_alignment as alignment
    clock,deadlines,diagnostics = [0.0],[],[]
    baseline,protect = alignment.validate_alignment_baseline,edge.protect_plan_edges
    def preparation(*args,**kwargs):
        clock[0] += 1
        return baseline(*args,**kwargs)
    def search(*args,**kwargs):
        deadlines.append(kwargs["deadline_monotonic"])
        result = protect(*args,**kwargs)
        diagnostics.append(deepcopy(kwargs["diagnostics"]))
        return result
    monkeypatch.setattr(app,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(alignment,"validate_alignment_baseline",preparation)
    monkeypatch.setattr(edge,"protect_plan_edges",search)
    outcome = gallery_witness_outcome(17)
    assert len(diagnostics) == len(deadlines) == 5
    assert deadlines[0] == 6  # reserved before the first 1-second preparation
    assert all(d <= 30 for d in deadlines)
    assert [d["sheets_reached"] for d in diagnostics] == [17]*5
    assert all(d["tested"]<=24 for d in diagnostics)
    assert all(p["validation"]["is_valid"] for p in outcome.candidate_snapshots)


def test_expiry_during_candidate_finalization_is_explicit_and_later_candidates_get_remaining_time(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    from almdina_erp.almdina_erp.domain.cutting import final_cut_line_alignment as alignment
    clock,calls,diagnostics = [0.0],[0],[]
    baseline,protect = alignment.validate_alignment_baseline,edge.protect_plan_edges
    def preparation(*args,**kwargs):
        calls[0] += 1
        clock[0] += 7 if calls[0]==1 else .1
        return baseline(*args,**kwargs)
    def search(*args,**kwargs):
        result = protect(*args,**kwargs)
        diagnostics.append((deepcopy(kwargs["diagnostics"]),deepcopy(result[1])))
        return result
    monkeypatch.setattr(app,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(edge,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(alignment,"validate_alignment_baseline",preparation)
    monkeypatch.setattr(edge,"protect_plan_edges",search)
    gallery_witness_outcome(17)
    assert diagnostics[0][0]["tested"] == 0
    assert {d["reason"] for d in diagnostics[0][1]} == {"NOT_EVALUATED_TIME_BUDGET"}
    assert [d[0]["sheets_reached"] for d in diagnostics[1:]] == [17]*4


def test_application_reuses_exact_baseline_check_but_keeps_independent_final_adapter_gate(monkeypatch):
    from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as app
    plan,sources = multi_board_witness(2)
    # Domain's expensive baseline check must be supplied by the actual engine
    # validation port, not a snapshot/client boolean. Candidate checks remain.
    validate = edge.validate_plan
    seen = []
    def domain_check(candidate,*args,**kwargs):
        seen.append(len(candidate["sheets"]))
        return validate(candidate,*args,**kwargs)
    monkeypatch.setattr(edge,"validate_plan",domain_check)
    outcome = gallery_witness_outcome(2)
    assert seen and set(seen) == {1}
    for snapshot in outcome.candidate_snapshots:
        assert snapshot["validation"]["is_valid"]
        assert snapshot["final_placement_diagnostics"]["baseline_validation_reused"]


@pytest.mark.parametrize("count", [1,2,8,17])
def test_multi_board_snapshot_actual_dxf_and_strict_reimport_preserve_protected_geometry(tmp_path,count):
    outcome = gallery_witness_outcome(count)
    assert_snapshot_dxf_roundtrip(tmp_path,outcome)
    assert outcome.snapshot["final_placement_diagnostics"]["sheets_reached"] == count


def assert_snapshot_dxf_roundtrip(tmp_path,outcome,*,rows=None,edge_profiles=None):
    import json
    import os
    from pathlib import Path
    import subprocess
    from almdina_erp.tests.test_edge_protection import _services
    _services()
    from almdina_erp.tests.test_glass_opening_nesting import _lifecycle_placed_row
    from almdina_erp.tests.test_cutter_center_paths import _import,_order,_piece
    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import sanitize_plan_snapshot
    from almdina_erp.almdina_erp.services.export_validation_service import _plan_to_export_snapshot
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors
    from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf
    count = len(outcome.snapshot["sheets"])
    saved = sanitize_plan_snapshot(json.loads(json.dumps(outcome.snapshot)))
    placed_rows = []
    for sheet in saved["sheets"]:
        for piece in sheet["pieces"]:
            row = _lifecycle_placed_row(piece,sheet["sheet_no"])
            for key,value in piece.items():
                if hasattr(row,key) or key=="liner_specs_json":
                    setattr(row,key,value)
            placed_rows.append(row)
    cutting_plan = SimpleNamespace(snapshot_json=json.dumps(saved),
        placed_pieces=placed_rows,
        sources=[SimpleNamespace(sheet_no=s["sheet_no"],source_type="Full Board",remnant=None,
            board_item=None,material="",color="",thickness_mm=18,full_width_mm=1220,
            full_length_mm=2440,usable_width_mm=1220,usable_length_mm=2440,source_area_m2=2.9768)
            for s in saved["sheets"]],
        engine_version=saved["engine_version"],method_key=saved["method_key"],method_label=saved["method_label"],
        full_board_width_mm=1220,full_board_length_mm=2440,usable_board_width_mm=1220,usable_board_length_mm=2440,
        kerf_mm=5,trim_margin_mm=0,used_area_m2=saved["used_area_m2"],total_source_area_m2=saved["total_board_area_m2"],
        waste_area_m2=saved["waste_area_m2"],required_boards=count)
    rebuilt = _plan_to_export_snapshot(cutting_plan)
    from almdina_erp.almdina_erp.domain.cutting.machining_overlay import machining_metadata
    assert [machining_metadata(p) for s in saved["sheets"] for p in s["pieces"]] == [
        machining_metadata(p) for s in rebuilt["sheets"] for p in s["pieces"]]
    assert not _kerf_errors(rebuilt)
    cases = tmp_path/"multi.json"
    cases.write_text(json.dumps([rebuilt]))
    subprocess.run(["node",str(Path(__file__).parents[1]/"tests/js/secure_dxf_topology_export.test.js")],
        check=True,capture_output=True,text=True,
        env=dict(os.environ,PERIMETER_CASES=str(cases),PERIMETER_OUTPUT_DIR=str(tmp_path)))
    path = tmp_path/"0.dxf"
    path.write_bytes(rebuild_autocad_dxf(path.read_bytes()))
    order_rows = rows or [dict(s,qty=1,piece_instance_id=s["piece_instance_id"].rsplit(":",1)[0])
                          for s in outcome.expanded_pieces]
    order = _order([_piece(**dict(s,cut_width_cm=s.get("cut_width_cm",s["width_cm"]),
                                cut_length_cm=s.get("cut_length_cm",s["length_cm"])))
                    for s in order_rows])
    order.kerf_mm = 5
    from unittest.mock import patch
    from almdina_erp.almdina_erp.services import piece_cut_dimension_service
    # The isolated fixture supplies the exact persisted band thicknesses; only
    # the database catalog port is replaced. Cut-dimension validation runs.
    if edge_profiles is None:
        imported = _import(str(path),order,kerf_mm=5,trim_mm=0)
    else:
        with patch.object(piece_cut_dimension_service,"_default_profile_loader",lambda names: edge_profiles):
            imported = _import(str(path),order,kerf_mm=5,trim_mm=0)
    def geometry(plan):
        return sorted((s["sheet_no"],*(round(p[k],6) for k in ("x","y","w","h")))
                      for s in plan["sheets"] for p in s["pieces"])
    assert saved["validation"]["is_valid"]
    assert geometry(saved) == geometry(rebuilt) == geometry(imported)
    assert sorted(p["piece_instance_id"] for s in saved["sheets"] for p in s["pieces"]) == sorted(
        p["piece_instance_id"] for s in imported["sheets"] for p in s["pieces"])
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
    import math
    import ezdxf
    from almdina_erp.tests.test_cutter_center_paths import _layer_segments
    # Imported protected contours remain conservative/unsupported for System
    # ranking. Measure the actual emitted CUT_PATH, rather than coercing them
    # back into rectangles to make an unavailable imported score look exact.
    actual = sum(math.dist(*segment) for segment in _layer_segments(ezdxf.readfile(path),"CUT_PATH"))
    assert actual == pytest.approx(sum(sheet_cut_line_quality(s,.5)[0] for s in saved["sheets"]),abs=.05)
    assert imported["saw_center_status"] == "Present"
    assert len(imported["sheets"]) == count
