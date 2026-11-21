"""Reproducible synthetic scheduling benchmark; never customer-plan evidence.

Run from the repository: python -m almdina_erp.tests.bench_final_placement_budget
Optional --baseline loads the unchanged 1a07d119 domain module for comparison.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import tracemalloc
from unittest.mock import patch

from almdina_erp.tests.test_final_placement_budget import multi_board_witness, METRICS
from almdina_erp.almdina_erp.domain.cutting import edge_protection
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.plan_settings import EdgeProtectionPolicy
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import physical_edge_margins_mm


def process_peak_mib():
    """OS process peak, including fixtures/imports; not Python allocations alone."""
    if sys.platform == "win32":
        import ctypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb",ctypes.c_ulong),("faults",ctypes.c_ulong)]+[
                (name,ctypes.c_size_t) for name in ("peak","working","peak_paged","paged",
                    "peak_nonpaged","nonpaged","pagefile","peak_pagefile")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(counters),counters.cb):
            return None
        return round(counters.peak/1048576,3)
    import resource
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1048576 if sys.platform=="darwin" else 1024),3)


def benchmark(module, count, seconds, *, dense=False, memory=False, application=None):
    plan,sources = multi_board_witness(count,dense=dense)
    durations, calls, reached = defaultdict(float),Counter(),set()
    stack = []
    def instrument(name, original):
        def measured(*args,**kwargs):
            if name == "translation":
                reached.add(args[1])
            started = time.perf_counter()
            stack.append([name,started,0.0])
            try:
                return original(*args,**kwargs)
            finally:
                _,_,children = stack.pop()
                elapsed = time.perf_counter()-started
                durations[name] += elapsed-children
                calls[name] += 1
                if stack:
                    stack[-1][2] += elapsed
        return measured
    stages = dict(_placement_goals="groups",_proposals="generation_sort",
        _candidate_moves="alignment_events",_projected_axis_gain="event_score",
        sheet_cut_line_quality="cutter",_remnants_preserved="remnants",
        validate_plan="geometry",placement_permission_errors="permissions",
        manufacturing_export_rejection="export_check",enrich_plan_metrics="metrics",
        _translate_group_moves_if_clear="translation")
    diagnostics, candidate_reports, finalization_ms = {},[],[]
    with ExitStack() as patches:
        for name,stage in stages.items():
            if hasattr(module,name):
                patches.enter_context(patch.object(module,name,instrument(stage,getattr(module,name))))
        if memory:
            tracemalloc.start()
        started = time.perf_counter()
        if application is None:
            result,decisions = module.protect_plan_edges(plan,sources,122,244,.5,
                policy=EdgeProtectionPolicy(15,20),max_centerable_edge_gap_cm=7,
                machine_type="CNC Router",mirroring_allowed=False,metric_options=METRICS,
                deadline_monotonic=time.monotonic()+seconds,diagnostics=diagnostics)
        else:
            from almdina_erp.tests.test_final_placement_budget import gallery_witness_outcome
            protect,finalize = module.protect_plan_edges,application._snapshot_outcome
            def capture(*args,**kwargs):
                reached.clear()
                detail = kwargs.setdefault("diagnostics",{})
                mark = time.perf_counter()
                result = protect(*args,**kwargs)
                candidate_reports.append(dict(reached=len(reached),search_ms=round((time.perf_counter()-mark)*1000,3),
                    tested=detail.get("tested"),accepted=detail.get("accepted"),rejected=detail.get("rejected"),
                    reasons=dict(Counter(d["reason"] for d in result[1]))))
                return result
            def finalized(*args,**kwargs):
                mark = time.perf_counter()
                result = finalize(*args,**kwargs)
                finalization_ms.append(round((time.perf_counter()-mark)*1000,3))
                return result
            patches.enter_context(patch.object(edge_protection,"protect_plan_edges",capture))
            patches.enter_context(patch.object(application,"_snapshot_outcome",finalized))
            outcome = gallery_witness_outcome(count,dense=dense,seconds=seconds,application=application)
            result,decisions = outcome.snapshot,outcome.snapshot["edge_positioning"]
            for report,final_ms in zip(candidate_reports,finalization_ms,strict=True):
                report["finalization_ms"] = final_ms
                report["outside_search_ms"] = round(final_ms-report["search_ms"],3)
        elapsed = time.perf_counter()-started
        peak = tracemalloc.get_traced_memory()[1]/1048576 if memory else None
        if memory:
            tracemalloc.stop()
    assert not validate_plan(result,sources,122,244,kerf_cm=.5)
    profiles = [sheet_cut_line_quality(s,.5) for s in result["sheets"]]
    return dict(boards=count,pieces_per_board=len(plan["sheets"][0]["pieces"]),budget_sec=seconds,
        reached=len(reached),trials=diagnostics.get("tested"),accepted=diagnostics.get("accepted"),
        reasons=dict(Counter(d["reason"] for d in decisions)),
        details=dict(Counter(d.get("detail") for d in decisions)),
        rejected=diagnostics.get("rejected"),elapsed_ms=round(elapsed*1000,3),peak_mib=peak,
        process_peak_mib=process_peak_mib(),
        stages_ms={k:round(v*1000,3) for k,v in durations.items()},calls=dict(calls),
        margins=[physical_edge_margins_mm(s) for s in result["sheets"]],
        cutter_mm=round(sum(p[0] for p in profiles),4),
        largest_remnant_m2=result["industrial_metrics"]["largest_reusable_free_area_m2"],
        candidate_reports=candidate_reports,diagnostics=diagnostics)


def baseline_module(path,name):
    source=subprocess.check_output(["git","show",f"1a07d119:{path}"],text=True)
    spec=importlib.util.spec_from_loader(name,loader=None)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    exec(compile(source,f"1a07d119/{path}","exec"),module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline",action="store_true")
    parser.add_argument("--boards",type=int,nargs="+",default=[1,2,8,17])
    parser.add_argument("--seconds",type=float,default=3)
    parser.add_argument("--dense",action="store_true")
    parser.add_argument("--memory",action="store_true")
    parser.add_argument("--gallery",action="store_true")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    module,application=edge_protection,None
    if args.baseline:
        module=baseline_module("almdina_erp/almdina_erp/domain/cutting/edge_protection.py",
                               "almdina_erp.almdina_erp.domain.cutting._budget_baseline")
    if args.gallery:
        from almdina_erp.almdina_erp.application.cutting import optimize_order_plan as application
        if args.baseline:
            application=baseline_module("almdina_erp/almdina_erp/application/cutting/optimize_order_plan.py",
                                         "almdina_erp.almdina_erp.application.cutting._budget_baseline")
    results = []
    for count in args.boards:
        report=benchmark(module,count,args.seconds,dense=args.dense,memory=args.memory,application=application)
        results.append(report)
        print(json.dumps({k:v for k,v in report.items() if k not in {"diagnostics","margins"}}),flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(results,separators=(",",":"))+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
