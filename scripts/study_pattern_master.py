"""Offline feasibility probe; never imported by production or sent designer poses.

The pattern pool includes historical frozen runs at different budgets. Its solve
time is NOT a cold-start or equal-budget benchmark. Optimal means within this
finite pool at fixed board count, never all continuous packing geometries.
"""
from collections import Counter, defaultdict, deque
from copy import deepcopy
from dataclasses import replace
import argparse
import hashlib
import faulthandler
import json
from pathlib import Path
import random
import sys
import time
from types import SimpleNamespace

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from scripts.benchmark_alns import command_for, metrics, strict_check
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.optimizer import _run_preordered_method, order_pieces
from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import _valid, largest_remnant_region
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality, final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import optimize_order_plan
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import DomainCuttingEngineAdapter

SETTINGS = dict(min_remnant_width_cm=30., min_remnant_length_cm=30., min_remnant_area_m2=.09)
IDENTITY = ('id', 'label', 'source_piece_no', 'copy_no', 'piece_instance_id')


def run(args):
    faulthandler.enable()
    faulthandler.dump_traceback_later(60,repeat=False)
    from ortools.linear_solver import pywraplp
    begin = time.monotonic()
    original = ROOT/f'docs/evidence/alns-ui/input-{args.case}.json'
    if not original.exists():
        original = ROOT/f'docs/evidence/alns-study/input-{args.case}.json'
    case = json.loads(original.read_text(encoding='utf-8'))
    sources = expand_piece_groups(case['rows'])
    if any(p['piece_type'] not in {'Regular', 'Clipped Corner', 'L-Shaped Corner'}
           or p.get('special_shape_geometry_json') or p.get('extra_liner')
           or p.get('extra_back_groove') or p.get('extra_recessed_handle_cutout') for p in sources):
        raise ValueError('Probe supports only the studied full-board unmachined cohorts')
    w, h, kerf = case['width'], case['height'], .5
    lookup = {p['id']: p for p in sources}
    demand = Counter(p['source_piece_no'] for p in sources)
    groups = sorted(demand)
    pool, seen = [], {}
    inputs = {}
    rejected = Counter()

    def add(sheet, origin):
        if not sheet['pieces']:
            return None
        sheet = deepcopy(sheet)
        for p in sheet['pieces']:
            if p.get('glass_host_piece_id') or p.get('placement_outline_cm'):
                return None
        signature = json.dumps(sorted((p['source_piece_no'], material_outline_cm(p))
                    for p in sheet['pieces']),separators=(',',':'))
        if signature in seen:
            return seen[signature]
        subset = [lookup[p['id']] for p in sheet['pieces']]
        candidate = _valid(dict(sheets=[sheet],unplaced=[]), subset,w,h,kerf,'CNC Router',
                           SETTINGS,time.monotonic()+30,True)
        if candidate is None:
            rejected['invalid_subset'] += 1
            return None
        profile = sheet_cut_line_quality(sheet,kerf)
        if profile is None:
            rejected['unsupported_cutter'] += 1
            return None
        region = largest_remnant_region(candidate,machine_type='CNC Router',metric_kwargs=SETTINGS)
        counts = Counter(p['source_piece_no'] for p in sheet['pieces'])
        index = len(pool)
        pool.append(dict(sheet=sheet,origin=origin,counts=counts,
            remnant=region.area_m2 if region else 0.,length_mm=profile[0],segments=profile[1]))
        seen[signature] = index
        return index

    for arm in ('native','alns','equal_total_native'):
        path=ROOT/f'docs/evidence/alns-ui/final-matrix/{args.case}-{arm}-r0.json'
        inputs[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        recorded=json.loads(path.read_text(encoding='utf-8'))
        if arm == 'alns':
            baseline=recorded['snapshot']
        for plan in [*recorded['seeds'],*recorded['gallery']]:
            for sheet in plan['sheets']:
                add(sheet,'frozen_'+arm)
    initial_count=len(pool)
    print('initial patterns',initial_count,flush=True)
    baseline_indices=[add(sh,'baseline') for sh in baseline['sheets']]
    if args.augment:
        # Partial-board patterns can be useful even when their parent plan
        # could not meet the final board count. They remain genuine subsets.
        originals=list(pool)
        for record in originals:
            sh=record['sheet']
            regular=Counter(p['source_piece_no'] for p in sh['pieces'] if p['piece_type']=='Regular')
            for group,_ in regular.most_common(3):
                partial=deepcopy(sh)
                partial['pieces']=[p for p in sh['pieces'] if p['source_piece_no']!=group]
                add(partial,'remove_one_family')
        regular=[p for p in sources if p['piece_type']=='Regular']
        sequences=[order_pieces(regular,order) for order in ('area_desc','width_desc','length_desc','long_side_desc')]
        families=defaultdict(list)
        for p in regular:
            families[p['source_piece_no']].append(p)
        for seed in range(8):
            grouped=list(families.values())
            random.Random(seed).shuffle(grouped)
            sequences.append([p for family in grouped for p in family])
        for sequence in sequences:
            for method in ('MaxRects Contact Point','MaxRects Best Short Side'):
                plan=_run_preordered_method(sequence,regular,w,h,kerf,method,'pattern_probe')
                for sheet in plan['sheets']:
                    add(sheet,'regular_pool')
        # Legal compact candidate remnant boards from every repeated family.
        for family in families.values():
            for count in sorted({1,min(2,len(family)),min(4,len(family)),len(family)}):
                subset=family[:count]
                plan=_run_preordered_method(subset,subset,w,h,kerf,
                        'MaxRects Best Short Side','family_pattern_probe')
                for sheet in plan['sheets']:
                    add(sheet,'compact_family')
    pool_elapsed=time.monotonic()-begin
    print('built patterns',len(pool),'seconds',pool_elapsed,flush=True)
    Path(args.output+'.pool.json').write_text(json.dumps(dict(patterns=pool,baseline=baseline),indent=2),encoding='utf-8')
    model=pywraplp.Solver.CreateSolver('CBC')
    model.SetTimeLimit(round(args.solve_sec*1000))
    status_names={0:'OPTIMAL',1:'FEASIBLE',2:'INFEASIBLE',3:'UNBOUNDED',4:'ABNORMAL',6:'NOT_SOLVED'}
    variables=[]
    for i,pattern in enumerate(pool):
        limit=min(demand[g]//qty for g,qty in pattern['counts'].items())
        variables.append(model.IntVar(0,limit,f'x{i}'))
    for group in groups:
        model.Add(sum(v*pattern['counts'].get(group,0) for v,pattern in zip(variables,pool))==demand[group])
    model.Add(sum(variables)==len(baseline['sheets']))
    owner=[model.BoolVar(f'owner{i}') for i in range(len(pool))]
    for own,var in zip(owner,variables):
        model.Add(own<=var)
    model.Add(sum(owner)==1)
    remnant=sum(o*round(p['remnant']*1_000_000) for o,p in zip(owner,pool))
    model.Maximize(remnant)
    hints=Counter(baseline_indices)
    owner_hint=max(baseline_indices,key=lambda i:pool[i]['remnant'])
    model.SetHint([*variables,*owner], [*(hints[i] for i in range(len(pool))),
                        *(int(i==owner_hint) for i in range(len(pool)))])
    started=time.monotonic()
    status=model.Solve()
    print('stage1',status_names.get(status,status),flush=True)
    stage1=dict(status=status_names.get(status,status),wall_sec=time.monotonic()-started,
        bound=model.Objective().BestBound() if status in (0,1) else None)
    if status not in (0,1):
        raise RuntimeError('No complete fixed-board-count solution within probe budget')
    best=round(model.Objective().Value())
    selection=[round(v.solution_value()) for v in variables]
    model.Add(remnant>=best)
    # Actual board cutter profiles are additive, while group bounding-box
    # proxies are not. This integer objective is only for pool selection;
    # the existing real final comparator remains the authoritative judge.
    model.Minimize(sum(v*(round(p['length_mm']*1000)*10000+p['segments']) for v,p in zip(variables,pool)))
    model.SetHint(variables,selection)
    started=time.monotonic()
    status2=model.Solve()
    print('stage2',status_names.get(status2,status2),flush=True)
    stage2=dict(status=status_names.get(status2,status2),wall_sec=time.monotonic()-started)
    if status2 in (0,1):
        selection=[round(v.solution_value()) for v in variables]
    remaining=defaultdict(deque)
    for source in sources:
        remaining[source['source_piece_no']].append(source)
    trial=dict(sheets=[],unplaced=[],method_key=baseline['method_key'],
               complexity=baseline['industrial_rank'][-1],method_label='Offline pattern master probe')
    selected=[]
    for index,multiplicity in enumerate(selection):
        for _ in range(multiplicity):
            sh=deepcopy(pool[index]['sheet'])
            sh['sheet_no']=len(trial['sheets'])+1
            for placed in sh['pieces']:
                source=remaining[placed['source_piece_no']].popleft()
                for key in IDENTITY:
                    placed[key]=source[key]
            trial['sheets'].append(sh)
            selected.append(dict(index=index,origin=pool[index]['origin'],remnant=pool[index]['remnant']))
    assert not any(remaining.values())
    checked=_valid(trial,sources,w,h,kerf,'CNC Router',SETTINGS,time.monotonic()+30,True)
    if checked is None:
        raise AssertionError('Complete reconstructed plan failed validation')
    class FrozenEngine(DomainCuttingEngineAdapter):
        def optimize(self,*pos,**kw):
            return dict(deepcopy(checked),smart_candidates=[deepcopy(checked)])
    command=replace(command_for(case,SimpleNamespace(trim_mm=0,kerf_mm=5,machine='CNC Router',
        budget=1,alignment_sec=0)),allow_piece_mirroring=True)
    outcome=optimize_order_plan(command,engine=FrozenEngine())
    final=outcome.snapshot
    if not final['validation']['is_valid'] or not strict_check(final,case['rows']):
        raise AssertionError('Real Application or JS/strict roundtrip failed')
    before,after=final_system_sort_keys([baseline,final])
    result=dict(case=args.case,augment=args.augment,initial_patterns=initial_count,total_patterns=len(pool),
        pool_build_sec=pool_elapsed,stage1=stage1,stage2=stage2,selected=selected,rejected=dict(rejected),
        before=metrics(baseline,kerf),after=metrics(final,kerf),snapshot=final,strict_roundtrip=True,
        comparison='better' if after[:2]<before[:2] else 'worse' if after[:2]>before[:2] else 'equal',
        historical_inputs=inputs,solver_backend=model.SolverVersion(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        warning='Offline upper-potential experiment with historical multi-budget pool, not a cold/equal-budget benchmark or global optimality proof')
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('snapshot','historical_inputs')},indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--augment',action='store_true')
    p.add_argument('--solve-sec',type=float,default=2.)
    p.add_argument('--output',required=True)
    run(p.parse_args())
