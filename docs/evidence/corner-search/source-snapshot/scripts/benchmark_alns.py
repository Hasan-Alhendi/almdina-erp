"""ALNS study: paired DXF audit, frozen-checkpoint ablations and equal-budget search.

All file writes are local research evidence. No Frappe site is contacted.
The SYSTEM DXF supplies dimensions only, never warm poses. The designer DXF
supplies comparison geometry only and is never sent to an optimizer.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.alns_dxf_inputs import paired_inputs
from scripts.alns_research import Policy, OPERATORS, run_alns
from scripts.benchmark_abc import peak_rss_kib
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan)
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import plan_cut_line_quality, final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.plan_search import _regular_layout_quality
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter


def source_manifest():
    files = sorted([*ROOT.glob("almdina_erp/almdina_erp/domain/cutting/**/*.py"),
        *ROOT.glob("almdina_erp/almdina_erp/application/cutting/*.py"),
        *ROOT.glob("almdina_erp/almdina_erp/infrastructure/cutting/*.py"),
        ROOT/"scripts/alns_dxf_inputs.py", ROOT/"scripts/alns_research.py", Path(__file__)])
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def metrics(plan, kerf):
    aligned, adjacent, splits = _regular_layout_quality(plan, kerf)
    return dict(boards=len(plan["sheets"]), pieces=sum(len(s["pieces"]) for s in plan["sheets"]),
        unplaced=len(plan.get("unplaced") or []), industrial_rank=plan.get("industrial_rank"),
        reusable_m2=(plan.get("industrial_metrics") or {}).get("largest_reusable_free_area_m2"),
        aligned=aligned, adjacent=adjacent, alignment_ratio=aligned/adjacent, family_splits=splits,
        cutter_profile=plan_cut_line_quality(plan, kerf), signature=geometry_signature(plan))


def strict_check(plan, rows):
    from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
    from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
    reloaded = json.loads(json.dumps(plan))
    with tempfile.TemporaryDirectory() as directory:
        imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, Path(directory)))
    def material(p):
        return sorted(tuple(sorted((v["source_piece_no"], *(round(v[k], 4) for k in ("x", "y", "w", "h")))
            for v in s["pieces"])) for s in p["sheets"])
    if material(imported) != material(reloaded):
        raise AssertionError("Strict import changed family geometry")
    ids = lambda p: sorted(v["piece_instance_id"] for s in p["sheets"] for v in s["pieces"])
    if ids(imported) != ids(reloaded):
        raise AssertionError("Strict import changed identity inventory")
    from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import parse_geometry_mm,geometry_mm_to_cm
    from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
    def polygons(p):
        def outer(part):
            if part.get('geometry'):
                return geometry_mm_to_cm(parse_geometry_mm(part['geometry'])).outer
            return material_outline_cm(part)
        return sorted(tuple(sorted(tuple(sorted((round(x,4),round(y,4)) for x,y in outer(part)))
            for part in sheet['pieces'])) for sheet in p['sheets'])
    if polygons(imported) != polygons(reloaded):
        raise AssertionError('Strict import changed actual material outlines')
    return True


def command_for(case, args):
    return OptimizeOrderPlanCommand("alns-research", "alns-research",
        BoardGeometry(case["width"], case["height"], args.trim_mm/10, args.kerf_mm/10),
        OptimizerOptions("smart", args.machine, args.budget, 40, 30, 30, .09,
                         alignment_search_budget_sec=args.alignment_sec), tuple(case["rows"]))


def worker(args):
    case = json.loads(Path(args.input).read_text(encoding="utf-8"))
    policy = Policy(operators=(args.arm,) if args.arm in OPERATORS else OPERATORS,
                    adaptive=args.arm == "adaptive", seed=args.seed, max_attempts=args.attempts,
                    max_boards=args.max_boards, area_first=args.area_first, screen_prefix=args.screen_prefix)
    class ResearchEngine(DomainCuttingEngineAdapter):
        def optimize(self, pieces, width, height, kerf, **kwargs):
            start = time.monotonic()
            deadline = start+kwargs["time_limit_sec"]
            if args.checkpoint:
                native = deepcopy(json.loads(Path(args.checkpoint).read_text(encoding="utf-8")))
            else:
                native_kw = dict(kwargs)
                if args.arm not in {"baseline", "aa"}:
                    native_kw["time_limit_sec"] *= 1-args.share
                native = super().optimize(pieces, width, height, kerf, **native_kw)
            self.native = deepcopy(native)
            self.trace = None
            if args.arm in {"baseline", "aa"}:
                return native
            # Preserve the *entire* native portfolio until real Application
            # projection. Raw proxy ranking cannot silently erase its winner.
            candidates = deepcopy(native.get("smart_candidates") or [native])
            candidates.sort(key=lambda p: tuple(p.get("industrial_rank") or ()))
            candidates, self.trace = self.research(candidates, pieces, width, height, kerf, deadline)
            native["smart_candidates"] = candidates
            return native

        def research(self, candidates, pieces, width, height, kerf, deadline):
            proposals, trace = run_alns(candidates[0], pieces, width, height, kerf,
                deadline=deadline, policy=policy, machine=args.machine)
            seen = {geometry_signature(p) for p in candidates}
            for p in proposals:
                signature = geometry_signature(p)
                if signature not in seen:
                    candidates.append(p)
                    seen.add(signature)
            return candidates, trace

    engine = ResearchEngine()
    start, cpu = time.perf_counter(), time.process_time()
    outcome = optimize_order_plan(command_for(case, args), engine=engine)
    wall, cpu = time.perf_counter()-start, time.process_time()-cpu
    candidates = list(outcome.candidate_snapshots or (outcome.snapshot,))
    result = dict(status="completed", case=args.case, arm=args.arm, checkpoint=bool(args.checkpoint),
        settings=dict(budget=args.budget, kerf_mm=args.kerf_mm, trim_mm=args.trim_mm,
                      machine=args.machine, alignment_sec=args.alignment_sec, native_share=1-args.share,
                      seed=args.seed, attempts=args.attempts, max_boards=args.max_boards,
                      area_first=args.area_first, screen_prefix=args.screen_prefix),
        input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        elapsed=wall, cpu=cpu, peak_rss_kib=peak_rss_kib(), overrun=max(0, wall-args.budget),
        valid=outcome.snapshot["validation"]["is_valid"], final=metrics(outcome.snapshot, args.kerf_mm/10),
        gallery=[metrics(p, args.kerf_mm/10) for p in candidates],
        trace=engine.trace, strict=[], snapshot=outcome.snapshot)
    # Write checkpoint before optional export. Its poses come ONLY from Smart.
    if args.native_output:
        Path(args.native_output).write_text(json.dumps(engine.native), encoding="utf-8")
    for i, p in enumerate(candidates):
        try:
            passed = strict_check(p, case["rows"]) if args.strict else None
            result["strict"].append(dict(candidate=i, passed=passed))
        except Exception as exc:
            result["strict"].append(dict(candidate=i, passed=False, error=f"{type(exc).__name__}: {exc}"))
    result["source_manifest"] = source_manifest()
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--downloads", default="C:/Users/HorizonTech/Downloads")
    parser.add_argument("--input")
    parser.add_argument("--case", default="263")
    parser.add_argument("--arm", choices=["baseline", "aa", "fixed", "adaptive", *OPERATORS], default="baseline")
    parser.add_argument("--budget", type=float, default=5)
    parser.add_argument("--share", type=float, default=.35)
    parser.add_argument("--kerf-mm", type=float, default=5)
    parser.add_argument("--trim-mm", type=float, default=0)
    parser.add_argument("--machine", choices=["CNC Router", "Panel Saw"], default="CNC Router")
    parser.add_argument("--alignment-sec", type=float, default=0)
    parser.add_argument("--seed", type=int, default=110526)
    parser.add_argument("--attempts", type=int, default=96)
    parser.add_argument("--max-boards", type=int, default=3)
    parser.add_argument("--area-first", action="store_true")
    parser.add_argument("--screen-prefix", action="store_true")
    parser.add_argument("--checkpoint")
    parser.add_argument("--native-output")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not all(math_is_finite_nonnegative(v) for v in (args.budget, args.kerf_mm, args.trim_mm, args.alignment_sec)) or not 0 < args.share < 1:
        parser.error("Invalid budget/geometry/share")
    if args.audit:
        d, output = Path(args.downloads), Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        for name in ("263", "298"):
            data = paired_inputs(d/f"cutting_plan_26-00{name}_AutoCAD2011_2026.dxf", d/f"{name}مصمم.dxf")
            for role in ("system", "designer"):
                raw = deepcopy(data[role]["layout"])
                # Supply evaluation metadata solely for geometric reference
                # measurements. This is never passed into search as a seed.
                for i, s in enumerate(raw["sheets"], 1):
                    s["sheet_no"] = i
                    for j, p in enumerate(s["pieces"], 1):
                        p.update(id=i*1000+j, area_m2=p["w"]*p["h"]/10000, rotated=False)
                ranked = enrich_plan_metrics(raw, "reference-only", "CNC Router")
                data[role]["measured"] = metrics(ranked, args.kerf_mm/10)
            (output/f"input-{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        provenance = dict(sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            tree=subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
            platform=platform.platform(), python=sys.version,
            versions={p: importlib.metadata.version(p) for p in ("ezdxf", "ortools", "pytest")},
            source_manifest=source_manifest())
        (output/"provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    elif args.worker:
        worker(args)
    else:
        parser.error("Use --audit or --worker; fresh workers are orchestrated externally")


def math_is_finite_nonnegative(value):
    import math
    return math.isfinite(value) and value >= 0


if __name__ == "__main__":
    main()
