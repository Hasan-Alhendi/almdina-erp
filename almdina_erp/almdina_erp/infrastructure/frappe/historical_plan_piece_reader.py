"""Frozen V2/V3 piece projection from the deployed October 2026 contracts.

Historical hashes must not call the evolving optimizer row adapter. Changing
this reader changes old plan meaning; add a new contract instead.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import require_cut_dimension_cm
from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import (
    PlanFingerprintContractError, freeze_geometry_piece,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import physical_cut_quantity
from almdina_erp.almdina_erp.domain.orders.piece_policy import canonical_glass_margin_mm


_ADDONS = (
    ("extra_liner", "liner"),
    ("extra_back_groove", "back_groove"),
    ("extra_recessed_handle_cutout", "recessed_handle"),
)

# These deployed V1–V3 normalization values are deliberately independent of
# future optimizer catalogs. New modes need a new hash contract, not a rewrite.
_MODE_IDS = frozenset('''auto auto_pro deep_search optimal maxrects guillotine shelf skyline
cp_sat_ortools mip_cbc scip highs gecode chuffed genetic simulated_annealing'''.split())
_ENGINE_MODES = {
    'Auto': 'auto', 'Auto Pro': 'auto_pro', 'Deep Search': 'deep_search',
    'Optimal Search': 'optimal', 'MaxRects Best Short Side': 'maxrects',
    'Guillotine Short Axis': 'guillotine', 'Shelf Horizontal': 'shelf',
    'Skyline Bottom Left': 'skyline',
}
_LEGACY_MODES = frozenset('''MaxRects Best Area|MaxRects Bottom Left|MaxRects Contact Point|
MaxRects Width|MaxRects Length|Shelf Vertical|Shelf First Fit|Shelf Next Fit|
Guillotine Long Axis|Guillotine Best Area Fit|Guillotine Best Short Side Fit|
Guillotine Best Long Side Fit|Skyline Best Fit'''.replace('\n', '').split('|'))


def historical_plan_settings(plan: Any) -> dict[str, Any]:
    """Frozen V1–V3 defaults, mode aliases, units, and numeric normalization."""
    def value(name: str) -> Any:
        return plan.get(name) if isinstance(plan, Mapping) else getattr(plan, name, None)

    mode = str(value('optimization_mode') or '').strip() or 'auto_pro'
    mode = _ENGINE_MODES.get(mode, mode)
    machine = str(value('machine_type') or '').strip() or 'Auto'
    if mode not in _MODE_IDS | _LEGACY_MODES or machine not in {'Auto', 'CNC Router', 'Panel Saw'}:
        raise PlanFingerprintContractError('unsupported_historical_plan_settings')
    numeric: dict[str, float] = {}
    for field, source, default, positive in (
        ('time_limit_sec', 'optimization_time_limit_sec', 10.0, True),
        ('kerf_mm', 'kerf_mm', 3.0, False),
        ('trim_margin_mm', 'trim_margin_mm', 5.0, False),
    ):
        raw = value(source)
        try:
            number = float(default if raw is None else raw)
        except (TypeError, ValueError) as exc:
            raise PlanFingerprintContractError('invalid_historical_plan_settings') from exc
        if not math.isfinite(number) or number < 0 or (positive and number == 0):
            raise PlanFingerprintContractError('invalid_historical_plan_settings')
        numeric[field] = number
    return {'optimization_mode': mode, 'machine_type': machine, **numeric}


def historical_geometry_piece(row: Any) -> dict[str, Any]:
    """The deployed representation, including inactive and empty defaults."""
    piece = {
        "piece_instance_id": str(getattr(row, "piece_instance_id", "") or "").strip(),
        "width_cm": require_cut_dimension_cm(getattr(row, "cut_width_cm", None), fieldname="cut_width_cm"),
        "length_cm": require_cut_dimension_cm(getattr(row, "cut_length_cm", None), fieldname="cut_length_cm"),
        "final_width_cm": flt(row.width_cm),
        "final_length_cm": flt(row.length_cm),
        "qty": physical_cut_quantity(cint(row.qty), full_door_double=bool(cint(getattr(row, "extra_full_door_double", 0)))),
        "allow_rotation": cint(row.allow_rotation),
        "edge_long_right": cint(row.edge_long_right),
        "edge_long_left": cint(row.edge_long_left),
        "edge_width_top": cint(row.edge_width_top),
        "edge_width_bottom": cint(row.edge_width_bottom),
        "edge_break": cint(getattr(row, "edge_break", 0)),
        "edge_break_only": cint(getattr(row, "edge_break_only", 0)),
        "piece_type": row.piece_type or "Regular",
        "extra_double": cint(getattr(row, "extra_double", 0)),
        "extra_double_reference_sides": str(getattr(row, "extra_double_reference_sides", "") or ""),
        "clipped_corner_position": row.clipped_corner_position or "",
        "clipped_corner_width_cm": flt(row.clipped_corner_width_cm),
        "clipped_corner_length_cm": flt(row.clipped_corner_length_cm),
        "special_shape_geometry_json": getattr(row, "special_shape_geometry_json", "") or "",
        "edge_long_thickness_mm": flt(row.edge_long_thickness_mm),
        "edge_width_thickness_mm": flt(row.edge_width_thickness_mm),
        "liner_specs_json": getattr(row, "liner_specs_json", "") or "",
    }
    margin = canonical_glass_margin_mm(getattr(row, "glass_margin_mm", None), row.piece_type or "Regular")
    if margin is not None:
        piece["glass_margin_mm"] = margin
    for enabled, prefix in _ADDONS:
        side = str(getattr(row, f"{prefix}_reference_side", "") or "")
        width = flt(getattr(row, f"{prefix}_width_cm", 0))
        if cint(getattr(row, enabled, 0)) and side and width > 0:
            piece[enabled] = 1
            piece[f"{prefix}_reference_side"] = side
            for suffix in ("offset_cm", "width_cm", "start_cm", "length_cm"):
                piece[f"{prefix}_{suffix}"] = flt(getattr(row, f"{prefix}_{suffix}", 0))
    return freeze_geometry_piece(piece)


def historical_v1_piece(row: Any) -> dict[str, Any]:
    """V1 additionally hashed commercial metadata; do not broaden its use."""
    return historical_geometry_piece(row) | {
        "edge_type": row.edge_type or "",
        "edge_rate_usd": flt(row.edge_rate_usd),
        "edge_cost_usd": flt(row.edge_cost_usd),
        "notes": row.notes or "",
        "edge_long_right_type_override": str(getattr(row, "edge_long_right_type_override", "") or ""),
        "edge_long_left_type_override": str(getattr(row, "edge_long_left_type_override", "") or ""),
        "edge_width_top_type_override": str(getattr(row, "edge_width_top_type_override", "") or ""),
        "edge_width_bottom_type_override": str(getattr(row, "edge_width_bottom_type_override", "") or ""),
        "edge_long_type": str(row.edge_long_type or ""),
        "edge_width_type": str(row.edge_width_type or ""),
        "edge_long_rate_usd": flt(row.edge_long_rate_usd),
        "edge_width_rate_usd": flt(row.edge_width_rate_usd),
        "edge_long_cost_usd": flt(row.edge_long_cost_usd),
        "edge_width_cost_usd": flt(row.edge_width_cost_usd),
        "cut_size_label": str(getattr(row, "cut_size_label", "") or ""),
    }
