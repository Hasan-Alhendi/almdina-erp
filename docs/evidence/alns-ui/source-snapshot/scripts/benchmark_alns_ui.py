"""Run the same Application calculation as Recalculate, without a Frappe site.

Inputs are dimension/shape rows from the SYSTEM only. A designer pose is never
passed to the optimizer. Each arm is an isolated process with explicit budgets.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_alns import command_for, metrics, strict_check, source_manifest
from scripts.benchmark_abc import peak_rss_kib
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter


def worker(args):
    payload = Path(args.input).read_bytes()
    case = json.loads(payload)
    command = replace(command_for(case, args), allow_piece_mirroring=not args.no_mirroring)
    if args.refinement > 0:
        command = replace(command, optimizer=replace(command.optimizer, alns_search_budget_sec=args.refinement))
    start = time.monotonic()
    outcome = optimize_order_plan(command, engine=DomainCuttingEngineAdapter())
    elapsed = time.monotonic()-start
    gallery = list(outcome.candidate_snapshots or (outcome.snapshot,))
    manifest = source_manifest()
    for path in (Path(__file__), ROOT/'scripts/study_designer_layout.py'):
        manifest[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(status='completed',case=args.case, budget=args.budget, refinement=args.refinement,
        alignment_sec=args.alignment_sec, trim_mm=args.trim_mm, kerf_mm=args.kerf_mm,
        mirroring_allowed=not args.no_mirroring, wall=elapsed, peak_rss_kib=peak_rss_kib(),
        environment=dict(python=sys.version,platform=platform.platform(),
            versions={p:importlib.metadata.version(p) for p in ('ortools','ezdxf','pytest')}),
        input_sha256=hashlib.sha256(payload).hexdigest(),
        source_manifest=manifest, valid=outcome.snapshot['validation']['is_valid'],
        final=metrics(outcome.snapshot, args.kerf_mm/10), snapshot=outcome.snapshot,
        gallery=gallery, seeds=outcome.search_seeds, strict=[])
    if args.strict:
        for i, plan in enumerate(gallery):
            try:
                result['strict'].append(dict(candidate=i, passed=strict_check(plan, case['rows'])))
            except Exception as exc:
                result['strict'].append(dict(candidate=i, passed=False, error=f'{type(exc).__name__}: {exc}'))
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(args.case, args.budget, args.refinement, elapsed, result['final'], result['strict'], flush=True)
    if not result['valid'] or any(not r['passed'] for r in result['strict']):
        raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', action='store_true')
    p.add_argument('--matrix', action='store_true', help='Native N, ALNS N+min(N,10), native equal-total allowance')
    p.add_argument('--cases', nargs='+', default=['108', '154'])
    p.add_argument('--case', default='108')
    p.add_argument('--input')
    p.add_argument('--budget', type=float, default=5)
    p.add_argument('--refinement', type=float, default=0)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--alignment-sec', type=float, default=1)
    p.add_argument('--trim-mm', type=float, default=0)
    p.add_argument('--kerf-mm', type=float, default=5)
    p.add_argument('--machine', default='CNC Router')
    p.add_argument('--strict', action='store_true')
    p.add_argument('--no-mirroring', action='store_true')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    if (not all(math.isfinite(v) for v in (args.budget,args.refinement,args.trim_mm,args.kerf_mm))
            or args.budget <= 0 or min(args.refinement,args.trim_mm,args.kerf_mm) < 0):
        p.error('Finite positive search time and nonnegative physical/refinement settings required')
    if args.worker:
        worker(args)
        return
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if (output/'index.json').exists():
        raise FileExistsError('Use a fresh benchmark directory')
    records = []
    extra = min(args.budget,10)
    arms = [('native',args.budget,0),('alns',args.budget,extra),('equal_total_native',args.budget+extra,0)] if args.matrix else [('configured',args.budget,args.refinement)]
    for repeat in range(args.repeats):
        for case in args.cases:
            source = ROOT/f'docs/evidence/alns-ui/input-{case}.json'
            if not source.exists():
                source = ROOT/f'docs/evidence/alns-study/input-{case}.json'
            for arm,budget,refinement in (arms if repeat%2==0 else list(reversed(arms))):
                target = output/f'{case}-{arm}-r{repeat}.json'
                command = [sys.executable, __file__, '--worker', '--case', case, '--input', str(source),
                    '--budget', str(budget), '--refinement', str(refinement),
                    '--alignment-sec', str(args.alignment_sec), '--trim-mm', str(args.trim_mm),
                    '--kerf-mm',str(args.kerf_mm),'--machine',args.machine,'--output', str(target)]
                if args.strict:
                    command.append('--strict')
                if args.no_mirroring:
                    command.append('--no-mirroring')
                try:
                    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
                    print(run.stdout, flush=True)
                    row=dict(case=case,arm=arm,repeat=repeat,returncode=run.returncode,
                        file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None,
                        stderr=run.stderr)
                except subprocess.TimeoutExpired as exc:
                    row=dict(case=case,arm=arm,repeat=repeat,returncode=-1,file=target.name,
                             error='worker_timeout',stderr=str(exc.stderr))
                records.append(row)
                (output/'index.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    if any(r['returncode'] for r in records):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
