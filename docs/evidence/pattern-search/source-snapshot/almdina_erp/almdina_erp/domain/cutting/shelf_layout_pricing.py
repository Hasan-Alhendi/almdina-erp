"""Coupled family-row pricing in disjoint native space around pinned nests.

The backend assigns row quantities to slots, not individual source geometry.
Rows and columns are real legal source orientations, with no virtual parts.
"""
from collections import defaultdict, deque
from copy import deepcopy
import math
import time

from .pattern_master import ShelfColumn, ShelfSelection
from .pattern_layout_search import source_families
from .primitives import orientations_for
from .regular_templates import _unprotected_regular
from .same_count_layout_search import _cache, _movable_sources
from .strategies.maxrects import place_piece_maxrects

_UNIT=10**6  # cm; conversion never relaxes the independent geometric gates.


def disjoint_slots(sheets,kerf):
    """Sweep bbox obstacles, merge adjacent slabs, guard artificial seams."""
    slots=[]
    for board,sheet in enumerate(sheets):
        w,h=sheet['w'],sheet['h']
        obstacles=[(max(0,p['x']-kerf),max(0,p['y']-kerf),
                    min(w,p['x']+p['w']+kerf),min(h,p['y']+p['h']+kerf)) for p in sheet['pieces']]
        xs=sorted({0.,w,*(v for rect in obstacles for v in (rect[0],rect[2]))})
        active={}
        rectangles=[]
        for left,right in zip(xs,xs[1:]):
            if right-left<1e-8:
                continue
            spans=sorted((top,bottom) for x,top,end,bottom in obstacles if x<right-1e-8 and end>left+1e-8)
            free=[]
            cursor=0.
            for top,bottom in spans:
                if top>cursor+1e-8:
                    free.append((cursor,top))
                cursor=max(cursor,bottom)
            if cursor<h-1e-8:
                free.append((cursor,h))
            next_active={}
            for top,bottom in free:
                key=(top,bottom)
                if key in active and abs(active[key]['x']+active[key]['w']-left)<1e-8:
                    rect=active[key]
                    rect['w']=right-rect['x']
                else:
                    rect=dict(board=board,x=left,y=top,w=right-left,h=bottom-top)
                    rectangles.append(rect)
                next_active[key]=rect
            active=next_active
        # A cell boundary inside free material needs half a Kerf on each side.
        for rect in rectangles:
            shrink=[0.,0.,0.,0.]
            for other in rectangles:
                if rect is other:
                    continue
                overlap_y=min(rect['y']+rect['h'],other['y']+other['h'])-max(rect['y'],other['y'])
                overlap_x=min(rect['x']+rect['w'],other['x']+other['w'])-max(rect['x'],other['x'])
                if overlap_y>1e-8:
                    if abs(rect['x']-(other['x']+other['w']))<1e-8: shrink[0]=kerf/2
                    if abs(rect['x']+rect['w']-other['x'])<1e-8: shrink[2]=kerf/2
                if overlap_x>1e-8:
                    if abs(rect['y']-(other['y']+other['h']))<1e-8: shrink[1]=kerf/2
                    if abs(rect['y']+rect['h']-other['y'])<1e-8: shrink[3]=kerf/2
            cell=dict(rect,x=rect['x']+shrink[0],y=rect['y']+shrink[1],
                w=rect['w']-shrink[0]-shrink[2],h=rect['h']-shrink[1]-shrink[3])
            if min(cell['w'],cell['h'])>1e-8:
                slots.append(cell)
    return slots


def row_patterns(families,width,height,kerf,transpose,deadline,limit=512):
    options=[]
    for group,family in enumerate(families):
        for orientation in orientations_for(family[0]):
            across=orientation['h'] if transpose else orientation['w']
            thick=orientation['w'] if transpose else orientation['h']
            if across<=width+1e-8 and thick<=height+1e-8:
                options.append((group,across,thick,orientation))
    generated={}
    single=[]

    def add(members):
        members=tuple(sorted(members,key=lambda v:v[0]))
        signature=tuple((g,o['rotated'],q) for g,o,q in members)
        if signature in generated:
            return signature
        counts=[0]*len(families)
        used=0.
        thick=0.
        area=0.
        for group,orientation,qty in members:
            across=orientation['h'] if transpose else orientation['w']
            h=orientation['w'] if transpose else orientation['h']
            counts[group]+=qty
            used+=qty*across
            thick=max(thick,h)
            area+=qty*across*h
        used+=(sum(counts)-1)*kerf
        if used>width+1e-8 or sum(counts)>64:
            return None
        generated[signature]=dict(column=ShelfColumn(tuple(counts),round((thick+kerf)*_UNIT)),
            members=members,height=thick,used_width=used,
            quality=((width*thick-area)/(width*thick),-area,thick))
        return signature

    # Always retain every legal source orientation and its singleton. A fixed
    # row cap must never silently remove an uncommon family's only coverage.
    for group,across,thick,orientation in options:
        maximum=min(len(families[group]),64,int((width+kerf+1e-8)/(across+kerf)))
        for qty in sorted({1,maximum},reverse=True):
            single.append(add(((group,orientation,qty),)))
    for index,(g,w,h,orientation) in enumerate(options):
        if time.monotonic()>=deadline:
            break
        maximum=min(len(families[g]),64,int((width+kerf)/(w+kerf)))
        for other,ow,oh,oo in options[index+1:]:
            if other==g:
                continue
            for qty in range(1,maximum+1):
                available=width-qty*w-qty*kerf
                fitted=min(len(families[other]),64-qty,int((available+kerf+1e-8)/(ow+kerf)))
                for count in {1,fitted}:
                    if 0<count<=fitted:
                        add(((g,orientation,qty),(other,oo,count)))
    # Extend dense pairs with a third family. This nominates mixed-height
    # shelves without changing the height or width of any original piece.
    pairs=sorted((p for p in generated.values() if len(p['members'])==2),key=lambda p:p['quality'])[:32]
    for pair in pairs:
        if time.monotonic()>=deadline:
            break
        used_groups={g for g,_,_ in pair['members']}
        count=sum(pair['column'].counts)
        for group,across,thick,orientation in options:
            if group in used_groups:
                continue
            qty=min(len(families[group]),64-count,int((width-pair['used_width']+1e-8)/(across+kerf)))
            if qty>0:
                add((*pair['members'],(group,orientation,qty)))
    chosen=[]
    seen=set()
    for signature in single:
        if signature is not None and signature not in seen:
            chosen.append(generated[signature]);seen.add(signature)
    mixed=sorted(((key,p) for key,p in generated.items() if key not in seen),key=lambda v:v[1]['quality'])
    # Several complementary rows per family before global density competes.
    # One nominally best row can consume another scarce family's only partner.
    for group in range(len(families)):
        selected=0
        for key,p in mixed:
            if p['column'].counts[group] and key not in seen and len(chosen)<limit:
                chosen.append(p);seen.add(key);selected+=1
                if selected==4:
                    break
    for key,p in mixed:
        if len(chosen)>=limit:
            break
        if key not in seen:
            chosen.append(p);seen.add(key)
    return chosen


def price_shelf_layout(frame,template,sources,width,height,kerf,*,deadline,solver,
                       min_remnant_m2,transpose=False):
    trace=dict(status='not_run',rows=0,slots=0,transpose=transpose,target_remnant_m2=min_remnant_m2)
    if solver is None or time.monotonic()>=deadline:
        return None,trace
    movable={p['id'] for p in _movable_sources(frame,sources,kerf)}
    sheets=deepcopy(frame['sheets'])
    for sheet in sheets:
        sheet['pieces']=[p for p in sheet['pieces'] if p['id'] not in movable]
    fixed={p['id'] for s in sheets for p in s['pieces']}
    pending=[p for p in sources if p['id'] not in fixed]
    if not pending:
        return None,trace
    if any(not _unprotected_regular(p) for p in pending):
        return None,dict(trace,status='unsupported_pending')
    families,_=source_families(pending)
    slots=disjoint_slots(sheets,kerf)
    if not slots or len(slots)>32:
        trace['status']='slot_limit'
        return None,trace
    blank=[i for i,s in enumerate(sheets) if not s['pieces']]
    owner=max(range(len(slots)),key=lambda i: (slots[i]['board'] in blank,
        slots[i]['board'],slots[i]['w']*slots[i]['h']))
    owner_w=slots[owner]['h'] if transpose else slots[owner]['w']
    owner_h=slots[owner]['w'] if transpose else slots[owner]['h']
    owner_limit=owner_h+kerf-min_remnant_m2*10000/owner_w
    if owner_limit<0:
        trace['status']='owner_too_small'
        return None,trace
    cached={}
    options=[]
    capacities=[]
    for slot in slots:
        w,h=(slot['h'],slot['w']) if transpose else (slot['w'],slot['h'])
        key=(w,h)
        if key not in cached:
            cached[key]=row_patterns(families,w,h,kerf,transpose,deadline,
                                    limit=min(512,max(224,16*len(families))))
        options.append(cached[key])
        capacities.append(round((h+kerf)*_UNIT))
    columns=tuple(tuple(p['column'] for p in choices) for choices in options)
    trace.update(rows=sum(map(len,columns)),slots=len(slots))
    if time.monotonic()>=deadline:
        trace['status']='deadline'
        return None,trace
    answer=solver(columns,tuple(map(len,families)),tuple(capacities),
        tuple(s['board'] for s in slots),tuple(bool(s['pieces']) for s in sheets),
        owner,math.floor(owner_limit*_UNIT+1e-5),deadline=deadline)
    trace['status']=getattr(answer,'status','invalid_selection')
    if (not isinstance(answer,ShelfSelection) or len(answer.allocations)!=len(slots)
            or any(len(values)!=len(choices) or any(type(v) is not int or not 0<=v<=256 for v in values)
                   for values,choices in zip(answer.allocations,columns))):
        return None,trace
    demand=tuple(map(len,families))
    actual=tuple(sum(value*col.counts[g] for values,cols in zip(answer.allocations,columns)
                    for value,col in zip(values,cols)) for g in range(len(families)))
    if actual!=demand:
        trace['status']='invalid_coverage'
        return None,trace
    for index,(values,cols,cap) in enumerate(zip(answer.allocations,columns,capacities)):
        used=sum(n*c.thickness for n,c in zip(values,cols))
        if used>cap or (index==owner and used>math.floor(owner_limit*_UNIT+1e-5)):
            trace['status']='invalid_capacity'
            return None,trace
    available=[deque(family) for family in families]
    for slot,choices,values in zip(slots,options,answer.allocations):
        rows=[row for row,qty in zip(choices,values) for _ in range(qty)]
        rows.sort(key=lambda row:(-row['used_width'],-row['height']))
        vertical=0.
        sheet=sheets[slot['board']]
        _cache(sheet,kerf)
        for row in rows:
            horizontal=0.
            for group,orientation,quantity in row['members']:
                for _ in range(quantity):
                    source=available[group].popleft()
                    x=slot['x']+(vertical if transpose else horizontal)
                    y=slot['y']+(horizontal if transpose else vertical)
                    place_piece_maxrects(sheet,source,dict(x=x,y=y,**orientation),kerf)
                    horizontal+=(orientation['h'] if transpose else orientation['w'])+kerf
            vertical+=row['height']+kerf
    if any(available):
        return None,dict(trace,status='invalid_identity')
    trial=deepcopy(template)
    trial['sheets']=[s for s in sheets if s['pieces']]
    if any(len(s['pieces'])>64 for s in trial['sheets']):
        return None,dict(trace,status='network_piece_limit')
    for index,sheet in enumerate(trial['sheets']):
        sheet['sheet_no']=index+1
    trial['unplaced']=[]
    return trial,trace
