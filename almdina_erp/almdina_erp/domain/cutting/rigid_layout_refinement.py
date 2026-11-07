"""ALNS contact proposals for complete corner nests, before final projection.

This is not Final Alignment: an entire validated shape/guest group may move.
Orientation, relative offsets, instances and the existing manufacturing gates
stay unchanged. Event coordinates come from real contours, never a grid scan.
"""
from copy import deepcopy
import time

from .cut_line_quality import plan_cut_line_quality, final_system_sort_keys
from .glass_opening_nesting import material_outline_cm
from .nesting_consolidation import extract_placement_groups, STANDALONE
from .same_count_layout_search import _cache, _valid, largest_remnant_region
from .shape_aware_nesting import _translate_pieces, _clears, _inside_board


def improve_rigid_contacts(plan, sources, width, height, kerf, *, deadline,
                           machine_type, mirroring_allowed, metric_kwargs):
    trace = dict(attempts=0, improvements=0)
    best = deepcopy(plan)
    if (machine_type not in {'Auto', 'CNC Router'} or plan.get('unplaced')
            or any((s.get('resource_kind') or 'FULL_BOARD') != 'FULL_BOARD' for s in plan.get('sheets') or [])
            or any((p.get('resource_kind') or 'FULL_BOARD') != 'FULL_BOARD' for p in sources)):
        return best, trace
    for _ in range(3):
        changed = False
        region = largest_remnant_region(best, machine_type=machine_type, metric_kwargs=metric_kwargs)
        groups = extract_placement_groups(best)
        for group in [g for g in groups if g.kind != STANDALONE][:8]:
            if time.monotonic() >= deadline or trace['attempts'] >= 192:
                return best, trace
            index = next((i for i, s in enumerate(best['sheets'])
                          if s.get('sheet_no') == group.sheet_no), None)
            if index is None or (region is not None and index == region.sheet_index):
                continue
            if any(p.get('piece_type') not in {'Regular', 'L-Shaped Corner', 'Clipped Corner'}
                   or p.get('extra_liner') or p.get('extra_back_groove')
                   or p.get('extra_recessed_handle_cutout') or p.get('geometry')
                   or p.get('special_shape_geometry_json') or p.get('placement_outline_cm')
                   for p in group.pieces):
                continue
            members = set(group.piece_ids)
            sheet = best['sheets'][index]
            others = [p for p in sheet['pieces'] if p['id'] not in members]
            moving = [p for p in sheet['pieces'] if p['id'] in members]
            fixed_outlines = [material_outline_cm(p) for p in others]
            body_outlines = [material_outline_cm(p) for p in moving]
            if not others or any(p is None for p in fixed_outlines+body_outlines):
                continue
            moves = []
            for axis in (0, 1):
                own = {v[axis] for ring in body_outlines for v in ring}
                fixed = {v[axis] for ring in fixed_outlines for v in ring}
                deltas = {round(b+gap-a, 7) for a in own for b in fixed for gap in (-kerf, 0, kerf)}
                deltas.discard(0.0)
                for delta in sorted(deltas, key=lambda d: (abs(d), d))[:24]:
                    moves.append((delta, 0) if axis == 0 else (0, delta))
            before = plan_cut_line_quality(best, kerf)
            if before is None:
                continue
            for dx, dy in moves:
                if time.monotonic() >= deadline or trace['attempts'] >= 192:
                    return best, trace
                trace['attempts'] += 1
                translated = [[(x+dx, y+dy) for x, y in ring] for ring in body_outlines]
                if not all(_inside_board(ring, width, height) and _clears(ring, fixed_outlines, kerf)
                           for ring in translated):
                    continue
                trial = deepcopy(best)
                trial['sheets'][index]['pieces'] = others + _translate_pieces(moving, dx, dy)
                _cache(trial['sheets'][index], kerf)
                after = plan_cut_line_quality(trial, kerf)
                if after is None or after[0] > before[0]+1e-5 or after[1] > before[1]:
                    continue
                candidate = _valid(trial, sources, width, height, kerf, machine_type,
                                   metric_kwargs, deadline, mirroring_allowed)
                if candidate is None:
                    continue
                keys = final_system_sort_keys([best, candidate])
                if keys[1] < keys[0]:
                    best = candidate
                    trace['improvements'] += 1
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    return best, trace
