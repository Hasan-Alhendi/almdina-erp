"""Coupled legal corner frames and coherent guest rows inside real voids."""
from collections import defaultdict
from copy import deepcopy
import math
import time

from . import shape_aware_nesting as shape
from .glass_opening_nesting import material_outline_cm
from .primitives import make_placed_piece


def _row_spots(void, width, height, hosts, kerf):
    """Centre the entire row; offset-edge contacts handle asymmetric diamonds."""
    left, top = void['x'], void['y']
    right, bottom = left+void['w']-width, top+void['h']-height
    if right < left-1e-8 or bottom < top-1e-8:
        return
    middle_x,middle_y=(left+right)/2,(top+bottom)/2
    centre=(void['x']+void['w']/2,void['y']+void['h']/2)
    constraints=[(1.,0.,left),(-1.,0.,-right),(0.,1.,top),(0.,-1.,-bottom)]
    for host in hosts:
        outline=material_outline_cm(host)
        xs,ys=zip(*outline)
        for a,b in zip(outline,outline[1:]+outline[:1]):
            nx,ny=b[1]-a[1],a[0]-b[0]
            # Only the notch boundary bounds the central empty region.
            internal=(abs(nx)>1e-8 and abs(ny)>1e-8 or
                abs(nx)<1e-8 and min(ys)+1e-8<a[1]<max(ys)-1e-8 or
                abs(ny)<1e-8 and min(xs)+1e-8<a[0]<max(xs)-1e-8)
            if not internal:continue
            c=nx*a[0]+ny*a[1]
            if nx*centre[0]+ny*centre[1]<c:
                nx,ny,c=-nx,-ny,-c
            c+=(kerf+1e-6)*math.hypot(nx,ny)-min(0.,nx*width)-min(0.,ny*height)
            constraints.append((nx,ny,c))
    def legal(x,y):
        return all(a*x+b*y>=c-1e-7 for a,b,c in constraints)
    contact_first=all(p['piece_type']=='L-Shaped Corner' for p in hosts)
    if not contact_first and legal(middle_x,middle_y):
        yield middle_x,middle_y
    vertices=[]
    for i,(a,b,c) in enumerate(constraints):
        for d,e,f in constraints[i+1:]:
            det=a*e-b*d
            if abs(det)<1e-9:continue
            x,y=(c*e-b*f)/det,(a*f-c*d)/det
            if legal(x,y):vertices.append((x,y))
    if vertices:
        # The centroid of a convex feasible polygon remains feasible, even
        # when unequal notch depths shift the opening away from its bbox centre.
        contacts=sorted(set(vertices),key=lambda p:((p[0]-middle_x)**2+(p[1]-middle_y)**2,p))[:4]
        if contact_first:yield from contacts
        yield sum(x for x,_ in vertices)/len(vertices),sum(y for _,y in vertices)/len(vertices)
        if not contact_first:yield from contacts


def guest_row_blocks(block, sources, kerf, width, height, *, deadline, limit=6):
    """Nominate whole rows/grids, retaining each original piece's dimensions."""
    from .pattern_layout_search import source_families
    from .shelf_layout_pricing import row_patterns
    hosts=block['pieces']
    used={p['id'] for p in hosts}
    candidates=[p for p in sources if p['piece_type']=='Regular' and p['id'] not in used]
    families,_=source_families(candidates)
    proposals=[]
    signatures=set()
    for void in block.get('voids') or []:
        if time.monotonic()>=deadline:
            break
        rows=row_patterns(families,void['w'],void['h'],kerf,False,deadline,limit=512)
        def repetitions(row):
            return min(4,int((void['h']+kerf)/(row['height']+kerf)),
                *(len(families[g])//q for g,q in enumerate(row['column'].counts) if q))
        # Rank the entire repeated bundle. Ranking one row first starves a
        # three-row nest behind larger single-row rectangles.
        rows.sort(key=lambda r:-repetitions(r)*sum(q*o['w']*o['h'] for _,o,q in r['members']))
        for row in rows:
            if time.monotonic()>=deadline:
                break
            counts=row['column'].counts
            repeat=repetitions(row)
            for n in sorted({1,repeat},reverse=True):
                if n<=0:
                    continue
                h=n*(row['height']+kerf)-kerf
                for x,y in _row_spots(void,row['used_width'],h,hosts,kerf):
                    if time.monotonic()>=deadline:
                        break
                    guests=[]
                    next_copy=defaultdict(int)
                    good=True
                    for line in range(n):
                        across=0.
                        for group,orientation,qty in row['members']:
                            for _ in range(qty):
                                source=families[group][next_copy[group]]
                                next_copy[group]+=1
                                placed=make_placed_piece(source,x+across,y+line*(row['height']+kerf),
                                    orientation['w'],orientation['h'],orientation['rotated'])
                                outline=material_outline_cm(placed)
                                if (not shape._inside_board(outline,width,height)
                                        or not shape._clears(outline,[*hosts,*guests],kerf)):
                                    good=False
                                    break
                                guests.append(placed)
                                across+=orientation['w']+kerf
                            if not good:break
                        if not good:break
                    if good:
                        key=tuple((p['id'],round(p['x'],6),round(p['y'],6),p['rotated']) for p in guests)
                        if key not in signatures:
                            signatures.add(key)
                            proposals.append(dict(block,pieces=[*deepcopy(hosts),*guests],guests=guests))
                        break
            if len(proposals)>=32:
                break
    proposals.sort(key=lambda b:(-sum(p['w']*p['h'] for p in b['guests']),-len(b['guests'])))
    return proposals[:limit]


def corner_frames(template, sources, width, height, kerf, *, deadline, mirroring_allowed, limit=12):
    """Fresh mixed-notch partitions, whole guest rows, then rigid seating."""
    from .system_layout_refinement import _body_rotations
    from .nesting_consolidation import best_rigid_translation
    from .same_count_layout_search import _cache, material_signature
    corners=[p for p in sources if p['piece_type'] in shape._CORNER_TYPES]
    if not 4<=len(corners)<=16:
        return
    buckets=defaultdict(list)
    for p in corners:
        buckets[p['piece_type'],p['width_cm'],p['length_cm']].append(p)
    partitions=[]
    for variant in range(3):
        blocks=[]
        for bucket in buckets.values():
            pending=sorted(bucket,key=lambda p:(-p['clipped_corner_width_cm'],-p['clipped_corner_length_cm'],p['id']))
            if variant==1:
                pending=pending[::2]+pending[1::2]
            elif variant==2:
                pending=list(reversed(pending))
            while len(pending)>=4:
                if time.monotonic()>=deadline:return
                quad=shape._take_quad(pending,width,height,kerf,mirroring_allowed=mirroring_allowed)
                if quad is None:break
                blocks.append(quad['block'])
                pending=[p for p in pending if p['id'] not in quad['ids']]
            blocks.extend(shape._partition_group(pending,width,height,kerf,mirroring_allowed=mirroring_allowed))
        if blocks:partitions.append(blocks)
    emitted=set()
    count=0
    # Breadth across partitions before deeper guest alternatives.
    choices=(1,0,2,3) if all(p['piece_type']=='L-Shaped Corner' for p in corners) else (0,1,2,3)
    for choice in choices:
        for blocks in partitions:
            if time.monotonic()>=deadline:return
            seated=[]
            used={p['id'] for b in blocks for p in b['pieces']}
            for block in blocks:
                available=[p for p in sources if p['id'] not in used or p['id'] in {v['id'] for v in block['pieces']}]
                if choice==0:
                    chosen=shape._seat_void_guests([block],available,kerf,width,height,
                        mirroring_allowed=mirroring_allowed,hosted=set(),quarter_turns_only=True,
                        contact_anchors=True,area_first=True,deadline=min(deadline,time.monotonic()+.15))[0]
                else:
                    options=guest_row_blocks(block,available,kerf,width,height,
                        deadline=min(deadline,time.monotonic()+.35),limit=3)
                    chosen=options[min(choice-1,len(options)-1)] if options else deepcopy(block)
                seated.append(chosen)
                used.update(p['id'] for p in chosen.get('guests') or [])
            for spread in (False,True):
                frame=deepcopy(template)
                for sheet in frame['sheets']:sheet['pieces']=[]
                complete=True
                for block in seated:
                    found=False
                    for sheet in sorted(frame['sheets'],key=lambda s:bool(s['pieces'])) if spread else frame['sheets']:
                        for body in _body_rotations(block['pieces'],sources):
                            if time.monotonic()>=deadline:return
                            pos=best_rigid_translation(sheet,body,kerf,width,height,
                                constraint='pair' if block['kind']=='pair' else '',deadline=deadline)
                            if pos is not None:
                                sheet['pieces'].extend(shape._translate_pieces(body,*pos[:2]))
                                found=True
                                break
                        if found:break
                    if not found:
                        complete=False
                        break
                if not complete:continue
                actual={p['id'] for s in frame['sheets'] for p in s['pieces']}
                if not {p['id'] for p in corners}<=actual:continue
                for sheet in frame['sheets']:_cache(sheet,kerf)
                signature=material_signature(frame)
                if signature in emitted:continue
                emitted.add(signature)
                count+=1
                yield frame
                if count>=limit:return


def _contact_repair(trial,sources,ids,receivers,kerf,deadline,*,fixed_axes=False):
    """Try all free-cell corners; original stock edges are not shared cutters."""
    from .primitives import orientations_for
    from .strategies.maxrects import contact_point_score,_candidate_preserves_kerf,place_piece_maxrects
    pending=sorted((p for p in sources if p['id'] in ids),key=lambda p:-p['area_m2'])
    for source in pending:
        options=[]
        for priority,board in enumerate(receivers):
            sheet=trial['sheets'][board]
            for free in sheet['free_rects']:
                if time.monotonic()>=deadline:return False
                for orientation in orientations_for(source):
                    if fixed_axes and orientation['rotated']:continue
                    w,h=orientation['w'],orientation['h']
                    if w>free['w']+1e-8 or h>free['h']+1e-8:continue
                    for x in (free['x'],free['x']+free['w']-w,free['x']+free['w']-w-kerf):
                        for y in (free['y'],free['y']+free['h']-h,free['y']+free['h']-h-kerf):
                            if x<free['x']-1e-8 or y<free['y']-1e-8:continue
                            spot=dict(x=x,y=y,**orientation)
                            if not _candidate_preserves_kerf(sheet,spot,kerf):continue
                            shared=contact_point_score(sheet,x,y,w,h,kerf)
                            if abs(x)<1e-7 or abs(x+w-sheet['w'])<1e-7:shared-=h
                            if abs(y)<1e-7 or abs(y+h-sheet['h'])<1e-7:shared-=w
                            options.append(((priority,-round(shared,6),y,x,orientation['rotated']),board,spot))
        if not options:return False
        _,board,spot=min(options,key=lambda v:v[0])
        place_piece_maxrects(trial['sheets'][board],source,spot,kerf)
    return True


def local_guest_exchanges(plan,sources,width,height,kerf,*,deadline,machine_type,metric_kwargs):
    """Exchange a whole guest bundle while preserving the surrounding layout."""
    from .nesting_consolidation import extract_placement_groups
    from .same_count_layout_search import _movable_sources,_cache,_repair,largest_remnant_region,material_signature
    movable={p['id'] for p in _movable_sources(plan,sources,kerf)}
    region=largest_remnant_region(plan,machine_type=machine_type,metric_kwargs=metric_kwargs)
    seen=set()
    for group in extract_placement_groups(plan):
        hosts=[p for p in group.pieces if p['piece_type'] in shape._CORNER_TYPES]
        if len(hosts)!=4:continue
        board=next((i for i,s in enumerate(plan['sheets']) if s.get('sheet_no')==group.sheet_no),None)
        if board is None:continue
        old_guests={p['id'] for p in group.pieces if p['piece_type']=='Regular'}
        allowed=[p for p in sources if p['id'] in movable|old_guests]
        block=shape._make_block(hosts,'quad',kerf)
        x,y=min(p['x'] for p in hosts),min(p['y'] for p in hosts)
        options=guest_row_blocks(block,allowed,kerf,width,height,deadline=deadline,limit=4)
        for option in options:
            if time.monotonic()>=deadline:return
            incoming={p['id'] for p in option['guests']}
            owner_parts=([p for p in plan['sheets'][region.sheet_index]['pieces']
                          if p['id'] in movable and p['id'] not in incoming] if region is not None else [])
            owners=[set(),*[{p['id']} for p in sorted(owner_parts,key=lambda p:-p['w']*p['h'])[:2]]]
            for owner_ids in owners:
                template=deepcopy(plan)
                for i,sheet in enumerate(template['sheets']):
                    sheet['pieces']=[p for p in sheet['pieces'] if p['id'] not in incoming|old_guests|owner_ids]
                    if i==board:
                        sheet['pieces'].extend(shape._translate_pieces(option['guests'],x,y))
                    _cache(sheet,kerf,region.rectangle() if region is not None and i==region.sheet_index else None)
                remaining=(old_guests|owner_ids)-incoming
                for fixed_axes in (True,False):
                    if time.monotonic()>=deadline:return
                    trial=deepcopy(template)
                    receivers=tuple([board,*[i for i in range(len(trial['sheets'])) if i!=board]])
                    if not _contact_repair(trial,sources,remaining,receivers,kerf,deadline,fixed_axes=fixed_axes):continue
                    trial['sheets']=[s for s in trial['sheets'] if s['pieces']]
                    for sheet in trial['sheets']:_cache(sheet,kerf)
                    signature=material_signature(trial)
                    if signature not in seen:
                        seen.add(signature)
                        yield trial


def refine_corner_layout(incumbent,seeds,sources,width,height,kerf,*,deadline,
                         machine_type,mirroring_allowed,metric_kwargs,solver=None,
                         formation_seeds=(),row_solver=None):
    """Complete fresh coupled frames without consuming previous-stage time."""
    from .pattern_layout_search import _supported,PatternPool,source_families
    from .same_count_layout_search import _valid,material_signature,improve_fixed_board_layout,FixedBoardSearchPolicy
    from .shelf_layout_pricing import price_shelf_layout
    from .cut_line_quality import final_system_sort_keys
    started=time.monotonic()
    trace=dict(stop='completed',frames=0,row_pricing=[],improvements=0)
    if (not _supported(incumbent,sources,machine_type) or row_solver is None
            or len(incumbent.get('industrial_rank') or ())!=8
            or incumbent.get('machine_type') not in {'Auto','CNC Router'}
            or incumbent.get('kerf_cm')!=kerf
            or not 4<=sum(p['piece_type'] in shape._CORNER_TYPES for p in sources)<=16
            or time.monotonic()>=deadline):
        return [deepcopy(incumbent)],dict(trace,stop='unsupported_or_expired')
    best=_valid(deepcopy(incumbent),sources,width,height,kerf,machine_type,metric_kwargs,deadline,mirroring_allowed)
    if best is None:
        return [deepcopy(incumbent)],dict(trace,stop='invalid_incumbent')
    candidates=[deepcopy(incumbent)]
    seen={material_signature(incumbent)}
    keys={}
    def quality(p):
        signature=material_signature(p)
        if signature not in keys:
            keys[signature]=final_system_sort_keys([p])[0]
        return keys[signature]
    def offer(trial):
        nonlocal best
        if trial is None or len(trial.get('sheets') or [])>len(incumbent['sheets']):return
        checked=_valid(trial,sources,width,height,kerf,machine_type,metric_kwargs,deadline,mirroring_allowed)
        if checked is None or material_signature(checked) in seen:return
        before,after=quality(incumbent),quality(checked)
        if after<before:
            seen.add(material_signature(checked))
            candidates.append(checked)
            trace['improvements']+=1
            a,b=quality(best),quality(checked)
            if b<a:best=checked
    local_end=started+(deadline-started)*.20
    for trial in local_guest_exchanges(best,sources,width,height,kerf,deadline=local_end,
            machine_type=machine_type,metric_kwargs=metric_kwargs):
        offer(trial)
    trace['local_improvements']=trace['improvements']
    frame_end=started+(deadline-started)*.32
    frames=[]
    for frame in corner_frames(incumbent,sources,width,height,kerf,
            deadline=frame_end,mirroring_allowed=mirroring_allowed,limit=8):
        subset_ids={p['id'] for s in frame['sheets'] for p in s['pieces']}
        checked=_valid(frame,[p for p in sources if p['id'] in subset_ids],width,height,kerf,
            machine_type,metric_kwargs,deadline,mirroring_allowed)
        if checked is not None:frames.append(checked)
    trace['frames']=len(frames)
    trace['frame_elapsed_sec']=round(time.monotonic()-started,3)
    # A complete shelf cover may fail even when useful individual boards were
    # built. Retain their exact counts for cross-parent pattern allocation.
    pool=PatternPool(sources,width,height,kerf,machine_type,mirroring_allowed,
        metric_kwargs,deadline,sheet_context=incumbent['sheets'][0])
    for sheet in best['sheets']:pool.add(sheet,'incumbent',validated=True)
    from .system_layout_refinement import _place_family_grid
    from .same_count_layout_search import _cache,_repair
    grid_end=started+(deadline-started)*.56
    corner_grid_end=started+(deadline-started)*.38
    for frame in frames:
        if time.monotonic()>=corner_grid_end:break
        used={p['id'] for s in frame['sheets'] for p in s['pieces']}
        families,_=source_families([p for p in sources if p['id'] not in used])
        families.sort(key=lambda f:-len(f)*f[0]['area_m2'])
        for rotated in (None,True,False):
            if time.monotonic()>=corner_grid_end:break
            trial=deepcopy(frame)
            for sheet in trial['sheets']:pool.add(sheet,'fresh_corner_frame')
            for family in families[:5]:
                if time.monotonic()>=corner_grid_end:break
                result=_place_family_grid(trial,family,width,height,kerf,corner_grid_end,
                    occupied_first=True,prefer_rotated=rotated)
                if result is not None:
                    board=result[1]['board']
                    pool.add(trial['sheets'][board],'corner_family_grid')
            for order in ('area_desc','long_side_desc'):
                if time.monotonic()>=corner_grid_end:break
                filled=deepcopy(trial)
                used_ids={p['id'] for s in filled['sheets'] for p in s['pieces']}
                remaining={p['id'] for p in sources if p['id'] not in used_ids}
                _repair(filled,sources,remaining,tuple(range(len(filled['sheets']))),kerf,
                    order,'contact_point',corner_grid_end,prioritize_receivers=True,allow_empty=True)
                for sheet in filled['sheets']:
                    if time.monotonic()>=corner_grid_end:break
                    pool.add(sheet,'coupled_native_repair')
    regular,_=source_families([p for p in sources if p['piece_type']=='Regular'])
    regular.sort(key=lambda f:-len(f)*f[0]['area_m2'])
    blank=deepcopy(incumbent)
    blank['sheets']=[deepcopy(incumbent['sheets'][0])]
    blank['sheets'][0]['pieces']=[]
    _cache(blank['sheets'][0],kerf)
    # Pure-family owner boards first, then complementary two-family boards.
    pairs=[(a,None) for a in regular]
    for i,a in enumerate(regular[:8]):
        for b in regular[i+1:8]:pairs.extend(((a,b),(b,a)))
    for a,b in pairs:
        if time.monotonic()>=grid_end:break
        for rotated in (False,True):
            trial=deepcopy(blank)
            _place_family_grid(trial,a,width,height,kerf,grid_end,occupied_first=False,prefer_rotated=rotated)
            if b is not None:
                _place_family_grid(trial,b,width,height,kerf,grid_end,occupied_first=False)
            pool.add(trial['sheets'][0],'complementary_regular_grid')
    trace['patterns']=len(pool.patterns)
    trace['pattern_origins']={kind:sum(p.origin==kind for p in pool.patterns)
        for kind in {p.origin for p in pool.patterns}}
    if solver is not None and pool.patterns and time.monotonic()<deadline:
        master_end=min(deadline,started+(deadline-started)*.72)
        columns=tuple(p.column for p in pool.patterns)
        answer=solver(columns,pool.demand,len(best['sheets']),deadline=master_end)
        trace['master_status']=getattr(answer,'status','invalid_selection')
        from .pattern_master import valid_selection
        if valid_selection(columns,pool.demand,answer,len(best['sheets'])):
            offer(pool.reconstruct(answer.multiplicities,best))
    row_end=started+(deadline-started)*.9
    floor=incumbent['industrial_metrics']['largest_reusable_free_area_m2']
    # A zero-floor cover can discover a better complement despite different
    # solver tie-breaks; it is exploratory and still passes the final guard.
    jobs=([(frames[0],False,0.,False),(frames[0],False,floor,False)] if frames else [])+[
        (frame,False,floor,True) for frame in frames]+[
        (frame,True,floor,False) for frame in frames]
    for index,(frame,transpose,target,work) in enumerate(jobs):
        if time.monotonic()>=row_end:break
        # CBC's first cover gets only part of this allowance. Very short
        # slices can return not_solved while leaving most stage time unused.
        local=min(row_end,time.monotonic()+2.)
        trial,stage=price_shelf_layout(frame,incumbent,sources,width,height,kerf,
            deadline=local,solver=row_solver,min_remnant_m2=target,transpose=transpose,
            column_order='width_desc',cut_work=work)
        stage['cut_work']=work
        trace['row_pricing'].append(stage)
        offer(trial)
    if time.monotonic()<deadline-.1 and len(candidates)>1:
        tail,tail_trace=improve_fixed_board_layout(best,sources,width,height,kerf,
            deadline=deadline-.05,machine_type=machine_type,mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs,policy=FixedBoardSearchPolicy(
                operators=('grid','relocate','repack','owner_repack'),max_attempts=96,pinned_shapes=True))
        for trial in tail[1:]:offer(trial)
        trace['tail']=dict(attempts=tail_trace.get('attempts'),stop=tail_trace.get('stop'))
    ranked=sorted(candidates,key=quality)
    trace.update(elapsed_sec=round(time.monotonic()-started,3),
                 stop='deadline' if time.monotonic()>=deadline else 'completed')
    from .cut_line_quality import plan_cut_line_quality
    alternatives=[p for p in ranked if material_signature(p)!=material_signature(incumbent)]
    nominees=[]
    if alternatives:
        priority=[alternatives[0],min(alternatives,key=lambda p:plan_cut_line_quality(p,kerf)[0]),*alternatives]
        selected=set()
        for p in priority:
            signature=material_signature(p)
            if signature not in selected:
                selected.add(signature)
                nominees.append(p)
            if len(nominees)==4:break
    return [deepcopy(incumbent),*nominees],trace
