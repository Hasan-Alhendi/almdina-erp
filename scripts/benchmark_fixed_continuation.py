"""Compare native warm continuation with fixed-board refinement of the same seed."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_fixed_board_layout import manifest
from scripts.benchmark_alns import command_for,metrics,strict_check
from scripts.benchmark_abc import peak_rss_kib
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import (
    improve_fixed_board_layout, FixedBoardSearchPolicy, material_signature)


def worker(args):
    source=ROOT/f"docs/evidence/alns-study/followup/{args.case}-checkpoint-adaptive-r0.json"
    incumbent=json.loads(source.read_text())["snapshot"]
    case=json.loads((ROOT/f"docs/evidence/alns-study/input-{args.case}.json").read_text(encoding="utf-8"))
    class Engine(DomainCuttingEngineAdapter):
        def optimize(self,sources,width,height,kerf,**kw):
            self.trace=None
            if args.arm=="baseline":
                kw["seed_plans"]=(deepcopy(incumbent),)
                return super().optimize(sources,width,height,kerf,**kw)
            candidates,self.trace=improve_fixed_board_layout(incumbent,sources,width,height,kerf,
                deadline=time.monotonic()+kw["time_limit_sec"],
                policy=FixedBoardSearchPolicy(max_attempts=160,adaptive=True),machine_type=args.machine)
            return dict(deepcopy(incumbent),smart_candidates=candidates)
    engine=Engine()
    start,cpu=time.perf_counter(),time.process_time()
    outcome=optimize_order_plan(command_for(case,args),engine=engine)
    wall,cpu=time.perf_counter()-start,time.process_time()-cpu
    gallery=list(outcome.candidate_snapshots or (outcome.snapshot,))
    sources=manifest()
    sources[str(Path(__file__).relative_to(ROOT))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result=dict(status="completed",case=args.case,arm=args.arm,valid=outcome.snapshot["validation"]["is_valid"],
        budget=args.budget,alignment_sec=args.alignment_sec,wall=wall,cpu=cpu,peak_rss_kib=peak_rss_kib(),
        final=metrics(outcome.snapshot,.5),snapshot=outcome.snapshot,gallery=gallery,
        physical_gallery=len({material_signature(p) for p in gallery}),trace=engine.trace,
        source_manifest=sources,incumbent_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),strict=[])
    for i,view in enumerate(gallery):
        try:
            result["strict"].append(dict(candidate=i,passed=strict_check(view,case["rows"])))
        except Exception as exc:
            result["strict"].append(dict(candidate=i,passed=False,error=str(exc)))
    Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker",action="store_true")
    p.add_argument("--case",default="263")
    p.add_argument("--arm",choices=["baseline","adaptive"],default="baseline")
    p.add_argument("--budget",type=float,default=5)
    p.add_argument("--alignment-sec",type=float,default=1)
    p.add_argument("--kerf-mm",type=float,default=5)
    p.add_argument("--trim-mm",type=float,default=0)
    p.add_argument("--machine",default="CNC Router")
    p.add_argument("--output",required=True)
    args=p.parse_args()
    if (args.kerf_mm,args.trim_mm,args.machine)!=(5,0,"CNC Router"):
        p.error("Frozen incumbent cohort requires CNC Router, Kerf 5 mm and Trim 0")
    if args.worker:
        worker(args)
        return
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    if (output/"index.json").exists():
        raise FileExistsError("Use fresh evidence directory")
    records=[]
    for case in ("263","298"):
        for repeat in range(2):
            for arm in (["baseline","adaptive"] if repeat==0 else ["adaptive","baseline"]):
                path=output/f"{case}-{arm}-r{repeat}.json"
                run=subprocess.run([sys.executable,__file__,"--worker","--case",case,"--arm",arm,
                    "--budget",str(args.budget),"--alignment-sec",str(args.alignment_sec),"--output",str(path)],
                    cwd=ROOT,capture_output=True,text=True,timeout=120)
                if run.returncode:
                    result=dict(status="worker_failed",stderr=run.stderr)
                    path.write_text(json.dumps(result),encoding="utf-8")
                else:
                    result=json.loads(path.read_text())
                records.append(dict(case=case,arm=arm,repeat=repeat,file=path.name,
                    status=result["status"],sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                (output/"index.json").write_text(json.dumps(dict(records=records),indent=2),encoding="utf-8")
                print(case,arm,repeat,result["status"],result.get("final"),flush=True)
    if any(row["status"] != "completed" for row in records):
        raise SystemExit(1)


if __name__=="__main__":
    main()
