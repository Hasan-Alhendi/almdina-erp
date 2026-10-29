"""Matched P4/P5 sources, isolated worker per observation, real checkout engine.

Run this same script from each worktree with the same --fixtures-root. Only
reporting hooks count generated formations; no placement/rank setting changes.
"""
import argparse
from contextlib import ExitStack
import importlib.util
from itertools import combinations
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

sys.path.insert(0,os.getcwd())
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,OptimizeOrderPlanCommand,OptimizerOptions,optimize_order_plan)
from almdina_erp.almdina_erp.domain.cutting import shape_aware_nesting as shape


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases(root):
    old=load(root/'scripts/benchmark_cutting_p1.py','p4_bench_sources')
    joint=load(root/'almdina_erp/tests/joint_nesting_cases.py','p4_joint_sources')
    geometry=load(root/'almdina_erp/tests/geometry_nesting_cases.py','p5_sources')
    result=[]
    for machine in ('CNC Router','Panel Saw'):
        for name,(w,h,trim,rows) in old.CASES.items():
            result.append((name,machine,'Smart Search',w,h,trim,rows))
    for module in (joint,geometry):
        for name,(w,h,trim,_) in module.CASES.items():
            result.append((name,'CNC Router','Smart Search',w,h,trim,module.source_rows(name)))
    w,h,trim,rows=old.CASES['L-mixed']
    result.append(('L-mixed','CNC Router','Deep Search',w,h,trim,rows))
    return result


def coverage(plan):
    # Valid material can overlap a corner's box only in its actual missing area.
    kinds=set()
    for sheet in plan.get('sheets') or []:
        pieces=sheet.get('pieces') or []
        located={int(p['id']):p for p in pieces}
        for p in pieces:
            if p.get('glass_host_piece_id'):
                kinds.add('Glass')
            if p.get('piece_type') not in shape._CORNER_TYPES:
                continue
            ancestors=set()
            host=p.get('glass_host_piece_id')
            while host not in (None,'') and int(host) in located and int(host) not in ancestors:
                ancestors.add(int(host));host=located[int(host)].get('glass_host_piece_id')
            if any(p['id']!=q['id'] and int(q['id']) not in ancestors and
                   min(p['x']+p['w'],q['x']+q['w'])-max(p['x'],q['x'])>1e-6 and
                   min(p['y']+p['h'],q['y']+q['h'])-max(p['y'],q['y'])>1e-6 for q in pieces):
                kinds.add(p['piece_type'])
    if 'Glass' in kinds and len(kinds)>1:
        kinds.add('Joint')
    return sorted(kinds)


class ObservedEngine(DomainCuttingEngineAdapter):
    def optimize(self,*args,**kwargs):
        self.raw=super().optimize(*args,**kwargs)
        return self.raw


def measure(item,label,budget):
    name,machine,mode,w,h,trim,rows=item
    generated=set()
    def record(fn):
        def observed(*args,**kwargs):
            block=fn(*args,**kwargs)
            if block and block.get('pieces'):
                body=shape._normalize_pieces(block['pieces'])
                generated.add(tuple((int(p['id']),round(p['x'],8),round(p['y'],8),
                    int(p.get('corner_rotation_quarter_turns') or 0),bool(p.get('mirrored'))) for p in sorted(body,key=lambda p:int(p['id']))))
            return block
        return observed
    engine=ObservedEngine()
    with ExitStack() as stack:
        stack.enter_context(patch.object(shape,'_make_block',record(shape._make_block)))
        try:
            from almdina_erp.almdina_erp.domain.cutting import geometry_nesting
        except ImportError:
            pass  # Original HEAD has no P5 generator; production is not patched.
        else:
            stack.enter_context(patch.object(geometry_nesting,'_block',record(geometry_nesting._block)))
        started=time.monotonic()
        outcome=optimize_order_plan(OptimizeOrderPlanCommand(engine_version='p5-benchmark',input_fingerprint='p5-benchmark',
            board=BoardGeometry(w,h,trim,.3),optimizer=OptimizerOptions(mode,machine,budget,20,30,30,.09),
            piece_rows=tuple(rows)),engine=engine)
        elapsed=time.monotonic()-started
    plan=outcome.snapshot
    search=plan.get('smart_search') or {}
    corners=[p for p in outcome.expanded_pieces if p.get('piece_type') in shape._CORNER_TYPES]
    metrics=dict(case=name,machine_type=machine,mode=mode,budget_sec=budget,
        valid=plan['validation']['is_valid'],boards=len(plan['sheets']),
        offcut_m2=plan['industrial_metrics']['largest_reusable_free_area_m2'],
        rank=engine.raw.get('industrial_rank'),potential_shape_pairs=sum(a['piece_type']==b['piece_type'] for a,b in combinations(corners,2)),
        generated_unique_formations=len(generated),shape_first=search.get('shape_first') or {},
        joint=search.get('joint') or {},portfolio=search.get('portfolio') or {},
        final_plan_coverage=[coverage(c) for c in outcome.candidate_snapshots],
        best_coverage=coverage(plan),unique_candidates=len(outcome.candidate_snapshots),
        runtime_sec=elapsed,search_elapsed_sec=plan.get('search_elapsed_sec'),
        total_elapsed_sec=plan.get('total_elapsed_sec'),peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return dict(label=label,head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        case=name,machine_type=machine,mode=mode,full_board_cm=[w,h],preferred_trim_cm=trim,
        kerf_cm=.3,mirroring=False,remnant=[30,30,.09],time_limit_sec=budget,exact_piece_limit=20,
        runtime_sec=elapsed,rows=rows,snapshot=plan,candidate_snapshots=list(outcome.candidate_snapshots),metrics=metrics)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures-root',type=Path,required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--time-limit',type=float,default=10)
    parser.add_argument('--worker-index',type=int)
    args=parser.parse_args()
    inputs=cases(args.fixtures_root)
    if args.worker_index is not None:
        args.output.write_text(json.dumps(measure(inputs[args.worker_index],args.label,args.time_limit),ensure_ascii=False))
        return
    results=[]
    with TemporaryDirectory() as td:
        for index in range(len(inputs)):
            path=Path(td)/f'{index}.json'
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--fixtures-root',str(args.fixtures_root),
                '--label',args.label,'--output',str(path),'--time-limit',str(args.time_limit),
                '--worker-index',str(index)],check=True)
            row=json.loads(path.read_text())
            results.append(row)
            args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2))
            print(json.dumps(row['metrics']),flush=True)


if __name__=='__main__':
    main()
