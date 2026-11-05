"""Compare the final Application winner against an immutable baseline revision.

Run from the repo root. Each observation is a fresh sequential Linux worker;
no production data/database is read or changed. Reuses reconstructed geometry
fixtures; their all-rotation/full-board assumptions are NOT DCO provenance.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.research_direct_kerf import case_data, metrics, peak_rss_kib, strict_roundtrip
from almdina_erp.almdina_erp.domain.cutting import optimizer as opt, plan_search
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry, OptimizerOptions, OptimizeOrderPlanCommand, optimize_order_plan,
)
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature

BASE = '76698c5ae2fcd89e50598773578b101203e98329'


def inputs(name):
    if name != '243-canonical':
        case, rows, _ = case_data(name)
        return case, rows
    from almdina_erp.tests.cutting_243_cases import source_case
    case = source_case()
    return dict(width=122, height=244), [dict(row, piece_instance_id=f'smart:{i}')
        for i, row in enumerate(case['rows'], 1)]


def worker(args):
    finish = opt._finish_plan_search
    if args.variant in {'baseline', 'validation-only'}:
        for module in (plan_search, opt):
            path = Path(module.__file__).resolve().relative_to(Path.cwd())
            source = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:{path}'], text=True)
            exec(compile(source, str(module.__file__), 'exec'), module.__dict__)
        if args.variant == 'validation-only':
            opt._finish_plan_search = finish
    case, rows = inputs(args.case)
    class RecordingEngine(DomainCuttingEngineAdapter):
        def optimize(self, *a, **kw):
            result = super().optimize(*a, **kw)
            self.domain = deepcopy(result)
            return result
    engine = RecordingEngine()
    start, cpu = time.perf_counter(), time.process_time()
    outcome = optimize_order_plan(OptimizeOrderPlanCommand(
        'layout-research', 'layout-research',
        BoardGeometry(case['width'], case['height'], args.trim_mm/10, .5),
        OptimizerOptions('smart', 'CNC Router', args.budget, 40, 30, 30, .09),
        tuple(rows)), engine=engine)
    elapsed, cpu = time.perf_counter()-start, time.process_time()-cpu
    rss = peak_rss_kib()
    result = dict(case=args.case, variant=args.variant, budget=args.budget,
        trim_mm=args.trim_mm, elapsed=elapsed, cpu=cpu, rss_kib=rss,
        overrun=max(0, elapsed-args.budget), domain=metrics(engine.domain),
        final=metrics(outcome.snapshot), valid=outcome.snapshot['validation']['is_valid'],
        snapshot=outcome.snapshot, domain_plan=engine.domain)
    Path(args.output).write_text(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--variant', choices=['baseline', 'validation-only', 'candidate'], default='candidate')
    parser.add_argument('--baseline-ref', default=BASE)
    parser.add_argument('--case', default='3687')
    parser.add_argument('--cases', nargs='+', default=['3687','243','107','232','235','325','3688','3700','3640'])
    parser.add_argument('--budget', type=float, default=5)
    parser.add_argument('--trim-mm', type=float, default=3)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    observations = []
    for name in args.cases:
        case, rows = inputs(name)
        for repeat in range(args.repeats):
            for variant in (['baseline','candidate'] if repeat % 2 == 0 else ['candidate','baseline']):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory)/'result.json'
                    subprocess.run([sys.executable, __file__, '--worker', '--case', name,
                        '--variant', variant, '--baseline-ref', args.baseline_ref,
                        '--budget', str(args.budget), '--trim-mm', str(args.trim_mm),
                        '--output', str(path)], check=True)
                    row = json.loads(path.read_text())
                row['repeat'] = repeat
                snapshot = row.pop('snapshot')
                row.pop('domain_plan')
                row['geometry'] = geometry_signature(snapshot)
                row['strict'] = None
                if variant == 'candidate':
                    # Actual final winner -> serialize/reload -> actual JS ->
                    # full strict import, even when it matches the baseline.
                    with tempfile.TemporaryDirectory() as directory:
                        saved = Path(directory)/'snapshot.json'
                        saved.write_text(json.dumps(snapshot))
                        reloaded = json.loads(saved.read_text())
                        assert geometry_signature(reloaded) == row['geometry']
                        # strict_roundtrip's defaults are 3mm; use the actual
                        # snapshot unchanged for the canonical margin controls.
                        if args.trim_mm == 3:
                            strict_roundtrip(reloaded, rows, case['width'], case['height'], Path(directory))
                        else:
                            from almdina_erp.tests.test_smart_cutting_manufacturing import import_saved_plan
                            from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js
                            imported = import_saved_plan(reloaded, rows, export_real_js(reloaded, Path(directory)))
                            assert sum(len(s['pieces']) for s in imported['sheets']) == sum(r['qty'] for r in rows)
                        row['strict'] = True
                observations.append(row)
                Path(args.output).write_text(json.dumps(observations, indent=2))
                print(name, repeat, variant, 'boards', row['final']['boards'],
                      'alignment', row['final']['alignment_ratio'], 'splits', row['final']['group_splits'],
                      'seconds', round(row['elapsed'], 3), flush=True)


if __name__ == '__main__':
    main()
