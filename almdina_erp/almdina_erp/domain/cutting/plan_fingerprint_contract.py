"""Frozen cutting-plan hash schemas. Version changes require new golden fixtures.

V2 had three deployed shapes (Git parents 13c3c89c / e8453978). Compatibility
must prove that fields omitted by an older shape add no machining requirements.
This module never hashes, reads storage, or changes an approved snapshot.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
)
from almdina_erp.almdina_erp.domain.orders.liner_specs import (
    door_liners_from_source,
)

FINGERPRINT_CONTRACT_VERSION = 3
FINGERPRINT_CONTRACT_KEY = 'input_fingerprint_contract'
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

# The only historical omissions supported by evidence from Git. No powerset search.
LEGACY_V2_SCHEMAS = (
    ('v2_oct22', ()),
    ('v2_pre_oct22', ('liner_specs_json',)),
    ('v2_pre_oct21', ('liner_specs_json', 'extra_double', 'extra_double_reference_sides')),
)


class PlanFingerprintContractError(ManufacturingRequirementsError):
    """The schema or its inputs cannot be verified; never silently drop fields."""


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
