"""Replay isolated production geometry; never recalculate or write a live plan.

--baseline loads reviewed HEAD 50f2b956. --projection models the identical 1.5s
remaining refinement tail: the old code gives placement only 150ms of it.
--gallery projects five copies of the same saved candidate, not a capture of
the historical five native finalists (which the saved snapshot does not hold).
"""
import argparse
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from almdina_erp.tests.test_unified_final_placement import production_witness,production_projection,METRICS
from almdina_erp.tests.bench_final_placement_budget import process_peak_mib
from almdina_erp.almdina_erp.domain.cutting import edge_protection as current
from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as current_app
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import physical_edge_margins_mm


def baseline(path,name):
    spec=importlib.util.spec_from_loader(name,loader=None)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    code=subprocess.check_output(["git","show",f"50f2b956:{path}"],text=True,encoding="utf-8")
    exec(compile(code,"50f2b956/"+path,"exec"),module.__dict__)
    return module


def replay(order,*,old=False,projection=False,gallery=False):
    domain,app=current,current_app
    if old:
        domain=baseline("almdina_erp/almdina_erp/domain/cutting/edge_protection.py",
                        "almdina_erp.almdina_erp.domain.cutting._unified_old")
        app=baseline("almdina_erp/almdina_erp/application/cutting/optimize_order_plan.py",
                     "almdina_erp.almdina_erp.application.cutting._unified_old")
    raw,sources=production_witness(order)
    data=json.loads((Path(__file__).parent/"fixtures/unified_placement"/(order+".json")).read_text())
    prepared=(deepcopy(raw),sources,data)
    snapshots=[]
    protect=domain.protect_plan_edges
    finalize=app._snapshot_outcome
    def capture_projection(*args,**kwargs):
        result=finalize(*args,**kwargs)
        snapshots.append(deepcopy(result.snapshot.get("final_placement_diagnostics",{})))
        return result
    started=time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(patch.object(current,"protect_plan_edges",protect))
        stack.enter_context(patch.object(app,"_snapshot_outcome",capture_projection))
        if projection:
            def budget(command):
                stage_deadline=time.monotonic()+1.5
                return (app._projection_placement_budget(command,stage_deadline,.15,1,"isolated_refinement_tail")
                        if not old else dict(deadline=min(stage_deadline,time.monotonic()+.15),remaining_candidates=1))
            outcome=production_projection(order,application=app,budget=budget,prepared=prepared)
            result,decisions=outcome.snapshot,outcome.snapshot["edge_positioning"]
            diag=outcome.snapshot.get("final_placement_diagnostics",{})
        elif gallery:
            outcome=production_projection(order,application=app,gallery=True,prepared=prepared)
            result,decisions=outcome.snapshot,outcome.snapshot["edge_positioning"]
            diag=result.get("final_placement_diagnostics",{})
        else:
            diag={}
            result,decisions=protect(raw,sources,122,244,.5,policy=EdgeProtectionPolicy(15,20),
                max_centerable_edge_gap_cm=7,machine_type="Auto",mirroring_allowed=False,
                metric_options=METRICS,deadline_monotonic=time.monotonic()+30,diagnostics=diag)
    elapsed=time.perf_counter()-started
    assert not validate_plan(result,sources,122,244,kerf_cm=.5)
    def geometry(plan):
        return [[dict(id=p["id"],x=p["x"],y=p["y"],w=p["w"],h=p["h"],rotated=p["rotated"])
                 for p in s["pieces"]] for s in plan["sheets"]]
    reports=[]
    for before,after in zip(raw["sheets"],result["sheets"],strict=True):
        b,a=sheet_cut_line_quality(before,.5),sheet_cut_line_quality(after,.5)
        reports.append(dict(sheet_no=before["sheet_no"],before=physical_edge_margins_mm(before),
            after=physical_edge_margins_mm(after),cutter_before=b,cutter_after=a,
            changed=any(p["x"]!=q["x"] or p["y"]!=q["y"] for p,q in zip(before["pieces"],after["pieces"],strict=True))))
    return dict(order=order,baseline=old,mode="projection" if projection else "gallery" if gallery else "domain",
        boards=len(raw["sheets"]),pieces=len(sources),elapsed_sec=elapsed,process_peak_mib=process_peak_mib(),
        changed_boards=sum(s["changed"] for s in reports),reached=diag.get("sheets_reached"),
        tested=diag.get("tested"),accepted=diag.get("accepted"),rejected=diag.get("rejected"),
        reasons=dict(Counter(d["reason"] for d in decisions)),sheets=reports,
        largest_remnant_before=raw["industrial_metrics"]["largest_reusable_free_area_m2"],
        largest_remnant_after=result["industrial_metrics"]["largest_reusable_free_area_m2"],
        diagnostics=diag,candidates=snapshots,decisions=decisions,geometry=geometry(result))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--baseline",action="store_true")
    parser.add_argument("--projection",action="store_true")
    parser.add_argument("--gallery",action="store_true")
    parser.add_argument("--synthetic",action="store_true")
    parser.add_argument("--orders",nargs="+",default=["26-00331","26-00344","26-00345","26-00346","26-00347"])
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.synthetic:
        from almdina_erp.tests.bench_final_placement_budget import benchmark
        module=(baseline("almdina_erp/almdina_erp/domain/cutting/edge_protection.py",
                         "almdina_erp.almdina_erp.domain.cutting._unified_old") if args.baseline else current)
        reports=[]
        for count in (1,2,8,17):
            report=benchmark(module,count,30,dense=True)
            reports.append(report)
            print(json.dumps({k:report[k] for k in ("boards","reached","trials","accepted","elapsed_ms","process_peak_mib")}),flush=True)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(reports,separators=(",",":"))+"\n",encoding="utf-8")
        sys.exit(0)
    reports=[]
    for order in args.orders:
        r=replay(order,old=args.baseline,projection=args.projection,gallery=args.gallery)
        reports.append(r)
        print(json.dumps({k:r[k] for k in ("order","mode","baseline","elapsed_sec","reached","tested","accepted","changed_boards","process_peak_mib")}),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(reports,separators=(",",":"))+"\n",encoding="utf-8")
