"""Temporary geometry identity for completed optimizer alternatives (no storage)."""
from __future__ import annotations
import hashlib
import json
from typing import Any

_GEOMETRY_FIELDS = frozenset('''id piece_instance_id source_piece_no copy_no x y w h
width_cm length_cm piece_type rotated mirrored placement_mirrored
corner_rotation_quarter_turns placement_rotation_deg placement_void_angle_deg
placement_outline_cm glass_host_piece_id special_shape_geometry_json geometry
clipped_corner_position clipped_corner_width_cm clipped_corner_length_cm
edge_long_right edge_long_left edge_width_top edge_width_bottom edge_break edge_break_only
edge_long_thickness_mm edge_width_thickness_mm'''.split())
_PREFIXES = ('glass_', 'liner_', 'back_groove_', 'recessed_handle_', 'extra_')


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
            for key in ('placement_outline_cm', 'glass_hole_local_mm'):
                if geometry.get(key):
                    geometry[key] = _ring(geometry[key])
            for key in ('rotated', 'mirrored', 'placement_mirrored'):
                geometry[key] = bool(geometry.get(key))
            for key in ('corner_rotation_quarter_turns', 'placement_rotation_deg'):
                geometry[key] = geometry.get(key) or 0
            pieces.append(json.dumps(geometry, sort_keys=True))
        sheets.append(json.dumps(_canonical(dict(w=sheet.get('w'),h=sheet.get('h'),trim_x=sheet.get('applied_trim_width_cm',0),trim_y=sheet.get('applied_trim_length_cm',0),pieces=sorted(pieces))),sort_keys=True))
    payload = json.dumps(dict(sheets=sorted(sheets),unplaced=sorted(str(p.get('id')) for p in plan.get('unplaced') or [])))
    return hashlib.sha256(payload.encode()).hexdigest()


def supports_manufacturing_rotation(plan):
    """The existing strict DXF identity contract only proves quarter turns."""
    return all(abs(float(p.get('placement_rotation_deg') or 0)/90
                   -round(float(p.get('placement_rotation_deg') or 0)/90))<=1e-6
               for sheet in plan.get('sheets') or [] for p in sheet.get('pieces') or [])
