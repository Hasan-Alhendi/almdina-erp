"""Bounded Smart-only contact formations using the existing material contract.

Contact vertices propose translations, never authorize them. Both polygons and
every completed plan pass the authoritative clearance/identity/permission gates.
The legacy exact groups remain a fast source alongside non-identical contacts.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations, product
import math
import time

from .dxf_geometry import polygon_area, polygon_distance, polygons_overlap
from .glass_opening_nesting import material_outline_cm
from .nesting_consolidation import best_rigid_translation
from .plan_portfolio import geometry_signature, manufacturing_export_rejection
from . import shape_aware_nesting as shape

_MAX_COMBINATIONS = 48
_MAX_CONTACTS = 192
_MAX_PARTITIONS = 8
_MAX_FINALS = 8


def has_shape_sources(pieces, machine_type):
    return machine_type != 'Panel Saw' and any(p.get('piece_type') in shape._CORNER_TYPES for p in pieces)


def _signature(body):
    return tuple((int(p['id']), round(p['x'], 8), round(p['y'], 8),
                  int(p.get('corner_rotation_quarter_turns') or 0), bool(p.get('mirrored')))
                 for p in sorted(shape._normalize_pieces(body), key=lambda p: int(p['id'])))


def contact_formations(fixed, moving, width, height, kerf, *, deadline, counters, limit=3):
    """Propose vertex/edge-normal contacts; permit shifting *both* bodies.

    No grid, outline approximation, clearance inflation, or stored absolute
    outline is used. Edge normals also cover unequal clipped diagonal slopes.
    Search truncation is recorded separately from geometric incompatibility.
    """
    left = [material_outline_cm(p) for p in fixed]
    right = [material_outline_cm(p) for p in moving]
    if any(p is None for p in left + right):
        counters['unknown_outline'] += 1
        return []
    offsets = {(0., 0.), *product((-kerf, 0., kerf), repeat=2)}
    for polygon in left + right:
        for a,b in zip(polygon, (*polygon[1:], polygon[0])):
            dx,dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx,dy)
            if length:
                for sign in (-1,1):
                    offsets.add((sign*kerf*dy/length, -sign*kerf*dx/length))
                    # Axis intercept of the offset edge: essential when a
                    # diagonal contact and a board edge constrain one axis.
                    if abs(dy)>1e-9:
                        offsets.add((sign*kerf*length/abs(dy),0.))
                    if abs(dx)>1e-9:
                        offsets.add((0.,sign*kerf*length/abs(dx)))
    anchors = set()
    for l,r in product(left,right):
        for a,b in product(l,r):
            for dx,dy in offsets:
                anchors.add((a[0]-b[0]+dx,a[1]-b[1]+dy))
    ranked = []
    for dx,dy in anchors:
        if not any(min(a['x']+a['w'],b['x']+dx+b['w'])-max(a['x'],b['x']+dx)>1e-6
                   and min(a['y']+a['h'],b['y']+dy+b['h'])-max(a['y'],b['y']+dy)>1e-6
                   for a,b in product(fixed,moving)):
            continue
        min_x = min(min(p['x'] for p in fixed), min(p['x']+dx for p in moving))
        min_y = min(min(p['y'] for p in fixed), min(p['y']+dy for p in moving))
        w = max(max(p['x']+p['w'] for p in fixed),max(p['x']+dx+p['w'] for p in moving))-min_x
        h = max(max(p['y']+p['h'] for p in fixed),max(p['y']+dy+p['h'] for p in moving))-min_y
        if w <= width+1e-6 and h <= height+1e-6:
            ranked.append((w*h,w,h,dx,dy))
    ranked.sort()
    counters['contact_enumeration_limit'] += max(0,len(ranked)-_MAX_CONTACTS)
    found,seen,aspects = [],set(),set()
    for _,_,_,dx,dy in ranked[:_MAX_CONTACTS]:
        if time.monotonic() >= deadline:
            counters['insufficient_budget'] += 1
            break
        counters['contact_tests'] += 1
        shifted = [tuple((x+dx,y+dy) for x,y in polygon) for polygon in right]
        if any(polygons_overlap(a,b) or polygon_distance(a,b)+1e-6 < kerf
               for a,b in product(left,shifted)):
            continue
        body = shape._normalize_pieces([*fixed,*shape._translate_pieces(moving,dx,dy)])
        signature = _signature(body)
        aspect=tuple(round(v,7) for v in shape._block_size(body))
        if signature in seen or aspect in aspects:
            continue
        seen.add(signature)
        aspects.add(aspect)
        found.append(body)
        if len(found) >= limit:
            break
    return found


def _block(body,kerf):
    body = shape._normalize_pieces(body)
    width,height = shape._block_size(body)
    # These are search regions only. Real polygons prove every guest position.
    voids = []
    for p in body:
        notch = shape._notch_bounds(material_outline_cm(p))
        if notch:
            voids.append(dict(x=notch['x']+kerf,y=notch['y']+kerf,
                              w=notch['w']-2*kerf,h=notch['h']-2*kerf))
    voids.append(dict(x=0.,y=0.,w=width,h=height))
    return dict(kind='geometry', pieces=body, guests=[], voids=voids,
                host_kind=body[0]['piece_type'])


def _partitions(pieces,width,height,kerf,mirroring_allowed,deadline,diagnostic):
    counters = Counter()
    corners = [p for p in pieces if p.get('piece_type') in shape._CORNER_TYPES]
    trace = {int(p['id']): dict(eligible_combinations=0,tested_combinations=0,valid_formations=0)
             for p in corners}
    options = {int(p['id']): [shape._placed_corner(p,x_cm=0,y_cm=0,mirrored=m,turns=t)
                             for m,t,*_ in shape._orientations(p,mirroring_allowed)] for p in corners}
    for piece_id,placed in options.items():
        proven=[p for p in placed if material_outline_cm(p) is not None]
        if len(proven)!=len(placed):
            counters['unknown_source_outline']+=1
        options[piece_id]=proven
    counters['rotation_not_permitted'] = sum(not shape._rotation_allowed(p) for p in corners)
    counters['mirroring_not_permitted'] = len(corners) if not mirroring_allowed else 0
    eligible = [(a,b) for a,b in combinations(corners,2) if a['piece_type']==b['piece_type']]
    diagnostic['eligible_combinations'] = len(eligible)
    for a,b in eligible:
        for p in (a,b):
            trace[int(p['id'])]['eligible_combinations'] += 1
    groups = shape._identical_groups(corners)
    counters['legacy_dimension_mismatch'] = len(eligible)-sum(len(g)*(len(g)-1)//2 for g in groups)
    counters['no_eligible_combination'] = int(not eligible)
    partitions = shape._cluster_sheet(corners,width,height,kerf,mirroring_allowed=mirroring_allowed,
        deadline=deadline,formation_alternatives=True)
    pairs=[]
    # Cross-size opportunities are not gated on rectangular or legacy ranking.
    dimensions=('width_cm','length_cm','clipped_corner_width_cm','clipped_corner_length_cm')
    eligible.sort(key=lambda ab: (all(ab[0].get(key)==ab[1].get(key) for key in dimensions),
                                  int(ab[0]['id']),int(ab[1]['id'])))
    counters['combination_enumeration_limit'] = max(0,len(eligible)-_MAX_COMBINATIONS)
    for index,(a,b) in enumerate(eligible[:_MAX_COMBINATIONS]):
        if time.monotonic() >= deadline:
            counters['budget_unvisited_combinations'] += min(len(eligible),_MAX_COMBINATIONS)-index
            break
        diagnostic['tested_combinations'] += 1
        for p in (a,b):
            trace[int(p['id'])]['tested_combinations'] += 1
        first,second = options[int(a['id'])], options[int(b['id'])]
        if not first or not second:
            counters['no_permitted_orientation'] += 1
            continue
        if polygon_area(material_outline_cm(first[0]))+polygon_area(material_outline_cm(second[0])) > width*height+1e-6:
            counters['material_area_exceeds_board'] += 1
            continue
        hits=[]
        for left,right in product(first,second):
            if time.monotonic() >= deadline:
                break
            hits.extend(contact_formations([left],[right],width,height,kerf,
                deadline=deadline,counters=counters,limit=2))
        hits.sort(key=lambda body: (math.prod(shape._block_size(body)),
                                   max(shape._block_size(body)),_signature(body)))
        if not hits:
            counters['no_valid_contact_in_bounded_search'] += 1
        # Compact area alone misses a slightly larger but narrower formation
        # that leaves room for the rest of the order. Preserve both extremes.
        if hits:
            hits=[hits[0],min(hits,key=lambda b:shape._block_size(b)),
                  min(hits,key=lambda b:tuple(reversed(shape._block_size(b)))),*hits]
        diverse=[]
        aspects=set()
        for body in hits:
            aspect=tuple(round(v,7) for v in shape._block_size(body))
            if aspect not in aspects:
                aspects.add(aspect)
                diverse.append(body)
            if len(diverse)>=4:
                break
        for body in diverse:
            pairs.append(_block(body,kerf))
            for p in (a,b):
                trace[int(p['id'])]['valid_formations'] += 1
    # Keep different members, aspect ratios and orientations before completion.
    seen=set()
    for block in pairs:
        signature=_signature(block['pieces'])
        if signature not in seen:
            seen.add(signature)
            partitions.append([block])
    # Disjoint contacts can coexist. Compare separate pairs and a compact quad.
    combined=set()
    for a,b in combinations(pairs,2):
        if time.monotonic() >= deadline:
            break
        if {p['id'] for p in a['pieces']} & {p['id'] for p in b['pieces']}:
            continue
        key=(_signature(a['pieces']),_signature(b['pieces']))
        if key in combined:
            continue
        combined.add(key)
        partitions.append([a,b])
        for body in contact_formations(a['pieces'],b['pieces'],width,height,kerf,
                                       deadline=deadline,counters=counters,limit=1):
            partitions.append([_block(body,kerf)])
        if len(combined)>=4:
            break
    # Singles are an independent choice, not a fallback only after pair failure.
    for p in corners[:2]:
        single=shape._inward_single(p,width,height,mirroring_allowed=mirroring_allowed)
        if single:
            partitions.append([_block(single['pieces'],kerf)])
        elif options[int(p['id'])]:
            for placed in options[int(p['id'])][:2]:
                if shape._pieces_inside([placed],width,height):
                    partitions.append([_block([placed],kerf)])
    diagnostic['generated_formations']=len({ _signature(b['pieces']) for part in partitions for b in part })
    diagnostic['piece_trace']=trace
    diagnostic['reasons']=dict(counters)
    # Alternate legacy and geometric partitions instead of spending every slot
    # on exact quads. The final industrial rank is never used to prune here.
    legacy=[p for p in partitions if all(b['kind']!='geometry' for b in p)]
    geometric=[p for p in partitions if any(b['kind']=='geometry' for b in p)]
    geometric.sort(key=lambda part: (-len({p['piece_type'] for b in part for p in b['pieces']}),
                                    -len({p['id'] for b in part for p in b['pieces']})))
    result=[]
    for i in range(max(len(legacy),len(geometric))):
        for source in (geometric,legacy):
            if i<len(source):
                result.append(source[i])
    counters['partition_enumeration_limit']=max(0,len(result)-_MAX_PARTITIONS)
    diagnostic['reasons']=dict(counters)
    return result[:_MAX_PARTITIONS]


def _pack(baseline, pieces, blocks, width,height,kerf,mirror,excluded,deadline):
    from .optimizer import _run_preordered_method
    from .plan_search import _spot_on_sheet
    seated=shape._seat_void_guests(deepcopy(blocks),pieces,kerf,width,height,
        mirroring_allowed=mirror,hosted=set(),guest_exclusions=excluded,quarter_turns_only=True,deadline=deadline)
    sheets=[]
    for block in seated:
        body=shape._normalize_pieces(block['pieces'])
        found=None
        for sheet in sheets:
            found=best_rigid_translation(sheet,body,kerf,width,height,deadline=deadline)
            if found:
                sheet['pieces'].extend(shape._translate_pieces(body,found[0],found[1]))
                break
        if found is None:
            if not shape._pieces_inside(body,width,height):
                return None
            sheets.append(dict(sheet_no=len(sheets)+1,w=width,h=height,pieces=body))
    used={p['id'] for b in seated for p in b['pieces']}
    remainder=[p for p in pieces if p['id'] not in used]
    for sheet in sheets:
        if time.monotonic()>=deadline:
            return None
        remainder=shape._fill_free_space(sheet,remainder,kerf,
            lambda s,p,k:_spot_on_sheet(s,p,k,deadline_monotonic=deadline),width,height)
    if remainder:
        if time.monotonic()>=deadline:
            return None
        raw=_run_preordered_method(sorted(remainder,key=lambda p:-p['width_cm']*p['length_cm']),
            remainder,width,height,kerf,'MaxRects Best Short Side','shape_first_remainder')
        if raw.get('unplaced'):
            return None
        sheets.extend(raw['sheets'])
    for i,sheet in enumerate(sheets,1):
        sheet['sheet_no']=i
    plan=shape._plan_from(baseline,sheets)
    plan['shape_nesting_diagnostics']=dict(outcome='accepted',formations=[b['kind'] for b in seated],
        formation_ids=[[int(p['id']) for p in original['pieces']] for original in blocks],
        void_guests=[int(p['id']) for b in seated for p in b['guests']],reserved_ids=[],dropped=[])
    return plan


def geometry_first_candidates(baseline,pieces,width,height,kerf,*,machine_type,
                              mirroring_allowed,deadline,metric_kwargs):
    """Discover formations before packing, then compare complete proven plans."""
    from .evaluation import validate_plan, placement_permission_errors
    from .optimizer import enrich_plan_metrics
    from .joint_nesting import complete_shape_candidate
    diagnostic=dict(eligible_combinations=0,tested_combinations=0,generated_formations=0,
                    valid_formations=0,completed_plans=0,reasons={},piece_trace={})
    if not has_shape_sources(pieces,machine_type) or time.monotonic()>=deadline:
        diagnostic['reasons']['insufficient_budget']=1
        return [],diagnostic
    generation_deadline=min(deadline,time.monotonic()+max(0,deadline-time.monotonic())*.45)
    partitions=_partitions(pieces,width,height,kerf,mirroring_allowed,generation_deadline,diagnostic)
    finals,seen,proven=[],set(),set()
    all_ids=frozenset(int(p['id']) for p in pieces)
    for blocks in partitions:
        # A vacant void is a real alternative; filling every opening is not a
        # prerequisite. It may preserve the guest needed by a Glass host.
        for excluded in (frozenset(),all_ids):
            if len(finals)>=_MAX_FINALS or time.monotonic()>=deadline:
                reason='completion_enumeration_limit' if len(finals)>=_MAX_FINALS else 'insufficient_completion_budget'
                diagnostic['reasons'][reason]=diagnostic['reasons'].get(reason,0)+1
                break
            candidate=_pack(baseline,pieces,blocks,width,height,kerf,mirroring_allowed,excluded,deadline)
            if candidate is None:
                diagnostic['reasons']['cannot_repack']=diagnostic['reasons'].get('cannot_repack',0)+1
                continue
            if validate_plan(candidate,pieces,width,height,kerf_cm=kerf,deadline_monotonic=deadline) or placement_permission_errors(
                    candidate,pieces,mirroring_allowed=mirroring_allowed):
                diagnostic['reasons']['validation_or_permission']=diagnostic['reasons'].get('validation_or_permission',0)+1
                continue
            proven.update(_signature(b['pieces']) for b in blocks)
            end=min(deadline,time.monotonic()+max(0,deadline-time.monotonic())/max(2,_MAX_FINALS-len(finals)))
            candidate=complete_shape_candidate(candidate,pieces,width,height,kerf,machine_type=machine_type,
                mirroring_allowed=mirroring_allowed,deadline=end,metric_kwargs=metric_kwargs)
            rejection=manufacturing_export_rejection(candidate)
            if rejection or validate_plan(candidate,pieces,width,height,kerf_cm=kerf) or placement_permission_errors(
                    candidate,pieces,mirroring_allowed=mirroring_allowed):
                reason=rejection or 'completed_validation'
                diagnostic['reasons'][reason]=diagnostic['reasons'].get(reason,0)+1
                continue
            candidate=enrich_plan_metrics(candidate,str(candidate.get('method_key') or ''),machine_type,**metric_kwargs)
            signature=geometry_signature(candidate)
            if signature not in seen:
                seen.add(signature)
                finals.append(candidate)
    diagnostic['completed_plans']=len(finals)
    diagnostic['valid_formations']=len(proven)
    return finals,diagnostic
