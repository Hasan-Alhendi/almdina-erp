"""Composite shape destroy/repair and adaptive Regular refinement.

Exploration skeletons may temporarily have a worse remnant or one extra board.
Only a complete independently validated winner can enter the output gallery.
No designer geometry, fabricated parts, persisted learning, or new stock.
"""
from __future__ import annotations

from copy import deepcopy
from collections import defaultdict, deque
from dataclasses import replace
import time

from .cut_line_quality import final_system_sort_keys, plan_cut_line_quality
from .same_count_layout_search import (
    FixedBoardSearchPolicy, MIXED_LAYOUT_OPERATORS,
    _valid, _cache, _repair, improve_fixed_board_layout, material_signature,
)
from . import shape_aware_nesting as shape
from .nesting_consolidation import best_rigid_translation
from .primitives import make_placed_piece
from .placement_orientation import resolve_placement_orientation
from .regular_templates import grid_specs
from .regular_templates import _unprotected_regular
from .strategies.maxrects import place_piece_maxrects


def _body_rotations(body, sources):
    """Legal new block orientations; Regular guests retain source-owned sides."""
    lookup = {p['id']: p for p in sources}
    current = shape._normalize_pieces(body)
    variants = [current]
    for _ in range(3):
        _, height = shape._block_size(current)
        rotated = []
        for placed in current:
            source = lookup[placed['id']]
            x, y = height-placed['y']-placed['h'], placed['x']
            if source['piece_type'] in shape._CORNER_TYPES:
                orientation = resolve_placement_orientation(placed)
                turns = (orientation.quarter_turns+1) % 4
                if turns and not source.get('allow_rotation'):
                    return [variants[0]]
                moved = shape._placed_corner(source, x_cm=x, y_cm=y,
                    mirrored=orientation.mirrored, turns=turns)
            else:
                swapped = abs(placed['h']-source['width_cm']) > 1e-7
                if swapped and not source.get('allow_rotation'):
                    return [variants[0]]
                moved = make_placed_piece(source, x, y, placed['h'], placed['w'], swapped)
            rotated.append(moved)
        current = shape._normalize_pieces(rotated)
        variants.append(current)
    return [variants[i] for i in (0, 2, 1, 3)]


def _skeletons(plan, sources, width, height, kerf, mirror, deadline):
    """Fair repair scheduling: a large first family cannot consume every probe."""
    variations = iter(_skeleton_variations(plan, sources, width, height, kerf, mirror, deadline))
    pending = deque()
    exhausted = False
    attempts = 0
    # Preserve the early coupled-family probes before the broader scheduler.
    # Breadth alone otherwise starves the second repair order of every family.
    for _ in range(4):
        if time.monotonic() >= deadline:
            return
        try:
            skeleton, remaining, event = next(variations)
        except StopIteration:
            exhausted = True
            break
        stream = iter(_repair_variation(skeleton, sources, remaining, event, width, height, kerf, deadline))
        for _ in range(10):
            try:
                attempts += 1
                yield next(stream)
            except StopIteration:
                break
        pending.append(stream)
    while time.monotonic() < deadline and attempts < 256:
        if not exhausted and len(pending) < 16:
            try:
                skeleton, remaining, event = next(variations)
                pending.append(iter(_repair_variation(skeleton, sources, remaining, event,
                                                     width, height, kerf, deadline)))
            except StopIteration:
                exhausted = True
        if not pending:
            if exhausted:
                return
            continue
        for _ in range(min(3, len(pending))):
            stream = pending.popleft()
            try:
                proposal = next(stream)
                attempts += 1
                yield proposal
                pending.append(stream)
            except StopIteration:
                pass


def _repair_variation(skeleton, sources, remaining, event, width, height, kerf, deadline):
    presets = list(_grid_presets(skeleton, sources, remaining, width, height, kerf, deadline))
    if not presets:
        return
    # Native tile preference, both allowed orientation preferences, and an
    # untiled control receive early probes before deeper ordering variants.
    presets = presets[:4] + presets[-1:]
    methods = ('best_short_side', 'contact_point', 'best_area')
    orders = ('width_length_desc', 'dimension_cycle_0', 'area_desc', 'length_desc')
    probes = [(0, order, method, True) for order in orders[:2] for method in methods]
    if len(presets) > 1:
        probes.extend((1, order, 'best_short_side', True) for order in orders[:2])
    probes.extend((0, order, 'contact_boundary', True) for order in orders[:2])
    probes.extend((index, order, method, priority) for order in orders
        for index in range(len(presets)) for priority in (False, True) for method in methods)
    seen = set()
    for index, order, heuristic, priority in probes:
        key = (index, order, heuristic, priority)
        if key in seen:
            continue
        if time.monotonic() >= deadline or len(seen) >= 36:
            return
        seen.add(key)
        preset, pending, tile = presets[index]
        trial = deepcopy(preset)
        complete = _repair(trial, sources, pending, tuple(range(len(trial['sheets']))), kerf,
            order, heuristic, deadline, prioritize_receivers=priority, allow_empty=True)
        if complete:
            trial['sheets'] = [s for s in trial['sheets'] if s['pieces']]
        yield trial if complete else None, dict(event, grid=tile, order=order,
            heuristic=heuristic, prioritize_receivers=priority)


def _skeleton_variations(plan, sources, width, height, kerf, mirror, deadline):
    # Other cohorts retain the proven native nesting pipeline unchanged.
    if (not any(p.get('piece_type') in shape._CORNER_TYPES for p in sources)
            or any(p.get('piece_type') not in {'Regular', *shape._CORNER_TYPES} for p in sources)
            or sum(p.get('piece_type') == 'Regular' for p in sources) > 64
            or sum(p.get('piece_type') in shape._CORNER_TYPES for p in sources) > 16
            or any(p.get('piece_type') == 'Regular' and not _unprotected_regular(p) for p in sources)
            or any(p.get('special_shape_geometry_json') or p.get('geometry') or p.get('overlays') for p in sources)
            or any(p.get('extra_liner') or p.get('extra_back_groove')
                   or p.get('extra_recessed_handle_cutout') for p in sources)):
        return
    partitions = shape._cluster_sheet(sources, width, height, kerf,
        mirroring_allowed=mirror, deadline=deadline, formation_alternatives=True)
    # Equal blanks can form a valid quad even when their notch depths differ.
    # The native identical-notch grouping does not nominate these combinations.
    buckets = defaultdict(list)
    for source in sources:
        if source['piece_type'] in shape._CORNER_TYPES:
            buckets[(source['piece_type'],source['width_cm'],source['length_cm'])].append(source)
    for bucket in buckets.values():
        cuts = {(p['clipped_corner_width_cm'],p['clipped_corner_length_cm']) for p in bucket}
        if len(bucket) < 4 or len(cuts) < 2:
            continue
        mixed = []
        remaining_corners = list(reversed(bucket))
        while len(remaining_corners) >= 4:
            cut_groups = defaultdict(deque)
            for p in remaining_corners:
                cut_groups[(p['clipped_corner_width_cm'],p['clipped_corner_length_cm'])].append(p)
            queue = deque(cut_groups.values())
            nominated = []
            while queue and len(nominated) < 4:
                group = queue.popleft()
                nominated.append(group.popleft())
                if group:
                    queue.append(group)
            quad = shape._take_quad(nominated,width,height,kerf,mirroring_allowed=mirror)
            if quad is None:
                break
            from .geometry_nesting import _block
            block = _block(quad['block']['pieces'],kerf)
            block['kind'] = 'quad'
            mixed.append(block)
            remaining_corners = [p for p in remaining_corners if p['id'] not in quad['ids']]
        mixed.extend(shape._partition_group(remaining_corners,width,height,kerf,mirroring_allowed=mirror))
        grouped = {p['id'] for b in mixed for p in b['pieces']}
        rest = [p for p in sources if p['piece_type'] in shape._CORNER_TYPES and p['id'] not in grouped]
        for group in shape._identical_groups(rest):
            mixed.extend(shape._partition_group(group,width,height,kerf,mirroring_allowed=mirror))
        if mixed:
            partitions.append(mixed)
        if len(partitions) >= 4:
            break
    families = defaultdict(list)
    for p in sources:
        if p['piece_type'] == 'Regular':
            families[(p['width_cm'], p['length_cm'], bool(p.get('allow_rotation')))].append(p)
    fragile = sorted(families.values(), key=lambda members: (
        -len(members)*max(members[0]['width_cm'], members[0]['length_cm'])**2,
        members[0]['id']))[:4]
    batches = [(blocks, chunk) for chunk in range(3) for blocks in partitions]
    for blocks, chunk in batches:
        variants = [(True, frozenset(p['id'] for p in members), spread)
                    for members in fragile for spread in (True, False)]
        variants.extend((area, frozenset(), spread) for area in (True, False) for spread in (True, False))
        for area_first, preferred, spread in variants[chunk*4:chunk*4+4]:
            if time.monotonic() >= deadline:
                return
            seated = shape._seat_void_guests(blocks, sources, kerf, width, height,
                mirroring_allowed=mirror, hosted=set(), quarter_turns_only=True,
                contact_anchors=True, area_first=area_first, preferred_guest_ids=preferred, deadline=deadline)
            # Place rigid proven groups on an empty *existing* board pool first.
            # Crowded incumbent positions otherwise prevent grouping before the
            # subsequent Regular repair can free any room (a coupled move).
            skeleton = deepcopy(plan)
            for sheet in skeleton['sheets']:
                sheet['pieces'] = []
            feasible = True
            used = set()
            for block in sorted(seated, key=lambda b: (b['kind']!='quad', b['kind']!='pair')):
                bodies = _body_rotations(block['pieces'], sources)
                used.update(p['id'] for p in block['pieces'])
                placed = False
                target_sheets = sorted(skeleton['sheets'], key=lambda s: bool(s['pieces'])) if spread else skeleton['sheets']
                for sheet in target_sheets:
                    for body in bodies:
                        if time.monotonic() >= deadline:
                            return
                        found = best_rigid_translation(sheet, body, kerf, width, height,
                            constraint='pair' if block['kind']=='pair' else '', deadline=deadline)
                        if found is not None:
                            sheet['pieces'].extend(shape._translate_pieces(body, found[0], found[1]))
                            placed = True
                            break
                    if placed:
                        break
                if not placed:
                    feasible = False
                    break
            if not feasible:
                continue
            remaining = {p['id'] for p in sources if p['id'] not in used}
            if len(remaining) > 64 or any(p['piece_type']!='Regular' for p in sources if p['id'] in remaining):
                continue
            for sheet in skeleton['sheets']:
                _cache(sheet, kerf)
            yield skeleton, remaining, dict(area_first=area_first, spread=spread,
                preferred_guest_ids=sorted(preferred), formations=[b['kind'] for b in seated],
                guest_ids=[p['id'] for b in seated for p in b.get('guests') or []])


def _grid_presets(skeleton, sources, remaining, width, height, kerf, deadline):
    """Seat an original repeated family in a native free rectangle before repair.

    Long-family rows are a coupled placement: a single-piece greedy insertion
    can fragment their only compatible strip. No virtual grid piece is made.
    """
    families = defaultdict(list)
    for source in sources:
        if source['id'] in remaining:
            families[(source['width_cm'],source['length_cm'],bool(source.get('allow_rotation')))].append(source)
    groups = sorted(families.values(),key=lambda ps:(-len(ps)*max(ps[0]['width_cm'],ps[0]['length_cm'])**2,ps[0]['id']))[:4]
    # Coupled family strips on the already occupied shape boards first. A full
    # family on a blank board can look locally attractive while wasting the
    # only compatible strip next to a shape and stranding long pieces later.
    for occupied_first, orientation_mask in ((True,None),(False,None),(True,15),(False,15)):
        combined = deepcopy(skeleton)
        combined_remaining = set(remaining)
        tiles = []
        for index, family in enumerate(groups):
            choice = _place_family_grid(combined, family, width, height, kerf, deadline,
                occupied_first=occupied_first,
                prefer_rotated=None if orientation_mask is None else bool((orientation_mask >> index) & 1))
            if choice is not None:
                used, tile = choice
                combined_remaining -= used
                tiles.append(tile)
        if tiles:
            yield combined, combined_remaining, dict(occupied_first=occupied_first,
                orientation_mask=orientation_mask, tiles=tiles)
    for family in groups:
        trial = deepcopy(skeleton)
        choice = _place_family_grid(trial, family, width, height, kerf, deadline, occupied_first=False)
        if choice is not None:
            used, tile = choice
            yield trial, remaining-used, tile
    yield skeleton, remaining, None


def _place_family_grid(skeleton, family, width, height, kerf, deadline, *, occupied_first, prefer_rotated=None):
    choices = []
    for members, orientation, columns, rows in grid_specs(family, width, height, kerf):
        if time.monotonic() >= deadline:
            return None
        gw = columns*orientation['w']+(columns-1)*kerf
        gh = rows*orientation['h']+(rows-1)*kerf
        for index, sheet in enumerate(skeleton['sheets']):
            for rect in sheet['free_rects']:
                if gw <= rect['w']+1e-8 and gh <= rect['h']+1e-8:
                    prefix = ((not bool(sheet['pieces']), -columns*rows) if occupied_first
                              else (-columns*rows, not bool(sheet['pieces'])))
                    orientation_preference = 0 if prefer_rotated is None else int(orientation['rotated'] != prefer_rotated)
                    choices.append(((*prefix, orientation_preference, rect['w']*rect['h']-gw*gh, index,
                        rect['y'], rect['x'], orientation['rotated']), index, rect, members, orientation, columns, rows))
    if not choices:
        return None
    _, index, rect, members, orientation, columns, rows = min(choices, key=lambda c:c[0])
    members = members[:columns*rows]
    for i, source in enumerate(members):
        spot = dict(x=rect['x']+(i%columns)*(orientation['w']+kerf),
                    y=rect['y']+(i//columns)*(orientation['h']+kerf), **orientation)
        place_piece_maxrects(skeleton['sheets'][index], source, spot, kerf)
    return {p['id'] for p in members}, dict(board=index, columns=columns, rows=rows,
        family=[family[0]['width_cm'], family[0]['length_cm']], count=len(members))


def _ranked(plans):
    keys = final_system_sort_keys(plans)
    return [p for _, p in sorted(zip(keys, plans), key=lambda item:item[0])]


def refine_system_layout(plan, sources, width, height, kerf, *, deadline,
                         machine_type, mirroring_allowed, metric_kwargs):
    """Preserve the original; explore compound moves before accepting by quality."""
    started = time.monotonic()
    trace = dict(attempts=0, skeletons=0, compound_attempts=0, compound_improvements=0,
                 stop='deadline', operators={}, exploration=[])
    if (machine_type not in {'Auto', 'CNC Router'} or time.monotonic() >= deadline
            or any((s.get('resource_kind') or 'FULL_BOARD') != 'FULL_BOARD' for s in plan.get('sheets') or [])
            or any((p.get('resource_kind') or 'FULL_BOARD') != 'FULL_BOARD' for p in sources)
            or any((p.get('resource_kind') or 'FULL_BOARD') != 'FULL_BOARD'
                   for s in plan.get('sheets') or [] for p in s.get('pieces') or [])):
        trace['stop'] = 'unsupported_or_expired'
        return [deepcopy(plan)], trace
    policy = FixedBoardSearchPolicy(operators=MIXED_LAYOUT_OPERATORS, max_attempts=160,
        pinned_shapes=True, allow_fewer_boards=True, max_removed=32)
    has_shapes = any(p.get('piece_type') in shape._CORNER_TYPES for p in sources)
    # First preserve the ordinary adaptive refinement opportunity. Compound
    # shape repair gets a separate share of this same deadline, not a new clock.
    end = min(deadline, started + (deadline-started)*(.1 if has_shapes else 1.0))
    portfolio, partial = improve_fixed_board_layout(plan, sources, width, height, kerf,
        deadline=end, policy=policy, machine_type=machine_type,
        mirroring_allowed=mirroring_allowed, metric_kwargs=metric_kwargs)
    trace.update(partial)
    trace['partial_attempts'] = partial.get('attempts', 0)
    if partial.get('stop') in {'invalid_incumbent', 'unsupported_cohort'}:
        return [deepcopy(plan)], trace
    seen = {material_signature(p) for p in portfolio}
    best = _ranked(portfolio)[0]
    profiles = {}

    def quality(candidate):
        signature = material_signature(candidate)
        if signature not in profiles:
            profiles[signature] = plan_cut_line_quality(candidate, kerf)
        return profiles[signature]

    def pareto_key(candidate):
        profile = quality(candidate)
        return (len(candidate['sheets']), -candidate['industrial_metrics']['largest_reusable_free_area_m2'],
                round(profile[0], 5), profile[1]) if profile is not None else None

    def trim_portfolio():
        if len(portfolio) <= 16:
            return
        ranked = _ranked(portfolio)
        proven = [p for p in ranked if quality(p) is not None]
        priority = [ranked[0]]
        if proven:
            priority.extend((min(proven,key=lambda p:quality(p)[0]),
                             min(proven,key=lambda p:quality(p)[1])))
        priority.extend(ranked)
        kept, signatures = [], set()
        for candidate in priority:
            signature = material_signature(candidate)
            if signature not in signatures:
                signatures.add(signature)
                kept.append(candidate)
            if len(kept) == 16:
                break
        portfolio[:] = kept

    def offer(candidate, *, already_validated=False):
        nonlocal best
        if candidate is None or len(candidate.get('sheets') or []) > len(best['sheets']):
            return
        checked = candidate if already_validated else _valid(candidate, sources, width, height, kerf, machine_type,
                         metric_kwargs, deadline, mirroring_allowed)
        if checked is None or material_signature(checked) in seen:
            return
        before, after = final_system_sort_keys([best, checked])
        if after < before:
            seen.add(material_signature(checked))
            portfolio.append(checked)
            best = checked
            trace['compound_improvements'] += 1
            trim_portfolio()
            return True
        baseline_key, candidate_key = final_system_sort_keys([plan, checked])
        key = pareto_key(checked)
        if candidate_key < baseline_key and key is not None:
            # Preserve a measured remnant/path trade-off for the gallery. A
            # shorter path need not erase the maximum-remnant incumbent.
            existing = [pareto_key(p) for p in portfolio]
            if not any(v is not None and all(a <= b for a, b in zip(v,key))
                       and any(a < b for a,b in zip(v,key)) for v in existing):
                seen.add(material_signature(checked))
                portfolio.append(checked)
                trim_portfolio()
        return False

    if has_shapes and time.monotonic() < deadline:
        skeleton_deadline = started+(deadline-started)*.7
        for skeleton, event in _skeletons(plan, sources, width, height, kerf, mirroring_allowed, skeleton_deadline):
            if time.monotonic() >= skeleton_deadline or trace['skeletons'] >= 160:
                break
            trace['compound_attempts'] += 1
            if skeleton is None:
                continue
            # One extra sheet is allowed only in the private exploration state.
            # Reject incomplete/forbidden skeletons before expensive reinsertion.
            if len(skeleton.get('sheets') or []) > len(plan['sheets'])+1:
                continue
            skeleton = _valid(skeleton, sources, width, height, kerf, machine_type,
                              metric_kwargs, deadline, mirroring_allowed)
            if skeleton is None:
                continue
            trace['skeletons'] += 1
            improved = offer(skeleton, already_validated=True)
            trace['exploration'].append(dict(event, improved=bool(improved),
                remnant_m2=skeleton['industrial_metrics']['largest_reusable_free_area_m2'],
                elapsed_sec=round(time.monotonic()-started,3)))
    # Use any remaining deadline to adapt around the best accepted skeleton.
    if time.monotonic() < deadline:
        regular_deadline = started+(deadline-started)*.85 if has_shapes else deadline
        later, late_trace = improve_fixed_board_layout(best, sources, width, height, kerf,
            deadline=regular_deadline, policy=replace(policy, max_attempts=96), machine_type=machine_type,
            mirroring_allowed=mirroring_allowed, metric_kwargs=metric_kwargs)
        for proposal in later[1:]:
            offer(proposal, already_validated=True)
        trace['tail'] = late_trace
    if has_shapes and time.monotonic() < deadline:
        from .rigid_layout_refinement import improve_rigid_contacts
        rigid, rigid_trace = improve_rigid_contacts(best, sources, width, height, kerf,
            deadline=deadline, machine_type=machine_type, mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs)
        offer(rigid, already_validated=True)
        trace['rigid'] = rigid_trace
    trace['attempts'] = (trace['partial_attempts']+trace['compound_attempts']
        +(trace.get('tail') or {}).get('attempts',0)+(trace.get('rigid') or {}).get('attempts',0))
    ranked = _ranked(portfolio)
    original = material_signature(plan)
    trace['elapsed_sec'] = round(time.monotonic()-started, 3)
    trace['stop'] = 'deadline' if time.monotonic() >= deadline else 'completed'
    alternatives = [p for p in ranked if material_signature(p) != original]
    nominees = []
    if alternatives:
        nominees.append(alternatives[0])
        proven = [p for p in alternatives if quality(p) is not None]
        if proven:
            nominees.extend((min(proven,key=lambda p:quality(p)[0]),
                             min(proven,key=lambda p:quality(p)[1])))
        nominees.extend(alternatives)
    unique = []
    signatures = set()
    for p in nominees:
        signature = material_signature(p)
        if signature not in signatures:
            signatures.add(signature)
            unique.append(p)
    return [deepcopy(plan), *unique[:4]], trace
