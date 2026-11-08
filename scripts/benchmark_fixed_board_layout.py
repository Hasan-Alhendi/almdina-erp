"""Fixed-count ALNS ablations using actual Application and JS/Strict Import.

Fresh sequential workers. Default cohort starts from previous system-derived
research snapshots; its cost is additional to creating those snapshots.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_alns import command_for, metrics, strict_check, source_manifest
from scripts.benchmark_abc import peak_rss_kib
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import (
    OPERATORS, FixedBoardSearchPolicy, improve_fixed_board_layout, material_signature)
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys

ARMS = ("baseline", "aa", *OPERATORS, "fixed", "adaptive", "align", "previous")


def manifest():
    result = source_manifest()
    for path in (Path(__file__), ROOT/"scripts/alns_research.py",
                 ROOT/"almdina_erp/tests/test_fixed_board_layout_search.py"):
        if path.exists():
            result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def worker(args):
    case = json.loads((ROOT/f"docs/evidence/alns-study/input-{args.case}.json").read_text(encoding="utf-8"))
    previous = ROOT/f"docs/evidence/alns-study/followup/{args.case}-checkpoint-adaptive-r0.json"
    incumbent = json.loads(previous.read_text(encoding="utf-8"))["snapshot"]
    policy = FixedBoardSearchPolicy(operators=(args.arm,) if args.arm in OPERATORS else OPERATORS,
        adaptive=args.arm == "adaptive", max_attempts=args.attempts, seed=args.seed,
        refine_seconds=args.refine_seconds)

    class Engine(DomainCuttingEngineAdapter):
        def optimize(self, sources, width, height, kerf, **kwargs):
            start = time.monotonic()
            deadline = start+kwargs["time_limit_sec"]
            if args.operational:
                options = dict(kwargs)
                if args.arm not in {"baseline", "aa", "align"}:
                    options["time_limit_sec"] *= .65
                plan = super().optimize(sources, width, height, kerf, **options)
                raw = deepcopy(plan.get("smart_candidates") or [plan])
                raw.sort(key=lambda p: tuple(p["industrial_rank"]))
            else:
                plan = deepcopy(incumbent)
                for key in ("smart_candidates", "smart_research_candidates"):
                    plan.pop(key, None)
                raw = [deepcopy(plan)]
            self.trace = None
            if args.arm not in {"baseline", "aa", "align"}:
                if args.arm == "previous":
                    from scripts.alns_research import Policy, run_alns
                    proposals, self.trace = run_alns(raw[0], sources, width, height, kerf, deadline=deadline,
                        policy=Policy(adaptive=True, max_attempts=args.attempts, max_boards=7,
                                      area_first=True, screen_prefix=True), machine=args.machine)
                else:
                    proposals, self.trace = improve_fixed_board_layout(raw[0], sources, width, height, kerf,
                        deadline=deadline, policy=policy, machine_type=args.machine)
                seen = {material_signature(p) for p in raw}
                for p in proposals:
                    signature = material_signature(p)
                    if signature not in seen:
                        raw.append(p)
                        seen.add(signature)
            plan["smart_candidates"] = raw
            self.raw = deepcopy(raw)
            return plan

    engine = Engine()
    start, cpu = time.perf_counter(), time.process_time()
    outcome = optimize_order_plan(command_for(case, args), engine=engine)
    wall, cpu = time.perf_counter()-start, time.process_time()-cpu
    snapshots = list(outcome.candidate_snapshots or (outcome.snapshot,))
    # Preserve and report *all* final snapshots for physical diversity auditing.
    result = dict(case=args.case, arm=args.arm, status="completed", operational=args.operational,
        budget=args.budget, seed=args.seed, attempts_cap=args.attempts, alignment_sec=args.alignment_sec,
        refine_seconds=args.refine_seconds,
        source_manifest=manifest(), incumbent_sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),
        input_sha256=hashlib.sha256((ROOT/f"docs/evidence/alns-study/input-{args.case}.json").read_bytes()).hexdigest(),
        valid=outcome.snapshot["validation"]["is_valid"], wall=wall, cpu=cpu,
        peak_rss_kib=peak_rss_kib(), final=metrics(outcome.snapshot, .5), trace=engine.trace,
        snapshot=outcome.snapshot, gallery=snapshots, physical_gallery=len({material_signature(p) for p in snapshots}), strict=[])
    for i, snapshot in enumerate(snapshots):
        try:
            passed = strict_check(snapshot, case["rows"]) if args.strict else None
            result["strict"].append(dict(candidate=i, passed=passed))
        except Exception as exc:
            result["strict"].append(dict(candidate=i, passed=False, error=f"{type(exc).__name__}: {exc}"))
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker", action="store_true")
    p.add_argument("--case", choices=["263", "298"], default="263")
    p.add_argument("--cases", nargs="+", default=["263", "298"])
    p.add_argument("--arm", choices=ARMS, default="baseline")
    p.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--budget", type=float, default=5)
    p.add_argument("--attempts", type=int, default=96)
    p.add_argument("--refine-seconds", type=float, default=0)
    p.add_argument("--seed", type=int, default=110526)
    p.add_argument("--operational", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--alignment-sec", type=float, default=0)
    p.add_argument("--kerf-mm", type=float, default=5)
    p.add_argument("--trim-mm", type=float, default=0)
    p.add_argument("--machine", default="CNC Router")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    if (args.kerf_mm,args.trim_mm,args.machine)!=(5,0,"CNC Router"):
        p.error("Frozen incumbent cohort requires CNC Router, Kerf 5 mm and Trim 0")
    if args.worker:
        worker(args)
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if (output/"index.json").exists():
        raise FileExistsError("Use a fresh evidence directory")
    records, sources = [], manifest()
    for case in args.cases:
        for repeat in range(args.repeats):
            for arm in (args.arms if repeat % 2 == 0 else list(reversed(args.arms))):
                destination = output/f"{case}-{arm}-r{repeat}.json"
                command = [sys.executable, __file__, "--worker", "--case", case, "--arm", arm,
                    "--budget", str(args.budget), "--attempts", str(args.attempts), "--seed", str(args.seed),
                    "--refine-seconds", str(args.refine_seconds),
                    "--alignment-sec", str(1 if arm == "align" else args.alignment_sec),
                    "--output", str(destination)]
                if args.operational:
                    command.append("--operational")
                if args.strict:
                    command.append("--strict")
                try:
                    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
                    if completed.returncode:
                        result = dict(status="worker_failed", returncode=completed.returncode, stderr=completed.stderr)
                        destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
                    else:
                        result = json.loads(destination.read_text(encoding="utf-8"))
                except subprocess.TimeoutExpired as exc:
                    result = dict(status="worker_timeout", stderr=str(exc.stderr))
                    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
                if result.get("status") == "completed" and result.get("source_manifest") != sources:
                    result["status"] = "source_changed"
                    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
                row = dict(case=case, arm=arm, repeat=repeat, file=destination.name,
                    sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), status=result["status"],
                    final=result.get("final"), wall=result.get("wall"), valid=result.get("valid"),
                    strict=result.get("strict"), attempts=(result.get("trace") or {}).get("attempts", 0))
                records.append(row)
                (output/"index.json").write_text(json.dumps(dict(source_manifest=sources, records=records), indent=2), encoding="utf-8")
                print(case, arm, repeat, row["status"], row["final"], row["attempts"], flush=True)
    if any(r["status"] != "completed" or not r["valid"] or any(s["passed"] is False for s in r["strict"] or []) for r in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
