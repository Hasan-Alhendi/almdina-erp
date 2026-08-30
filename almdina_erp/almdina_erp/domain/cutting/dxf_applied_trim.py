from __future__ import annotations

from copy import deepcopy
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AdaptiveTrimDecision,
    AppliedTrim,
    PlanQuality,
    TRIM_PRECISION_CM,
    resolve_adaptive_trim,
)


class DxfAppliedTrimError(ValueError):
    pass


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _piece_fits(piece: dict[str, Any], *, full_w: float, full_h: float, trim: AppliedTrim) -> bool:
    x = _number(piece.get("x"))
    y = _number(piece.get("y"))
    w = _number(piece.get("w"))
    h = _number(piece.get("h"))
    tolerance = 0.001
    return (
        x >= trim.width_trim_cm - tolerance
        and y >= trim.length_trim_cm - tolerance
        and x + w <= full_w - trim.width_trim_cm + tolerance
        and y + h <= full_h - trim.length_trim_cm + tolerance
    )


def _quality(snapshot: dict[str, Any], trim: AppliedTrim) -> PlanQuality:
    failures = 0
    sheets = snapshot.get("sheets") or []
    for sheet in sheets:
        full_w = _number(sheet.get("full_width_cm") or snapshot.get("full_board_width_cm"))
        full_h = _number(sheet.get("full_length_cm") or snapshot.get("full_board_length_cm"))
        for piece in sheet.get("pieces") or []:
            failures += 0 if _piece_fits(piece, full_w=full_w, full_h=full_h, trim=trim) else 1
    return PlanQuality(unplaced_count=failures, board_count=len(sheets))


def _shift_geometry(geometry: Any, *, dx_mm: float, dy_mm: float) -> Any:
    if not isinstance(geometry, dict):
        return geometry
    shifted = dict(geometry)

    def shift_polygon(points: Any) -> Any:
        if not isinstance(points, list):
            return points
        return [
            [float(point[0]) - dx_mm, float(point[1]) - dy_mm]
            for point in points
        ]

    shifted["outer"] = shift_polygon(geometry.get("outer"))
    shifted["holes"] = [shift_polygon(hole) for hole in (geometry.get("holes") or [])]
    return shifted


def _trim_policy(*, preferred: AppliedTrim, decision: AdaptiveTrimDecision) -> dict[str, Any]:
    return {
        "mode": decision.mode,
        "preferred_trim_mm": round(preferred.width_trim_cm * 10.0, 2),
        "applied_width_trim_mm": round(decision.applied.width_trim_cm * 10.0, 2),
        "applied_length_trim_mm": round(decision.applied.length_trim_cm * 10.0, 2),
        "relaxed_axes": list(decision.relaxed_axes),
        "precision_mm": round(TRIM_PRECISION_CM * 10.0, 2),
        "preferred_quality": {
            "unplaced_count": decision.preferred_quality.unplaced_count,
            "board_count": decision.preferred_quality.board_count,
        },
        "applied_quality": {
            "unplaced_count": decision.applied_quality.unplaced_count,
            "board_count": decision.applied_quality.board_count,
        },
    }


def apply_adaptive_trim_to_fixed_dxf_layout(
    snapshot: dict[str, Any],
    *,
    preferred_trim_mm: float,
) -> dict[str, Any]:
    """Resolve ALMADINA-138 Applied Trim for an already validated physical DXF layout.

    The imported layout is fixed: no optimizer is rerun and no geometry is
    repacked. Candidate trims are evaluated only against each piece's physical
    position inside its physical board. Physical board bounds therefore remain
    absolute; adaptive trim can only relax the preferred usable inset.
    """
    preferred_cm = max(0.0, _number(preferred_trim_mm)) / 10.0
    preferred = AppliedTrim(preferred_cm, preferred_cm)
    preferred_quality = _quality(snapshot, preferred)
    has_pieces = any(sheet.get("pieces") for sheet in (snapshot.get("sheets") or []))
    decision = resolve_adaptive_trim(
        preferred=preferred,
        preferred_quality=preferred_quality,
        evaluate=lambda candidate: _quality(snapshot, candidate),
        has_pieces=has_pieces,
        # Fixed DXF import cannot improve board count by repacking. A zero lower
        # bound prevents the optimizer-only early exit while preserving the
        # canonical ALMADINA-138 candidate/refinement algorithm.
        physical_board_lower_bound=0,
    )
    if decision.applied_quality.unplaced_count:
        raise DxfAppliedTrimError("dxf_layout_exceeds_physical_board_or_applied_trim")

    result = deepcopy(snapshot)
    applied = decision.applied
    full_w = _number(result.get("full_board_width_cm"))
    full_h = _number(result.get("full_board_length_cm"))
    usable_w = applied.usable_width_cm(full_width_cm=full_w)
    usable_h = applied.usable_length_cm(full_length_cm=full_h)

    result["usable_board_width_cm"] = usable_w
    result["usable_board_length_cm"] = usable_h
    # trim_cm remains the Preferred Trim compatibility value, matching System
    # optimization snapshots. Applied Trim is axis-specific below.
    result["trim_cm"] = preferred_cm
    result["applied_trim_width_cm"] = applied.width_trim_cm
    result["applied_trim_length_cm"] = applied.length_trim_cm
    result["trim_policy"] = _trim_policy(preferred=preferred, decision=decision)
    result["margin_policy"] = {
        "mode": decision.mode,
        "preferred_margin_mm": round(preferred_cm * 10.0, 2),
        "left_mm": round(applied.width_trim_cm * 10.0, 2),
        "right_mm": round(applied.width_trim_cm * 10.0, 2),
        "top_mm": round(applied.length_trim_cm * 10.0, 2),
        "bottom_mm": round(applied.length_trim_cm * 10.0, 2),
        "notes": [],
    }

    for sheet in result.get("sheets") or []:
        sheet_full_w = _number(sheet.get("full_width_cm") or full_w)
        sheet_full_h = _number(sheet.get("full_length_cm") or full_h)
        sheet_usable_w = applied.usable_width_cm(full_width_cm=sheet_full_w)
        sheet_usable_h = applied.usable_length_cm(full_length_cm=sheet_full_h)
        sheet["usable_width_cm"] = sheet_usable_w
        sheet["usable_length_cm"] = sheet_usable_h
        sheet["w"] = sheet_usable_w
        sheet["h"] = sheet_usable_h
        for piece in sheet.get("pieces") or []:
            piece["x"] = _number(piece.get("x")) - applied.width_trim_cm
            piece["y"] = _number(piece.get("y")) - applied.length_trim_cm
            if "geometry" in piece:
                piece["geometry"] = _shift_geometry(
                    piece["geometry"],
                    dx_mm=applied.width_trim_cm * 10.0,
                    dy_mm=applied.length_trim_cm * 10.0,
                )

    return result


__all__ = [
    "DxfAppliedTrimError",
    "apply_adaptive_trim_to_fixed_dxf_layout",
]
