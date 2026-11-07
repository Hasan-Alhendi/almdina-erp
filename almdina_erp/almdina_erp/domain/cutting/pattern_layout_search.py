"""Session-local board patterns, remnant-directed pricing and exact coverage.

Native geometry owns placements and validation. The optional integer backend
sees counts and measured profiles only. No cross-order cache or designer poses.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import time

from .cut_line_quality import final_system_sort_keys, sheet_cut_line_quality
from .glass_opening_nesting import material_outline_cm
from .pattern_master import PatternColumn, PatternSelection, valid_selection
from .primitives import create_sheet, orientations_for
from .regular_templates import _unprotected_regular
from .same_count_layout_search import (
    _valid, _cache, _movable_sources, largest_remnant_region, material_signature,
    improve_fixed_board_layout, FixedBoardSearchPolicy,
)
from .strategies.maxrects import (
    place_piece_maxrects, maxrects_score, _candidate_preserves_kerf,
)
from .optimizer import _run_preordered_method, order_pieces

_IDENTITY = ('id','label','source_piece_no','copy_no','piece_instance_id')
_CORNERS = {'L-Shaped Corner','Clipped Corner'}
_SHEET_CONTEXT=('full_width_cm','full_length_cm','applied_trim_width_cm',
                'applied_trim_length_cm','usable_width_cm','usable_length_cm')


def source_families(sources):
    """Only copies with identical source-owned manufacturing data may swap IDs."""
    rows, indices, keys = [], {}, {}
    for source in sources:
        key = json.dumps({k:v for k,v in source.items() if k not in
            {'id','label','copy_no','piece_instance_id'}},sort_keys=True,separators=(',',':'))
        if key not in keys:
            keys[key] = len(rows)
            rows.append([])
        index = keys[key]
        rows[index].append(source)
        indices[source['id']] = index
    return rows, indices


@dataclass
class _Pattern:
    sheet: dict
    column: PatternColumn
    signature: tuple
    origin: str


class PatternPool:
    def __init__(self,sources,width,height,kerf,machine,mirror,metrics,deadline,limit=192,sheet_context=None):
        self.sources=sources
        self.families,self.family_by_id=source_families(sources)
        self.lookup={p['id']:p for p in sources}
        self.demand=tuple(map(len,self.families))
        self.width,self.height,self.kerf=width,height,kerf
        self.machine,self.mirror,self.metrics=machine,mirror,metrics
        self.deadline,self.limit=deadline,min(256,limit)
        self.patterns=[]
        self.seen={}
        self.rejected=Counter()
        self.sheet_context={k:v for k,v in (sheet_context or {}).items() if k in _SHEET_CONTEXT}

    def add(self,sheet,origin,*,validated=False):
        if time.monotonic() >= self.deadline:
            return None
        sheet=dict(sheet,**self.sheet_context)
        if (not sheet.get('pieces') or len(sheet['pieces']) > 64
                or abs(sheet['w']-self.width)>1e-7 or abs(sheet['h']-self.height)>1e-7
                or (sheet.get('resource_kind') or 'FULL_BOARD')!='FULL_BOARD'):
            return None
        rings=[]
        counts=[0]*len(self.families)
        subset=[]
        for placed in sheet['pieces']:
            source=self.lookup.get(placed.get('id'))
            if source is None or placed.get('glass_host_piece_id') or placed.get('placement_outline_cm'):
                return None
            ring=material_outline_cm(placed)
            if ring is None:
                return None
            family=self.family_by_id[source['id']]
            counts[family]+=1
            rings.append((family,tuple(tuple(point) for point in ring)))
            subset.append(source)
        signature=tuple(sorted(rings))
        if signature in self.seen:
            return self.seen[signature]
        # Reuse only an immediate full-parent validation in this same source,
        # geometry and permission context. Never trust snapshot flags.
        checked=(dict(sheets=[deepcopy(sheet)]) if validated else
            _valid(dict(sheets=[deepcopy(sheet)],unplaced=[]),subset,self.width,self.height,
                self.kerf,self.machine,self.metrics,self.deadline,self.mirror))
        if checked is None:
            self.rejected['validation']+=1
            return None
        sheet=checked['sheets'][0]
        profile=sheet_cut_line_quality(sheet,self.kerf)
        if profile is None:
            self.rejected['unsupported_network']+=1
            return None
        region=largest_remnant_region(checked,machine_type=self.machine,metric_kwargs=self.metrics)
        column=PatternColumn(tuple(counts),round((region.area_m2 if region else 0)*10**8),
            round(profile[0]*10**5),round(profile[2]*1000),profile[1])
        quality=lambda c:(c.cutter_units,-c.internal_units,c.segments)
        for index,existing in enumerate(self.patterns):
            if existing.column.counts!=column.counts:
                continue
            # A grid is also a partial owner to be filled later. Complete-board
            # dominance does not prove dominance of its remaining free space.
            if origin=='family_grid':
                continue
            if existing.column.remnant_units>=column.remnant_units and quality(existing.column)<quality(column):
                self.seen[signature]=index
                self.rejected['dominated_pattern']+=1
                return index
            if (existing.origin!='family_grid' and column.remnant_units>=existing.column.remnant_units
                    and quality(column)<quality(existing.column)):
                self.patterns[index]=_Pattern(sheet,column,signature,origin)
                self.seen[signature]=index
                return index
        if len(self.patterns)>=self.limit:
            return None
        index=len(self.patterns)
        self.seen[signature]=index
        self.patterns.append(_Pattern(sheet,column,signature,origin))
        return index

    def reconstruct(self,multiplicities,template):
        selection=PatternSelection(tuple(multiplicities))
        columns=tuple(p.column for p in self.patterns)
        if not valid_selection(columns,self.demand,selection,len(template['sheets'])):
            return None
        available=[deque(family) for family in self.families]
        trial=deepcopy(template)
        trial['sheets']=[]
        trial['unplaced']=[]
        for pattern,qty in zip(self.patterns,multiplicities):
            for _ in range(qty):
                sheet=deepcopy(pattern.sheet)
                sheet['sheet_no']=len(trial['sheets'])+1
                for placed in sheet['pieces']:
                    family=self.family_by_id[placed['id']]
                    source=available[family].popleft()
                    for key in _IDENTITY:
                        placed[key]=source[key]
                _cache(sheet,self.kerf)
                trial['sheets'].append(sheet)
        if any(available):
            return None
        return _valid(trial,self.sources,self.width,self.height,self.kerf,self.machine,
                      self.metrics,self.deadline,self.mirror)


def _supported(plan,sources,machine):
    if (machine not in {'Auto','CNC Router'} or not 0<len(sources)<=256
            or not 0<len(plan.get('sheets') or [])<=32 or plan.get('unplaced')):
        return False
    return (all((s.get('resource_kind') or 'FULL_BOARD')=='FULL_BOARD'
        and len(s['pieces'])<=64
        and all((p.get('resource_kind') or 'FULL_BOARD')=='FULL_BOARD'
            and not any(p.get(k) for k in ('geometry','overlays','placement_outline_cm',
                'special_shape_geometry_json','extra_liner','extra_back_groove','extra_recessed_handle_cutout'))
            for p in s['pieces']) for s in plan['sheets'])
        and all((p.get('resource_kind') or 'FULL_BOARD')=='FULL_BOARD'
            and p.get('piece_type') in {'Regular',*_CORNERS}
            and not any(p.get(key) for key in ('geometry','overlays','special_shape_geometry_json',
                'extra_liner','extra_back_groove','extra_recessed_handle_cutout','extra_double')) for p in sources))


def _family_grids(pool,floor=0.):
    """Real source instances at legal native grid events, both allowed axes."""
    families=[f for f in pool.families if all(_unprotected_regular(p) for p in f)]
    families.sort(key=lambda f:(min(f[0]['width_cm'],f[0]['length_cm']),-len(f),f[0]['id']))
    groups=[]
    for family in families:
        choices=[]
        for orientation in orientations_for(family[0]):
            max_columns=min(len(family),int((pool.width+pool.kerf)/(orientation['w']+pool.kerf)))
            if max_columns<1:
                continue
            for qty in sorted({1,min(2,len(family)),min(4,len(family)),min(6,len(family)),min(64,len(family))},reverse=True):
                columns=min(qty,max_columns)
                rows=math.ceil(qty/columns)
                if rows*orientation['h']+(rows-1)*pool.kerf > pool.height+1e-8:
                    continue
                gw=columns*orientation['w']+(columns-1)*pool.kerf
                gh=rows*orientation['h']+(rows-1)*pool.kerf
                estimate=max((pool.width-gw)*pool.height,pool.width*(pool.height-gh))/10000
                choices.append((estimate,qty,columns,orientation))
        # A pass across every family before revisiting the smallest family.
        # Otherwise moderate achievable remnants never reach the pricer.
        choices.sort(key=lambda item:(item[0]<=floor,item[0] if item[0]>floor else -item[0],-item[1]))
        groups.append((family,choices))
    emitted=0
    for rank in range(4):
        for family,choices in groups:
            if rank>=len(choices):
                continue
            if time.monotonic()>=pool.deadline or emitted>=min(96,max(32,2*len(families))):
                return
            _,qty,columns,orientation=choices[rank]
            sheet=create_sheet(1,pool.width,pool.height)
            for i,source in enumerate(family[:qty]):
                spot=dict(x=(i%columns)*(orientation['w']+pool.kerf),
                    y=(i//columns)*(orientation['h']+pool.kerf),**orientation)
                place_piece_maxrects(sheet,source,spot,pool.kerf)
            index=pool.add(sheet,'family_grid')
            if index is not None:
                emitted+=1
                yield index


def _native_owner_plan(owner,template,pool,ordering,method,deadline):
    """Fill an owner strip, then repack the residual order natively, even >64.

    A private failed full plan can still supply independently validated dense
    board patterns. It cannot increase the final incumbent's board count.
    """
    sheet=deepcopy(owner.sheet)
    region=largest_remnant_region(dict(sheets=[sheet]),machine_type=pool.machine,metric_kwargs=pool.metrics)
    if region is None:
        return None
    _cache(sheet,pool.kerf,region.rectangle())
    used={p['id'] for p in sheet['pieces']}
    for piece in sorted((p for p in pool.sources if p['id'] not in used),key=lambda p:(p['area_m2'],p['id'])):
        if time.monotonic()>=deadline:
            return None
        if len(sheet['pieces'])>=64:
            break
        positions=_positions(sheet,piece,pool.kerf,'best_short_side',deadline)
        if positions:
            place_piece_maxrects(sheet,piece,positions[0],pool.kerf)
            used.add(piece['id'])
    remaining=[p for p in pool.sources if p['id'] not in used]
    if not remaining:
        packed=[]
    else:
        plan=_run_preordered_method(order_pieces(remaining,ordering),remaining,
            pool.width,pool.height,pool.kerf,method,ordering)
        if (plan.get('unplaced') or len(plan['sheets'])>len(template['sheets'])
                or any(len(s['pieces'])>64 for s in plan['sheets'])):
            return None
        packed=plan['sheets']
    trial=deepcopy(template)
    trial['sheets']=[sheet,*packed]
    for i,board in enumerate(trial['sheets']):
        board['sheet_no']=i+1
        board.update(pool.sheet_context)
    trial['unplaced']=[]
    return _valid(trial,pool.sources,pool.width,pool.height,pool.kerf,pool.machine,
                  pool.metrics,pool.deadline,pool.mirror)


def _reserve_skeleton(seed,owner,pool):
    movable={p['id'] for p in _movable_sources(seed,pool.sources,pool.kerf)}
    skeleton=deepcopy(seed)
    for sheet in skeleton['sheets']:
        sheet['pieces']=[p for p in sheet['pieces'] if p['id'] not in movable]
    empty=[i for i,s in enumerate(skeleton['sheets']) if not s['pieces']]
    if not empty:
        return None
    index=empty[-1]
    fixed={p['id'] for s in skeleton['sheets'] for p in s['pieces']}
    available=[deque(p for p in f if p['id'] not in fixed) for f in pool.families]
    pieces=deepcopy(owner.sheet['pieces'])
    for placed in pieces:
        family=pool.family_by_id[placed['id']]
        if not available[family]:
            return None
        source=available[family].popleft()
        for key in _IDENTITY:
            placed[key]=source[key]
    skeleton['sheets'][index]['pieces']=pieces
    region=largest_remnant_region(dict(sheets=[skeleton['sheets'][index]]),
        machine_type=pool.machine,metric_kwargs=pool.metrics)
    if region is None:
        return None
    for i,sheet in enumerate(skeleton['sheets']):
        _cache(sheet,pool.kerf,region.rectangle() if i==index else None)
    used={p['id'] for s in skeleton['sheets'] for p in s['pieces']}
    remaining=[p for p in pool.sources if p['id'] not in used]
    return skeleton,remaining


def _positions(sheet,source,kerf,heuristic,deadline):
    options=[]
    for free in sheet['free_rects']:
        if time.monotonic()>=deadline:
            break
        for orientation in orientations_for(source):
            if orientation['w']>free['w']+1e-8 or orientation['h']>free['h']+1e-8:
                continue
            candidate=dict(x=free['x'],y=free['y'],**orientation)
            if _candidate_preserves_kerf(sheet,candidate,kerf):
                candidate['score']=maxrects_score(sheet,free,orientation,heuristic,kerf)
                options.append(candidate)
    options.sort(key=lambda p:(p['score'],p['y'],p['x'],p['rotated']))
    unique=[]
    seen=set()
    for spot in options:
        key=tuple(spot[k] for k in ('x','y','w','h'))
        if key not in seen:
            seen.add(key)
            unique.append(spot)
        if len(unique)==2:
            break
    return unique


def _beam_repair(skeleton,remaining,pool,deadline,*,order,urgent=()):
    """Three legal states, bounded native placements; partial boards survive."""
    priority={g:i for i,g in enumerate(urgent)}
    pending=sorted(remaining,key=lambda p:(priority.get(pool.family_by_id[p['id']],len(priority)),
        (-min(p['width_cm'],p['length_cm']),-max(p['width_cm'],p['length_cm']),p['id'])
        if order==0 else (-p['area_m2'],-max(p['width_cm'],p['length_cm']),p['id'])))
    states=[(0.,skeleton)]
    probes=0
    for position,source in enumerate(pending):
        if time.monotonic()>=deadline or probes>=6000:
            return states[0][1],pending[position:],probes
        branches=[]
        for score,state in states:
            options=[]
            for index,sheet in enumerate(state['sheets']):
                for spot in _positions(sheet,source,pool.kerf,
                        'best_short_side' if order==0 else 'contact_point',deadline):
                    probes+=1
                    options.append((spot['score'],index,spot))
            options.sort(key=lambda v:(not bool(state['sheets'][v[1]]['pieces']),v[0],v[1]))
            for cost,index,spot in options[:3]:
                trial=dict(state,sheets=list(state['sheets']))
                trial['sheets'][index]=deepcopy(state['sheets'][index])
                place_piece_maxrects(trial['sheets'][index],source,spot,pool.kerf)
                branches.append((score+cost,trial))
        if not branches:
            return states[0][1],pending[position:],probes
        branches.sort(key=lambda item:(sum(bool(s['pieces']) for s in item[1]['sheets']),item[0]))
        states=branches[:3]
    return states[0][1],[],probes


def refine_pattern_layout(incumbent,seeds,sources,width,height,kerf,*,deadline,
                          machine_type,mirroring_allowed,metric_kwargs,solver=None,formation_seeds=(),row_solver=None):
    started=time.monotonic()
    trace=dict(stop='completed',patterns=0,seed_plans=0,pricing_attempts=0,
        pricing_completed=0,placement_probes=0,master_status='not_run',master_phases=[],improvements=0)
    if (not all(math.isfinite(v) for v in (width,height,kerf)) or min(width,height)<=0 or kerf<0
            or not _supported(incumbent,sources,machine_type) or time.monotonic()>=deadline):
        trace['stop']='unsupported_or_expired'
        return [deepcopy(incumbent)],trace
    if len(source_families(sources)[0])>64:
        trace['stop']='too_many_distinct_families'
        return [deepcopy(incumbent)],trace
    best=_valid(deepcopy(incumbent),sources,width,height,kerf,machine_type,metric_kwargs,
                deadline,mirroring_allowed)
    if best is None:
        trace['stop']='invalid_incumbent'
        return [deepcopy(incumbent)],trace
    pool=PatternPool(sources,width,height,kerf,machine_type,mirroring_allowed,metric_kwargs,deadline,
                     sheet_context=incumbent['sheets'][0])
    candidates=[deepcopy(incumbent)]
    offered={material_signature(incumbent)}

    def offer(trial,*,validated=False):
        nonlocal best
        if (trial is None or len(trial.get('sheets') or [])>len(best['sheets'])
                or any(len(s['pieces'])>64 for s in trial['sheets'])):
            return
        checked=(trial if validated else
            _valid(trial,sources,width,height,kerf,machine_type,metric_kwargs,deadline,mirroring_allowed))
        if checked is None:
            return
        signature=material_signature(checked)
        if signature in offered:
            return
        before,after=final_system_sort_keys([best,checked])
        if after<before:
            offered.add(signature)
            best=checked
            candidates.append(checked)
            trace['improvements']+=1

    parents=[]
    parent_signatures=set()
    for seed in [incumbent,*seeds[:5]]:
        if time.monotonic()>=deadline or len(parents)>=5:
            break
        signature=material_signature(seed)
        if signature in parent_signatures:
            continue
        checked=(deepcopy(best) if seed is incumbent else
            _valid(deepcopy(seed),sources,width,height,kerf,machine_type,metric_kwargs,deadline,mirroring_allowed))
        if checked is None or len(checked['sheets'])>len(best['sheets']):
            continue
        parent_signatures.add(signature)
        parents.append(checked)
        for sheet in checked['sheets']:
            pool.add(sheet,'seed',validated=True)
    trace['seed_plans']=len(parents)
    trace['seed_elapsed_sec']=round(time.monotonic()-started,3)
    if formation_seeds:
        for skeleton in formation_seeds[:4]:
            if time.monotonic()>=deadline:
                break
            used={p['id'] for s in skeleton['sheets'] for p in s['pieces']}
            subset=[p for p in sources if p['id'] in used]
            checked=_valid(skeleton,subset,width,height,kerf,machine_type,metric_kwargs,
                           deadline,mirroring_allowed)
            if checked is not None:
                parents.append(checked)
                for sheet in checked['sheets']:
                    pool.add(sheet,'shape_formation',validated=True)
    trace['shape_skeletons']=max(0,len(parents)-trace['seed_plans'])
    trace['row_pricing']=[]
    if row_solver is not None and parents:
        from .shelf_layout_pricing import price_shelf_layout
        unique_frames={}
        for parent in parents:
            moving={p['id'] for p in _movable_sources(parent,sources,kerf)}
            fixed=[(i,p) for i,s in enumerate(parent['sheets']) for p in s['pieces'] if p['id'] not in moving]
            key=tuple((i,pool.family_by_id[p['id']],tuple(material_outline_cm(p))) for i,p in fixed)
            if key not in unique_frames:
                unique_frames[key]=(len({i for i,_ in fixed}),parent)
        frames=[p for _,p in sorted(unique_frames.values(),key=lambda v:v[0])[:2]]
        regular_only=all(p['piece_type']=='Regular' for p in sources)
        row_end=started+(deadline-started)*(.45 if regular_only else .67)
        jobs=[(frame,transpose) for transpose in (False,True) for frame in frames]
        for index,(frame,transpose) in enumerate(jobs):
            if time.monotonic()>=row_end:
                break
            local=min(row_end,time.monotonic()+max(.2,(row_end-time.monotonic())/(len(jobs)-index)))
            try:
                trial,row_trace=price_shelf_layout(frame,best,sources,width,height,kerf,
                    deadline=local,solver=row_solver,
                    min_remnant_m2=(0. if index==len(jobs)-1 else
                        best['industrial_metrics']['largest_reusable_free_area_m2']),transpose=transpose)
                trace['row_pricing'].append(row_trace)
                if trial is not None:
                    for sheet in trial['sheets']:
                        pool.add(sheet,'global_rows')
                    offer(trial)
            except Exception as error:
                trace['row_pricing'].append(dict(status='solver_error:'+type(error).__name__))
    initial_end=min(deadline,time.monotonic()+(deadline-started)*.15)
    owners=[]
    material=0.
    for sheet in incumbent['sheets']:
        for p in sheet['pieces']:
            ring=material_outline_cm(p)
            material+=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1])))/2
    owner_minimum=max(0.,material-(len(incumbent['sheets'])-1)*width*height)
    for index in _family_grids(pool,best['industrial_metrics']['largest_reusable_free_area_m2']):
        pattern=pool.patterns[index]
        if (pattern.column.remnant_units>round(best['industrial_metrics']['largest_reusable_free_area_m2']*10**8)
                and sum(p['w']*p['h'] for p in pattern.sheet['pieces'])+1e-6>=owner_minimum):
            owners.append(index)
        if time.monotonic()>=initial_end:
            break
    by_area={}
    for i in sorted(set(owners),key=lambda i:-sum(p['w']*p['h'] for p in pool.patterns[i].sheet['pieces'])):
        by_area.setdefault(pool.patterns[i].column.remnant_units,i)
    ordered=[by_area[area] for area in sorted(by_area)]
    owners=([ordered[round(i*(len(ordered)-1)/(min(16,len(ordered))-1))] for i in range(min(16,len(ordered)))]
            if len(ordered)>1 else ordered)
    pricing_end=started+(deadline-started)*.78
    trace['native_pricing_attempts']=0
    trace['native_owners']=[]
    if all(p['piece_type']=='Regular' for p in sources):
        variants=(('area_desc','MaxRects Contact Point'),('long_side_desc','MaxRects Best Short Side'),
            ('width_desc','MaxRects Contact Point'),('length_desc','MaxRects Best Short Side'),
            ('area_desc','MaxRects Best Short Side'),('long_side_desc','MaxRects Contact Point'))
        jobs=((i,order,method) for order,method in variants for i in owners)
        owner_statistics={}
        for owner_index,ordering,method in jobs:
            if time.monotonic()>=pricing_end:
                break
            if owner_index not in owner_statistics:
                owner_statistics[owner_index]=dict(target_m2=pool.patterns[owner_index].column.remnant_units/10**8,
                    attempts=0,fewest_generated_boards=None)
                trace['native_owners'].append(owner_statistics[owner_index])
            owner_trace=owner_statistics[owner_index]
            trace['native_pricing_attempts']+=1
            owner_trace['attempts']+=1
            trial=_native_owner_plan(pool.patterns[owner_index],best,pool,ordering,method,pricing_end)
            if trial is not None:
                owner_trace['fewest_generated_boards']=min(owner_trace['fewest_generated_boards'] or 99,len(trial['sheets']))
                if len(trial['sheets'])<=len(best['sheets']):
                    subset=trial['sheets']
                else:
                    donors=trial['sheets'][1:]
                    dense=sorted(donors,key=lambda s:-sum(p['area_m2'] for p in s['pieces']))[:2]
                    coverage=[sum(p.column.counts[g]>0 for p in pool.patterns) for g in range(len(pool.demand))]
                    def scarcity(sheet):
                        counts=Counter(pool.family_by_id[p['id']] for p in sheet['pieces'])
                        return sum(q/pool.demand[g]/max(1,coverage[g]) for g,q in counts.items())
                    rare=max(donors,key=scarcity) if donors else None
                    subset=[trial['sheets'][0],*dense]
                    if rare is not None and all(rare is not s for s in dense):
                        subset.append(rare)
                for sheet in subset:
                    pool.add(sheet,'native_owner',validated=True)
                offer(trial,validated=True)
    urgent=()
    # Repaired board subsets are useful even when that full attempt fails.
    for attempt in range(min(8,len(owners)*2)):
        if time.monotonic()>=pricing_end or not parents:
            break
        owner=pool.patterns[owners[attempt//2]]
        # Alternate a complete incumbent skeleton with a new legal formation.
        parent=(parents[trace['seed_plans']+(attempt//2)%trace['shape_skeletons']]
            if attempt%2 and trace['shape_skeletons'] else parents[(attempt//2)%max(1,trace['seed_plans'])])
        proposal=_reserve_skeleton(parent,owner,pool)
        if proposal is None:
            continue
        trace['pricing_attempts']+=1
        local_deadline=min(pricing_end,time.monotonic()+max(.15,(pricing_end-time.monotonic())/max(1,4-attempt)))
        if attempt%2==0:
            from .system_layout_refinement import _grid_presets
            skeleton,remaining=proposal
            ids={p['id'] for p in remaining}
            grid=next(_grid_presets(skeleton,sources,ids,width,height,kerf,local_deadline),None)
            if grid is not None:
                skeleton,ids,_=grid
                proposal=skeleton,[p for p in remaining if p['id'] in ids]
        trial,left,probes=_beam_repair(*proposal,pool,local_deadline,order=attempt%2,
                                     urgent=urgent if attempt%2 else ())
        trace['placement_probes']+=probes
        urgent=tuple(dict.fromkeys(pool.family_by_id[p['id']] for p in left))
        for sheet in trial['sheets']:
            pool.add(sheet,'remnant_repair')
        if not left:
            trace['pricing_completed']+=1
            trial['sheets']=[s for s in trial['sheets'] if s['pieces']]
            offer(trial)
    # Preserve a few useful sub-patterns; the master can fill their family
    # deficits from another parent without carrying that parent's bad boards.
    for pattern in list(pool.patterns)[:12]:
        if time.monotonic()>=pricing_end:
            break
        regular=Counter(pool.family_by_id[p['id']] for p in pattern.sheet['pieces'] if _unprotected_regular(p))
        for family,_ in regular.most_common(1):
            sheet=deepcopy(pattern.sheet)
            sheet['pieces']=[p for p in sheet['pieces'] if pool.family_by_id[p['id']]!=family]
            pool.add(sheet,'family_deficit')
    if solver is not None and pool.patterns and time.monotonic()<deadline:
        columns=tuple(p.column for p in pool.patterns)
        hint=[0]*len(columns)
        for sheet in parents[0]['sheets'] if parents else []:
            index=pool.add(sheet,'seed')
            if index is not None:
                hint[index]+=1
        try:
            answer=solver(columns,pool.demand,len(best['sheets']),deadline=deadline,hint=tuple(hint))
            trace['master_status']=answer.status
            trace['master_phases']=list(answer.phases)
            if valid_selection(columns,pool.demand,answer,len(best['sheets'])):
                offer(pool.reconstruct(answer.multiplicities,best),validated=True)
            else:
                trace['master_status']='invalid_or_empty_selection'
        except Exception as error:
            trace['master_status']='solver_error:'+type(error).__name__
    if time.monotonic()<deadline-.1:
        # A newly concentrated plan creates fresh local opportunities. Reuse
        # the proven ALNS geometry gates at its new remnant floor, within this
        # same deadline; do not stop after selecting a row allocation.
        trace['tail_remnant_floor_m2']=best['industrial_metrics']['largest_reusable_free_area_m2']
        tail,tail_trace=improve_fixed_board_layout(best,sources,width,height,kerf,
            deadline=deadline-.08,machine_type=machine_type,mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs,policy=FixedBoardSearchPolicy(
                operators=('grid','relocate','repack','owner_repack'),max_attempts=128,
                pinned_shapes=True,allow_fewer_boards=True))
        for proposal in tail[1:]:
            offer(proposal,validated=True)
        trace['tail']=dict(attempts=tail_trace.get('attempts',0),stop=tail_trace.get('stop'),
                          operators=tail_trace.get('operators',{}))
    trace.update(patterns=len(pool.patterns),rejections=dict(pool.rejected),elapsed_sec=round(time.monotonic()-started,3),
        stop='deadline' if time.monotonic()>=deadline else 'completed')
    keys=final_system_sort_keys(candidates)
    ranked=[p for _,p in sorted(zip(keys,candidates),key=lambda item:item[0])]
    original=material_signature(incumbent)
    return [deepcopy(incumbent),*[p for p in ranked if material_signature(p)!=original][:4]],trace
