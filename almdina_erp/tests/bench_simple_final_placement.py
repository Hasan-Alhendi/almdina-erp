"""Actual optimizer from isolated order dimensions; no search replacement.

Run baseline/candidate sequentially with identical settings. Captured pre-stage
plans prove positioning's own board count and rigid-geometry invariants.
"""
import argparse
from copy import deepcopy
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

from almdina_erp.tests.test_simple_final_placement import ORDERS, METRICS, order_data, captured_plan, finish
from almdina_erp.tests.simple_placement_support import assert_snapshot_dxf_roundtrip
from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as current
from almdina_erp.almdina_erp.domain.cutting import final_sheet_positioning as positioning
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import physical_edge_margins_mm
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter


def baseline_application():
    name="almdina_erp.almdina_erp.application.cutting._simple_baseline"
    spec=importlib.util.spec_from_loader(name,loader=None)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    path="almdina_erp/almdina_erp/application/cutting/optimize_order_plan.py"
    code=subprocess.check_output(["git","show","origin/Develop:"+path],text=True,encoding="utf-8")
    exec(compile(code,"Develop/"+path,"exec"),module.__dict__)
    return module


def sheet_report(before,after,report):
    deltas=[(b["x"]-a["x"],b["y"]-a["y"]) for a,b in zip(before["pieces"],after["pieces"],strict=True)]
    if deltas:
        assert all(abs(x-deltas[0][0])<1e-7 and abs(y-deltas[0][1])<1e-7 for x,y in deltas)
    assert [(p["id"],p["piece_instance_id"],p["w"],p["h"],p["rotated"]) for p in before["pieces"]] == [
        (p["id"],p["piece_instance_id"],p["w"],p["h"],p["rotated"]) for p in after["pieces"]]
    assert before["applied_trim_width_cm"] == after["applied_trim_width_cm"]
    assert before["applied_trim_length_cm"] == after["applied_trim_length_cm"]
    return dict(**report,before_mm=physical_edge_margins_mm(before),after_mm=physical_edge_margins_mm(after),
        cutter_before=sheet_cut_line_quality(before,.5),cutter_after=sheet_cut_line_quality(after,.5))


def run(order,application,seconds,old):
    data=order_data(order)
    prepared=[]
    position=positioning.position_final_sheets
    def observe(plan,*args,**kwargs):
        result,diag=position(plan,*args,**kwargs)
        assert len(plan["sheets"]) == len(result["sheets"])
        prepared.append(dict(sheets=[sheet_report(a,b,d) for a,b,d in
            zip(plan["sheets"],result["sheets"],diag["sheets"],strict=True)],**{
                k:v for k,v in diag.items() if k!="sheets"}))
        return result,diag
    options=dict(max_centerable_edge_gap_cm=7,alignment_search_budget_sec=30,
                 alns_search_budget_sec=10,pattern_search_budget_sec=10,corner_search_budget_sec=10)
    if not old:
        options["edge_protection"]=EdgeProtectionPolicy(15,20)
    command=application.OptimizeOrderPlanCommand("simple-native-benchmark","isolated-input",
        application.BoardGeometry(122,244,0,.5),
        application.OptimizerOptions("smart","Auto",seconds,40,**METRICS,**options),tuple(data["rows"]))
    positioning.position_final_sheets=observe
    started=perf_counter()
    try:
        outcome=application.optimize_order_plan(command,engine=DomainCuttingEngineAdapter())
    finally:
        positioning.position_final_sheets=position
    elapsed=perf_counter()-started
    snapshot=outcome.snapshot
    assert snapshot["validation"]["is_valid"],snapshot["validation"]
    assert not validate_plan(snapshot,list(outcome.expanded_pieces),122,244,kerf_cm=.5)
    roundtrip="not run for baseline"
    if not old:
        with tempfile.TemporaryDirectory() as tmp:
            assert_snapshot_dxf_roundtrip(Path(tmp),outcome,rows=data["order_rows"],edge_profiles=data["edge_profiles"])
        roundtrip="passed"
    captured=None
    if not old:
        before,sources=captured_plan(order)
        after,diag=finish(before,sources)
        captured=dict(**{k:v for k,v in diag.items() if k!="sheets"},sheets=[sheet_report(a,b,d) for a,b,d in
            zip(before["sheets"],after["sheets"],diag["sheets"],strict=True)])
    return dict(order=order,baseline=old,search_limit_sec=seconds,elapsed_sec=elapsed,
        boards=len(snapshot["sheets"]),pieces=len(outcome.expanded_pieces),
        candidates=len(outcome.candidate_snapshots),attempts=snapshot["attempts"],
        industrial_metrics=snapshot["industrial_metrics"],native_candidates=prepared,
        captured_geometry=captured,dxf_strict_reimport=roundtrip,
        snapshot=snapshot)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--baseline",action="store_true")
    parser.add_argument("--seconds",type=float,default=120)
    parser.add_argument("--orders",nargs="+",default=ORDERS)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    application=baseline_application() if args.baseline else current
    runtime_paths=["almdina_erp/almdina_erp/application/cutting/optimize_order_plan.py",
        "almdina_erp/almdina_erp/domain/cutting/final_sheet_positioning.py",
        "almdina_erp/almdina_erp/domain/cutting/optimizer.py",
        "almdina_erp/almdina_erp/domain/cutting/cut_line_quality.py"]
    runtime_digest=hashlib.sha256(b"".join(Path(path).read_bytes() for path in runtime_paths)).hexdigest()
    reports=json.loads(args.output.read_text()) if args.output.exists() else []
    reports=[report for report in reports if report["order"] not in args.orders]
    for order in args.orders:
        report=run(order,application,args.seconds,args.baseline)
        report["runtime_source_sha256"]=runtime_digest
        reports.append(report)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(reports,separators=(",",":"))+"\n",encoding="utf-8")
        print(json.dumps({k:report[k] for k in ("order","baseline","boards","pieces","candidates","attempts","elapsed_sec","dxf_strict_reimport")}),flush=True)
