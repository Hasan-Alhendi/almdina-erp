"""Frozen cutting-plan hash schemas. Version changes require new golden fixtures.

V2 had three deployed shapes (Git parents 13c3c89c / e8453978). Compatibility
must prove that fields omitted by an older shape add no machining requirements.
This module never hashes, reads storage, or changes an approved snapshot.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
)
from almdina_erp.almdina_erp.domain.orders.liner_specs import (
    door_liners_from_source,
)

FINGERPRINT_CONTRACT_VERSION = 3
FINGERPRINT_CONTRACT_KEY = 'input_fingerprint_contract'
MANUFACTURING_BASELINE_VERSION = 4
MANUFACTURING_BASELINE_KEY = 'manufacturing_baseline'
_V4_MACHINE_TYPES = frozenset({'Auto', 'CNC Router', 'Panel Saw'})
# Explicitly frozen; never derive this set from a mutable add-on registry.
GEOMETRY_PIECE_KEYS = frozenset('''
piece_instance_id width_cm length_cm final_width_cm final_length_cm qty
allow_rotation edge_long_right edge_long_left edge_width_top edge_width_bottom
edge_break edge_break_only piece_type clipped_corner_position
clipped_corner_width_cm clipped_corner_length_cm special_shape_geometry_json
glass_margin_mm extra_double extra_double_reference_sides
edge_long_thickness_mm edge_width_thickness_mm liner_specs_json
extra_liner liner_reference_side liner_offset_cm liner_width_cm liner_start_cm liner_length_cm
extra_back_groove back_groove_reference_side back_groove_offset_cm back_groove_width_cm back_groove_start_cm back_groove_length_cm
extra_recessed_handle_cutout recessed_handle_reference_side recessed_handle_offset_cm recessed_handle_width_cm recessed_handle_start_cm recessed_handle_length_cm
'''.split())

# Required keys and primitive types are part of V3, including inactive defaults.
# Do not infer these from the mutable row adapter or add-on registry.
_REQUIRED_PIECE_KEYS = frozenset("""
piece_instance_id width_cm length_cm final_width_cm final_length_cm qty
allow_rotation edge_long_right edge_long_left edge_width_top edge_width_bottom
edge_break edge_break_only piece_type extra_double extra_double_reference_sides
clipped_corner_position clipped_corner_width_cm clipped_corner_length_cm
special_shape_geometry_json liner_specs_json edge_long_thickness_mm edge_width_thickness_mm
""".split())
_INTEGER_PIECE_KEYS = frozenset("""
qty allow_rotation edge_long_right edge_long_left edge_width_top edge_width_bottom
edge_break edge_break_only extra_double extra_liner extra_back_groove extra_recessed_handle_cutout
""".split())
_STRING_PIECE_KEYS = frozenset("""
piece_instance_id piece_type extra_double_reference_sides clipped_corner_position
special_shape_geometry_json liner_specs_json liner_reference_side
back_groove_reference_side recessed_handle_reference_side
""".split())
_MACHINING_GROUPS = tuple(
    frozenset((enabled, *(f"{prefix}_{suffix}" for suffix in (
        "reference_side", "offset_cm", "width_cm", "start_cm", "length_cm",
    ))))
    for enabled, prefix in (
        ("extra_liner", "liner"), ("extra_back_groove", "back_groove"),
        ("extra_recessed_handle_cutout", "recessed_handle"),
    )
)

# The only historical omissions supported by evidence from Git. No powerset search.
LEGACY_V2_SCHEMAS = (
    ('v2_oct22', ()),
    ('v2_pre_oct22', ('liner_specs_json',)),
    ('v2_pre_oct21', ('liner_specs_json', 'extra_double', 'extra_double_reference_sides')),
)


class PlanFingerprintContractError(ManufacturingRequirementsError):
    """The schema or its inputs cannot be verified; never silently drop fields."""


def freeze_v4_execution_settings(*, machine_type: Any, kerf_mm: Any,
                                 trim_margin_mm: Any) -> dict[str, Any]:
    """Historic physical settings, independent of evolving optimizer catalogs."""
    machine = str(machine_type or 'Auto').strip()
    if machine not in _V4_MACHINE_TYPES:
        raise PlanFingerprintContractError('unknown_v4_machine_type')
    numeric: dict[str, float] = {}
    for field, value, default in (('kerf_mm', kerf_mm, 3.0),
                                  ('trim_margin_mm', trim_margin_mm, 5.0)):
        try:
            number = float(default if value is None else value)
        except (TypeError, ValueError) as exc:
            raise PlanFingerprintContractError('invalid_v4_execution_setting') from exc
        if not math.isfinite(number) or number < 0:
            raise PlanFingerprintContractError('invalid_v4_execution_setting')
        numeric[field] = number
    return {'machine_type': machine, **numeric}


def validate_v4_baseline(value: Any) -> None:
    """Reject an altered schema before interpreting it as changed requirements."""
    if not isinstance(value, dict) or set(value) != {'version', 'order', 'board', 'execution_settings', 'pieces'}:
        raise PlanFingerprintContractError('invalid_v4_baseline_shape')
    if type(value['version']) is not int or value['version'] != MANUFACTURING_BASELINE_VERSION:
        raise PlanFingerprintContractError('invalid_v4_baseline_version')
    if type(value['order']) is not str or not value['order']:
        raise PlanFingerprintContractError('invalid_v4_baseline_order')
    board = value['board']
    if (not isinstance(board, dict) or set(board) != {'width_mm', 'length_mm'}
            or any(type(v) is not float or not math.isfinite(v) or v <= 0 for v in board.values())):
        raise PlanFingerprintContractError('invalid_v4_baseline_board')
    settings = value['execution_settings']
    if (not isinstance(settings, dict)
            or set(settings) != {'machine_type', 'kerf_mm', 'trim_margin_mm'}
            or any(type(settings[k]) is not float for k in ('kerf_mm', 'trim_margin_mm'))
            or settings != freeze_v4_execution_settings(**settings)):
        raise PlanFingerprintContractError('invalid_v4_baseline_settings')
    pieces = value['pieces']
    if not isinstance(pieces, list) or not pieces:
        raise PlanFingerprintContractError('invalid_v4_baseline_pieces')
    for piece in pieces:
        if not isinstance(piece, dict):
            raise PlanFingerprintContractError('invalid_v4_baseline_piece')
        freeze_geometry_piece(piece)


@dataclass(frozen=True)
class FingerprintCompatibility:
    state: str
    expected_fingerprint: str
    contract: str = ''
    reason: str = ''

    @property
    def compatible(self) -> bool:
        return self.state in {'MATCH', 'COMPATIBLE'}


def freeze_geometry_piece(piece: Mapping[str, Any]) -> dict[str, Any]:
    if set(piece) - GEOMETRY_PIECE_KEYS:
        raise PlanFingerprintContractError('unknown_fingerprint_piece_fields')
    if _REQUIRED_PIECE_KEYS - set(piece):
        raise PlanFingerprintContractError('missing_fingerprint_piece_fields')
    if piece['piece_type'] == 'Glass' and 'glass_margin_mm' not in piece:
        raise PlanFingerprintContractError('missing_fingerprint_glass_margin')
    for group in _MACHINING_GROUPS:
        present = group.intersection(piece)
        if present and present != group:
            raise PlanFingerprintContractError('incomplete_fingerprint_machining_fields')
    for key, value in piece.items():
        expected = int if key in _INTEGER_PIECE_KEYS else str if key in _STRING_PIECE_KEYS else float
        if type(value) is not expected:
            raise PlanFingerprintContractError('noncanonical_fingerprint_piece_type')
    return dict(piece)


def legacy_omission_is_safe(pieces: list[dict[str, Any]], omitted: tuple[str, ...]) -> bool:
    for piece in pieces:
        if 'liner_specs_json' in omitted:
            # A historical scalar hash is evidence for that exact scalar toolpath.
            # JSON is safe to omit only if it expresses exactly the same toolpath.
            current = door_liners_from_source(piece)
            scalar = door_liners_from_source({**piece, 'liner_specs_json': ''})
            if current.width_cm != scalar.width_cm or current.enabled != scalar.enabled:
                return False
            def paths(liners):
                return tuple((p.side, p.offset_cm, p.start_cm, p.length_cm) for p in liners)
            if paths(current.liners) != paths(scalar.liners):
                return False
        if 'extra_double' in omitted and (
            piece.get('extra_double') or str(piece.get('extra_double_reference_sides') or '').strip()
        ):
            return False
    return True
