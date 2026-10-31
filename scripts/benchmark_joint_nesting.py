"""Measure source-only joint witnesses against the modules of the current checkout."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.path.insert(0, os.getcwd())
from benchmark_cutting_p1 import RecordingEngine
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry, OptimizeOrderPlanCommand, OptimizerOptions, optimize_order_plan,
)


class JointRecordingEngine(RecordingEngine):
    def optimize(self, *args, **kwargs):
        self.raw_plan = super().optimize(*args, **kwargs)
        return self.raw_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-file', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--time-limit', type=float, default=10)
    parser.add_argument('--machine-type', default='CNC Router', choices=['CNC Router', 'Panel Saw'])
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('joint_cases', args.cases_file)
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    results = []
    for name, (width, height, trim, _) in cases.CASES.items():
        rows = cases.source_rows(name)
        engine = JointRecordingEngine()
        started = time.monotonic()
        outcome = optimize_order_plan(OptimizeOrderPlanCommand(
            engine_version='joint-benchmark', input_fingerprint='joint-benchmark',
            board=BoardGeometry(width, height, trim, .3),
            optimizer=OptimizerOptions('Smart Search', args.machine_type, args.time_limit, 20, 30, 30, .09),
            piece_rows=tuple(rows)), engine=engine)
        elapsed = time.monotonic()-started
        plan = outcome.snapshot
        diagnostic = dict((plan.get('smart_search') or {}).get('joint') or {})
        metrics = dict(case=name, label=args.label, machine_type=args.machine_type,
            head=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
            mode='Smart Search', time_limit_sec=args.time_limit, runtime_sec=elapsed,
            search_elapsed_sec=plan.get('search_elapsed_sec'), total_elapsed_sec=plan.get('total_elapsed_sec'),
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            boards=len(plan['sheets']), reusable_offcut_m2=plan['industrial_metrics']['largest_reusable_free_area_m2'],
            glass_guests=sum(bool(p.get('glass_host_piece_id')) for s in plan['sheets'] for p in s['pieces']),
            shape_void_guests=len((engine.raw_plan.get('shape_nesting_diagnostics') or {}).get('void_guests') or []),
            unique_candidates=len(outcome.candidate_snapshots), joint=diagnostic)
        results.append(dict(metrics, rows=rows, snapshot=plan, candidate_snapshots=list(outcome.candidate_snapshots)))
        Path(args.output).write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(json.dumps(metrics), flush=True)


if __name__ == '__main__':
    main()
