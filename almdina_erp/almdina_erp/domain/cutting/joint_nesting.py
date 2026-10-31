"""Bounded Glass/shape reassignment before rigid nest decisions are frozen.

Every branch is a complete copied plan. Existing shape/opening geometry creates
placements; consolidation still moves proven nests rigidly. No coordinates from
independent plans are combined and no manufacturing validator is relaxed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import time
from typing import Any

from .evaluation import placement_permission_errors, validate_plan
from .glass_opening_nesting import (
    MAX_NESTING_DEPTH, _declared_host_id, _openings, _place_in_usable, guest_is_eligible,
)
from .nesting_consolidation import best_rigid_translation, consolidate_nested_boards
from .plan_portfolio import geometry_signature, manufacturing_export_rejection
from .shape_aware_nesting import _cluster_sheet, _place_in_voids, _translate_pieces

_CORNERS = frozenset({'L-Shaped Corner', 'Clipped Corner'})
_BEAM_WIDTH = 4
_MAX_COMPLETED = 12
_REASSIGNMENT_DEPTH = 2


def has_joint_sources(pieces: list[dict[str, Any]], machine_type: str) -> bool:
    """Cheap gate: actual opening/void compatibility is proved inside the budget."""
    return machine_type != 'Panel Saw' and any(p.get('piece_type') in _CORNERS for p in pieces) and any(
        p.get('piece_type') == 'Glass' and float(p.get('glass_margin_mm') or 0) > 0 for p in pieces)


def _shape_ids(plan):
    diagnostic = plan.get('shape_nesting_diagnostics') or {}
    return {int(i) for group in diagnostic.get('formation_ids') or [] for i in group} | {
        int(i) for i in diagnostic.get('void_guests') or []}


def _glass_ids(plan):
    return {int(i) for sheet in plan.get('sheets') or [] for p in sheet.get('pieces') or []
            if p.get('glass_host_piece_id') not in (None, '') for i in (p['id'], p['glass_host_piece_id'])}


def complete_shape_candidate(candidate, pieces, width, height, kerf, *, machine_type,
                             mirroring_allowed, deadline, metric_kwargs, excluded=frozenset()):
    """Complete a proven shape seed without repeating formation enumeration."""
    from .glass_opening_nesting import nest_glass_openings
    from .plan_search import improve_plan_search
    if time.monotonic() >= deadline:
        return candidate
    machining = {int(p['id']) for p in pieces if any(p.get(k) for k in (
        'extra_liner', 'extra_back_groove', 'extra_recessed_handle_cutout'))}
    protected = _shape_ids(candidate) | _glass_ids(candidate) | set(excluded) | machining
    nested = nest_glass_openings(deepcopy(candidate), pieces, width, height, kerf,
        machine_type=machine_type, time_limit_sec=max(0,deadline-time.monotonic()),
        guest_exclusions=frozenset(protected), preserve_existing=True, **metric_kwargs)
    nested = consolidate_nested_boards(nested,pieces,width,height,kerf,machine_type=machine_type,
        mirroring_allowed=mirroring_allowed,
        deadline=min(deadline,time.monotonic()+max(0,deadline-time.monotonic())*.5))
    return improve_plan_search(nested,pieces,width,height,kerf,machine_type=machine_type,
        mirroring_allowed=mirroring_allowed,time_limit_sec=max(0,deadline-time.monotonic())*.2,
        deadline_monotonic=min(deadline,time.monotonic()+max(0,deadline-time.monotonic())*.2),**metric_kwargs)


def _release_guest(plan, piece_id, width, height, kerf, deadline):
    """Detach just one selected relation and keep its descendants as a rigid unit."""
    copied = deepcopy(plan)
    located = {int(p['id']): p for s in copied['sheets'] for p in s['pieces']}
    if piece_id not in located:
        return None
    released = {piece_id}
    for _ in range(MAX_NESTING_DEPTH):
        released.update(int(p['id']) for p in located.values()
                        if _declared_host_id(p) in released)
    body = [located[i] for i in sorted(released)]
    located[piece_id].pop('glass_host_piece_id', None)
    for sheet in copied['sheets']:
        sheet['pieces'] = [p for p in sheet['pieces'] if int(p['id']) not in released]
    copied['sheets'] = [s for s in copied['sheets'] if s['pieces']]
    sheet = dict(sheet_no=max((s['sheet_no'] for s in copied['sheets']), default=0)+1,
                 w=width, h=height, pieces=[])
    shift = best_rigid_translation(sheet, body, kerf, width, height, deadline=deadline)
    if shift is None:
        return None
    sheet['pieces'] = _translate_pieces(body, shift[0], shift[1])
    copied['sheets'].append(sheet)
    diagnostic = copied.get('shape_nesting_diagnostics') or {}
    if diagnostic:
        diagnostic['formation_ids'] = [[i for i in group if int(i) not in released]
                                       for group in diagnostic.get('formation_ids') or []]
        diagnostic['void_guests'] = [i for i in diagnostic.get('void_guests') or [] if int(i) not in released]
    return copied


def joint_nesting_candidates(baseline, incumbent, pieces, width, height, kerf, *,
                             machine_type, mirroring_allowed, deadline, metric_kwargs):
    """Return up to four proven finals and small diagnostics within one deadline."""
    from . import shape_aware_nesting as shape
    from .optimizer import enrich_plan_metrics

    diagnostics = dict(joint_candidates_generated=0, joint_candidates_valid=0,
                       guest_reassignments=0, rejection_reasons={})
    rejected = Counter()
    if not has_joint_sources(pieces, machine_type) or time.monotonic() >= deadline:
        return [], diagnostics
    openings = _openings(baseline, kerf)
    if not openings:
        return [], diagnostics
    partitions = _cluster_sheet(pieces, width, height, kerf, mirroring_allowed=mirroring_allowed,
                                deadline=deadline)
    blocks = next((p for p in partitions if any(b.get('voids') for b in p)), [])
    if not blocks:
        return [], diagnostics
    hosts = {int(p['id']) for b in blocks for p in b['pieces']}
    glass_fits, shape_fits = set(), set()
    for piece in pieces:
        if time.monotonic() >= deadline:
            return [], diagnostics
        key = int(piece['id'])
        if guest_is_eligible(piece) and any(o['host_id'] != key and _place_in_usable(
                piece, o['usable'], [], kerf) is not None for o in openings):
            glass_fits.add(key)
        if key not in hosts and _place_in_voids(piece, deepcopy(blocks), kerf, width, height,
                mirroring_allowed=mirroring_allowed, quarter_turns_only=True) is not None:
            shape_fits.add(key)
    if not glass_fits or not shape_fits:
        return [], diagnostics

    beam, seen = [], set()
    def offer(candidate):
        diagnostics['joint_candidates_generated'] += 1
        if time.monotonic() >= deadline:
            rejected['deadline'] += 1
            return
        export_rejection = manufacturing_export_rejection(candidate)
        if export_rejection:
            rejected[export_rejection] += 1
            return
        errors = validate_plan(candidate, pieces, width, height, kerf_cm=kerf, deadline_monotonic=deadline)
        if errors:
            rejected['geometry_or_identity'] += 1
            return
        if placement_permission_errors(candidate, pieces, mirroring_allowed=mirroring_allowed):
            rejected['permissions'] += 1
            return
        candidate = enrich_plan_metrics(candidate, str(candidate.get('method_key') or ''), machine_type, **metric_kwargs)
        signature = geometry_signature(candidate)
        if signature in seen:
            rejected['duplicate'] += 1
            return
        seen.add(signature)
        diagnostics['joint_candidates_valid'] += 1
        beam.append(candidate)
        beam.sort(key=lambda p: tuple(p['industrial_rank']))
        del beam[_BEAM_WIDTH:]

    def complete(candidate, excluded=frozenset()):
        if time.monotonic() >= deadline or diagnostics['joint_candidates_generated'] >= _MAX_COMPLETED:
            return
        nested = complete_shape_candidate(candidate,pieces,width,height,kerf,machine_type=machine_type,
            mirroring_allowed=mirroring_allowed,deadline=deadline,metric_kwargs=metric_kwargs,excluded=excluded)
        offer(nested)

    def shape_then_glass(source, excluded=frozenset(), glass_excluded=frozenset()):
        if time.monotonic() >= deadline or diagnostics['joint_candidates_generated'] >= _MAX_COMPLETED:
            return
        formations = []
        def collect(candidate):
            if len(formations) < _BEAM_WIDTH:
                formations.append(candidate)
        shape.apply_shape_aware_nesting(deepcopy(source), pieces, width, height, kerf,
            machine_type=machine_type, mirroring_allowed=mirroring_allowed,
            time_limit_sec=max(0, deadline-time.monotonic()), formation_alternatives=True,
            guest_exclusions=excluded, quarter_turns_only=True,
            candidate_callback=collect, **metric_kwargs)
        for candidate in formations:
            complete(candidate, glass_excluded)

    # Path A has already completed in Smart. Path B keeps every proven formation
    # until the downstream Glass allocation and rigid repack have been compared.
    shape_then_glass(baseline)
    parents = [incumbent, *beam[:_BEAM_WIDTH-1]]
    for _depth in range(_REASSIGNMENT_DEPTH):
        next_parents = []
        for parent in parents[:_BEAM_WIDTH]:
            if time.monotonic() >= deadline or diagnostics['joint_candidates_generated'] >= _MAX_COMPLETED:
                break
            placed = [p for s in parent['sheets'] for p in s['pieces']]
            # A corner consumed by Glass can prevent a whole formation. A guest
            # fitting both opportunity types may need to move the opposite way.
            selected = sorted({int(p['id']) for p in placed if p.get('glass_host_piece_id')
                               and (int(p['id']) in shape_fits or p.get('piece_type') in _CORNERS)}
                              | (_shape_ids(parent) & shape_fits & glass_fits))[:2]
            for guest_id in selected:
                detached = _release_guest(parent, guest_id, width, height, kerf, deadline)
                if detached is None or validate_plan(detached, pieces, width, height, kerf_cm=kerf,
                                                     deadline_monotonic=deadline):
                    rejected['release'] += 1
                    continue
                diagnostics['guest_reassignments'] += 1
                # A released shape guest is reserved for Glass on this branch;
                # a released corner remains available to form an L/clip block.
                to_glass = guest_id in set((parent.get('shape_nesting_diagnostics') or {}).get('void_guests') or [])
                excluded = frozenset({guest_id}) if to_glass else frozenset()
                glass_excluded = frozenset() if to_glass else frozenset({guest_id})
                shape_then_glass(detached, excluded, glass_excluded)
                next_parents.extend(beam[:2])
        parents = next_parents[:_BEAM_WIDTH]
        if not parents:
            break
    diagnostics['rejection_reasons'] = dict(rejected)
    return beam, diagnostics
