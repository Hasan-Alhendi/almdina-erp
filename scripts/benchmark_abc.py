"""Eight-arm ABC research through actual Application; default production is off.

Inputs are anonymized/reconstructed, not authoritative live-order snapshots.
Run sequential fresh workers, record every result including crashes/timeouts.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_digest():
    files = [ROOT/"scripts/benchmark_abc.py"]
    files.extend((ROOT/"almdina_erp/almdina_erp/domain/cutting"/name) for name in
                 ("optimizer.py", "abc_search.py", "regular_templates.py", "plan_search.py",
                  "cut_line_quality.py", "kerf_layout.py"))
    files.extend(ROOT/p for p in (
        "almdina_erp/almdina_erp/application/cutting/optimize_order_plan.py",
        "almdina_erp/almdina_erp/infrastructure/cutting/domain_engine.py"))
    payload = [(str(p.relative_to(ROOT)), hashlib.sha256(p.read_bytes()).hexdigest()) for p in files]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def source_rows(case):
    if case == "regular-48":
        # Effective reconstructed dimensions, all rotations explicitly assumed;
        # no customer identities, material data, reference poses or warm plans.
        dimensions = [(29.9,57.3,2),(29.9,34.3,4),(29.9,56.8,4),(29.9,36.8,4),
                      (29.9,78.8,8),(16.4,78.8,2),(29.9,39.8,2),(17.2,16.4,4),
                      (11.9,38,8),(11.9,40,8),(79.7,40,2)]
        return 122, 244, [dict(width_cm=w, length_cm=h, qty=q, allow_rotation=1,
            piece_type="Regular", piece_instance_id=f"smart:{i}")
            for i, (w,h,q) in enumerate(dimensions, 1)]
    fixture = json.loads((ROOT / "almdina_erp/tests/fixtures/regroup_native_baselines.json").read_text())
    entry = fixture[case]
    return entry["width"], entry["height"], [dict(deepcopy(row), piece_instance_id=f"smart:{i}")
                                               for i,row in enumerate(entry["rows"], 1)]


def peak_rss_kib():
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb",wintypes.DWORD),("faults",wintypes.DWORD)] + [
                (name,ctypes.c_size_t) for name in ("peak","working","peak_paged","paged",
                "peak_nonpaged","nonpaged","pagefile","peak_pagefile")]
        counter = Counters()
        counter.cb = ctypes.sizeof(counter)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        read = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        read.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not read(kernel.GetCurrentProcess(), ctypes.byref(counter), counter.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counter.peak//1024
    from scripts.research_direct_kerf import peak_rss_kib as linux_peak
    return linux_peak()


def worker(args):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
    )
    from almdina_erp.almdina_erp.domain.cutting.abc_search import ABCSearchPolicy
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import plan_cut_line_quality
    from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
    from scripts.research_direct_kerf import metrics
    width, height, rows = source_rows(args.case)
    flags = [value == "1" for value in args.arm]
    policy = ABCSearchPolicy(*flags, share=args.share) if any(flags) else None
    options = OptimizerOptions("smart", "CNC Router", args.budget, args.exact_piece_limit,
                               30, 30, .09, research_abc=policy)
    class Recording(DomainCuttingEngineAdapter):
        def optimize(self, *a, **kw):
            result = super().optimize(*a, **kw)
            self.domain = deepcopy(result)
            return result
    engine = Recording()
    start, cpu = time.perf_counter(), time.process_time()
    outcome = optimize_order_plan(OptimizeOrderPlanCommand("abc-research", "research-input",
        BoardGeometry(width, height, args.trim_mm/10, .5), options, tuple(rows)), engine=engine)
    elapsed, used_cpu = time.perf_counter()-start, time.process_time()-cpu
    snapshot = outcome.snapshot
    # Record work before serialization/optional export; RSS excludes child Node.
    result = dict(status="completed", source_digest=source_digest(), case=args.case, arm=args.arm, budget=args.budget,
        share=args.share, trim_mm=args.trim_mm, exact_piece_limit=args.exact_piece_limit,
        input_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
        elapsed=elapsed, cpu=used_cpu, peak_rss_kib=peak_rss_kib(), overrun=max(0,elapsed-args.budget),
        native_elapsed=engine.domain.get("search_elapsed_sec"),
        valid=snapshot["validation"]["is_valid"], final=metrics(snapshot),
        real_cut_profile=plan_cut_line_quality(snapshot,.5),
        geometry_signature=geometry_signature(snapshot),
        abc=(engine.domain.get("smart_search") or {}).get("abc_research"),
        gallery_count=len(outcome.candidate_snapshots), strict_import=None)
    if args.strict:
        from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
        from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
        with tempfile.TemporaryDirectory() as directory:
            reloaded = json.loads(json.dumps(snapshot))
            imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, Path(directory)))
            def material(p):
                # DXF may renumber/reorder full sheets and equal source copies.
                # Compare complete per-board family geometry, not display IDs.
                return sorted(tuple(sorted((v["source_piece_no"],
                    *(round(v[k],5) for k in ("x","y","w","h"))) for v in s["pieces"]))
                    for s in p["sheets"])
            if material(imported) != material(reloaded):
                raise AssertionError("Strict import changed family placements")
            if sorted(p["piece_instance_id"] for s in imported["sheets"] for p in s["pieces"]) != sorted(
                    p["piece_instance_id"] for s in reloaded["sheets"] for p in s["pieces"]):
                raise AssertionError("Strict import changed identity inventory")
        result["strict_import"] = True
    Path(args.output).write_text(json.dumps(result), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case", default="regular-48")
    parser.add_argument("--cases", nargs="+", default=["regular-48", "3687"])
    parser.add_argument("--arm", choices=["".join(v) for v in itertools.product("01",repeat=3)], default="000")
    parser.add_argument("--arms", nargs="+", default=["".join(v) for v in itertools.product("01",repeat=3)])
    parser.add_argument("--budget", type=float, default=5)
    parser.add_argument("--share", type=float, default=.1)
    parser.add_argument("--trim-mm", type=float, default=0)
    parser.add_argument("--exact-piece-limit", type=int, default=40)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    records = []
    artifact = dict(source_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        source_digest=source_digest(),
        working_tree_dirty=bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True).strip()),
        platform=platform.platform(), python=sys.version, versions={p:importlib.metadata.version(p)
        for p in ("pytest","ezdxf","ortools")}, provenance="reconstructed input-only; not a live production comparison",
        records=records)
    for case in args.cases:
        for repeat in range(args.repeats):
            for arm in (args.arms if repeat%2 == 0 else list(reversed(args.arms))):
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory)/"worker.json"
                    command = [sys.executable,__file__,"--worker","--case",case,"--arm",arm,
                        "--budget",str(args.budget),"--share",str(args.share),"--trim-mm",str(args.trim_mm),
                        "--exact-piece-limit",str(args.exact_piece_limit),"--output",str(output)]
                    if args.strict: command.append("--strict")
                    try:
                        run = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,
                                             timeout=max(60,args.budget*5))
                        row = (json.loads(output.read_text(encoding="utf-8")) if run.returncode == 0 else
                               dict(status="worker_failed",returncode=run.returncode,stderr=run.stderr[-6000:]))
                    except subprocess.TimeoutExpired:
                        row = dict(status="worker_timeout")
                if row.get("status") == "completed" and row.get("source_digest") != artifact["source_digest"]:
                    row["status"] = "source_changed_during_run"
                row.update(case=case,arm=arm,repeat=repeat)
                records.append(row)
                Path(args.output).write_text(json.dumps(artifact,indent=2),encoding="utf-8")
                print(case,repeat,arm,row["status"],row.get("final",{}).get("boards"),flush=True)
    if any(r.get("status") != "completed" or not r.get("valid") for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
