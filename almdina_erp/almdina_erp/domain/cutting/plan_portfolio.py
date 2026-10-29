"""Temporary geometry identity for completed optimizer alternatives (no storage)."""
from __future__ import annotations
import hashlib
import json
from typing import Any

_GEOMETRY_FIELDS = frozenset('''id piece_instance_id source_piece_no copy_no x y w h
width_cm length_cm original_w original_h piece_type rotated mirrored corner_mirrored placement_mirrored
corner_rotation_quarter_turns placement_rotation_deg placement_void_angle_deg
placement_outline_cm glass_host_piece_id special_shape_geometry_json geometry
clipped_corner_position clipped_corner_width_cm clipped_corner_length_cm
edge_long_right edge_long_left edge_width_top edge_width_bottom edge_break edge_break_only
edge_long_thickness_mm edge_width_thickness_mm'''.split())
_PREFIXES = ('glass_', 'liner_', 'back_groove_', 'recessed_handle_', 'extra_')


def nesting_coverage(plan: dict[str, Any]) -> frozenset[str]:
    """Actual opening guests/interlocks, independent of engine names or scores."""
    pieces = [p for s in plan.get('sheets') or [] for p in s.get('pieces') or []]
    coverage = {'Glass'} if any(p.get('glass_host_piece_id') for p in pieces) else set()
    diagnostic = plan.get('shape_nesting_diagnostics') or {}
    formed = {int(i) for ids in diagnostic.get('formation_ids') or [] for i in ids}
    guests = bool(diagnostic.get('void_guests'))
    for sheet in plan.get('sheets') or []:
        placed=sheet.get('pieces') or []
        located={int(p['id']):p for p in placed}
        corners = [p for p in placed if p.get('piece_type') in
                   {'L-Shaped Corner', 'Clipped Corner'}]
        for p in corners:
            ancestors=set()
            host=p.get('glass_host_piece_id')
            while host not in (None,'') and int(host) in located and int(host) not in ancestors:
                ancestors.add(int(host))
                host=located[int(host)].get('glass_host_piece_id')
            interlock = any(p['id'] != q['id'] and
                int(q['id']) not in ancestors and
                min(p['x']+p['w'],q['x']+q['w'])-max(p['x'],q['x']) > 1e-6 and
                min(p['y']+p['h'],q['y']+q['h'])-max(p['y'],q['y']) > 1e-6 for q in placed)
            if interlock or (guests and int(p['id']) in formed):
                coverage.add(str(p['piece_type']))
    if 'Glass' in coverage and len(coverage)>1:
        coverage.add('Joint')
    return frozenset(coverage)


def retain_diverse_finals(candidates: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Industrial winner first; preserve useful coverage on the same board count.

    A lower-ranked alternative can trade off offcut/complexity explicitly in the
    gallery, but can never replace the winner or reserve an extra-board slot.
    """
    ranked = sorted(candidates,key=lambda p:tuple(p['industrial_rank']))
    if len(ranked)<=limit:
        return ranked
    selected=[ranked[0]]
    boards=len(ranked[0].get('sheets') or [])
    for kind in ('Joint','L-Shaped Corner','Clipped Corner','Glass'):
        if any(kind in nesting_coverage(p) for p in selected):
            continue
        candidate=next((p for p in ranked if len(p.get('sheets') or [])==boards and kind in nesting_coverage(p)),None)
        if candidate is not None and all(candidate is not p for p in selected):
            selected.append(candidate)
    for candidate in ranked:
        if len(selected)>=limit:
            break
        if all(candidate is not p for p in selected):
            selected.append(candidate)
    return sorted(selected[:limit],key=lambda p:tuple(p['industrial_rank']))


def _canonical(value: Any) -> Any:
    if isinstance(value, float):
        number = round(value, 9)
        return int(number) if number.is_integer() else number
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def _ring(value):
    points = [tuple(_canonical(p)) for p in value]
    if points and points[0] == points[-1]:
        points.pop()
    if not points:
        return []
    return min(tuple(ring[i:]+ring[:i]) for ring in (points,list(reversed(points))) for i in range(len(points)))


def geometry_signature(plan: dict[str, Any]) -> str:
    sheets = []
    for sheet in plan.get('sheets') or []:
        pieces = []
        for piece in sheet.get('pieces') or []:
            geometry = {k: _canonical(v) for k,v in piece.items()
                        if (k in _GEOMETRY_FIELDS or k.startswith(_PREFIXES))
                        and not k.endswith('_usd') and not k.endswith('_label')}
            for key in ('special_shape_geometry_json', 'liner_specs_json'):
                if geometry.get(key):
                    try:
                        geometry[key] = _canonical(json.loads(geometry[key]))
                    except (TypeError, ValueError):
                        pass  # Malformed geometry remains distinct and fails validation.
            special = geometry.get('special_shape_geometry_json')
            if isinstance(special, dict) and special.get('points'):
                special['points'] = _ring(special['points'])
            for key in ('placement_outline_cm', 'glass_hole_local_mm'):
                if geometry.get(key):
                    geometry[key] = _ring(geometry[key])
            for key in ('rotated', 'mirrored', 'corner_mirrored', 'placement_mirrored'):
                geometry[key] = bool(geometry.get(key))
            geometry['corner_rotation_quarter_turns'] = (geometry.get('corner_rotation_quarter_turns') or 0) % 4
            geometry['placement_rotation_deg'] = (geometry.get('placement_rotation_deg') or 0) % 360
            pieces.append(json.dumps(geometry, sort_keys=True))
        sheets.append(json.dumps(_canonical(dict(w=sheet.get('w'),h=sheet.get('h'),trim_x=sheet.get('applied_trim_width_cm',0),trim_y=sheet.get('applied_trim_length_cm',0),pieces=sorted(pieces))),sort_keys=True))
    payload = json.dumps(dict(sheets=sorted(sheets),unplaced=sorted(str(p.get('id')) for p in plan.get('unplaced') or [])))
    return hashlib.sha256(payload.encode()).hexdigest()


def supports_manufacturing_rotation(plan):
    """The existing strict DXF identity contract only proves quarter turns."""
    return all(abs(float(p.get('placement_rotation_deg') or 0)/90
                   -round(float(p.get('placement_rotation_deg') or 0)/90))<=1e-6
               for sheet in plan.get('sheets') or [] for p in sheet.get('pieces') or [])


def manufacturing_export_rejection(plan):
    """Known unsupported identity paths; validators/export contracts stay intact."""
    if not supports_manufacturing_rotation(plan):
        return 'unsupported_rotation'
    # Strict overlay ownership currently sees both the Glass outer contour and
    # its machined guest as owners (OVERLAY_SPANS_HOSTS). Do not certify it.
    if any(p.get('glass_host_piece_id') not in (None, '') and any(
            p.get(key) for key in ('extra_liner', 'extra_back_groove', 'extra_recessed_handle_cutout'))
            for s in plan.get('sheets') or [] for p in s.get('pieces') or []):
        return 'glass_guest_machining_identity'
    from .corner_contour_rotation import match_corner_contour
    from .glass_opening_nesting import material_outline_cm
    for sheet in plan.get('sheets') or []:
        for p in sheet.get('pieces') or []:
            if p.get('piece_type') not in {'L-Shaped Corner','Clipped Corner'} or not any(
                    p.get(key) for key in ('extra_liner','extra_back_groove','extra_recessed_handle_cutout')):
                continue
            outline=material_outline_cm(p)
            if outline is None:
                return 'corner_machining_unknown_outline'
            # Import binds corners with selected bands before checking machining.
            # Equal tokens mean the same physical band; the token spelling is
            # irrelevant to the existing contour matcher. Preserve that proof.
            sides={'top':('edge_width_top','width'),'bottom':('edge_width_bottom','width'),
                   'left':('edge_long_left','long'),'right':('edge_long_right','long')}
            banded=any(p.get(field) for field,_ in sides.values()) or p.get('edge_break') or p.get('edge_break_only')
            tokens=None
            if banded:
                tokens={role:json.dumps([True,p.get(field+'_type_override') or p.get('edge_'+axis+'_type')
                    or p.get('edge_type') or '',float(p.get('edge_'+axis+'_thickness_mm') or 0)])
                    if p.get(field) else '0' for role,(field,axis) in sides.items()}
                notch='break' if p.get('edge_break') else ('break-only' if p.get('edge_break_only')
                    and p['piece_type']=='Clipped Corner' else 'open')
                tokens.update(inner_horizontal=notch,inner_vertical=notch,chord=notch)
            match=match_corner_contour([(x*10,y*10) for x,y in outline],piece_type=p['piece_type'],
                position=p.get('clipped_corner_position') or '',width_cm=float(p.get('original_w') or p.get('width_cm') or 0),
                length_cm=float(p.get('original_h') or p.get('length_cm') or 0),
                cut_width_cm=float(p.get('clipped_corner_width_cm') or 0),
                cut_length_cm=float(p.get('clipped_corner_length_cm') or 0),edge_bands=tokens)
            if match.quarter_turns is None:
                return 'corner_machining_orientation_'+match.reason
            if banded:
                from .placement_orientation import resolve_placement_orientation
                actual=resolve_placement_orientation(p)
                if (actual.quarter_turns,actual.mirrored)!=(match.quarter_turns,match.mirrored):
                    return 'corner_machining_semantic_orientation'
    return ''
