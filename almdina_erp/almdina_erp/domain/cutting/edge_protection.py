"""Conservative final System placement preference; never a packing constraint.

Move an entire regular FULL_BOARD group rigidly after alignment. Attached or
nested geometry is deliberately left alone until its complete translation can
be proven. Every proposal is isolated, checked and either accepted or discarded.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .cut_line_quality import sheet_cut_line_quality
from .evaluation import placement_permission_errors, validate_plan
from .final_cut_line_alignment import _is_movable_regular
from .optimizer import _reusable_free_rectangles_for_sheet, enrich_plan_metrics
from .plan_search import _locked_piece_ids
from .plan_settings import EdgeProtectionPolicy
from .sheet_edge_trim import (
    _occupied_span, decide_axis_placement, resolved_sheet_trim_cm,
)

_EPS_CM = 1e-7
_NETWORK_TOL_MM = 0.05
_ATTACHED_GEOMETRY_KEYS = (
    "geometry", "overlays", "special_shape_geometry_json", "placement_outline_cm",
    "toolpaths", "cnc_toolpaths", "attached_geometry",
)


def _remnants_preserved(
    before: dict[str, Any], after: dict[str, Any], *, axis: str,
    delta_cm: float, options: dict[str, Any],
) -> bool:
    """Allow only the protection strip loss, with each useful remnant still whole/eligible.

    Maximal free rectangles may overlap. Each original useful rectangle must
    retain one connected, factory-eligible successor covering its remaining
    area; a collection of fragments cannot stand in for that successor.
    """
    previous = _reusable_free_rectangles_for_sheet(before, **options)
    current = _reusable_free_rectangles_for_sheet(after, **options)
    for rect in previous:
        strip_area = abs(delta_cm) * rect["h" if axis == "x" else "w"]
        required_area = rect["w"] * rect["h"] - strip_area
        if required_area <= _EPS_CM:
            return False
        if not any(
            max(0.0, min(rect["x"] + rect["w"], other["x"] + other["w"])
                - max(rect["x"], other["x"]))
            * max(0.0, min(rect["y"] + rect["h"], other["y"] + other["h"])
                - max(rect["y"], other["y"])) >= required_area - _EPS_CM
            for other in current
        ):
            return False
    return True


def _movable_sheet(
    sheet: dict[str, Any], sources: dict[int, dict[str, Any]], locked: set[int],
) -> bool:
    if str(sheet.get("resource_kind") or "FULL_BOARD").upper() != "FULL_BOARD":
        return False
    if any(sheet.get(key) for key in _ATTACHED_GEOMETRY_KEYS):
        return False
    # Reuse alignment's conservative geometry classification, including source
    # metadata that a reduced placement might otherwise have omitted.
    for piece in sheet.get("pieces") or []:
        source = sources.get(piece.get("id"))
        if (source is None or piece.get("id") in locked
                or (source.get("piece_type") or "Regular") != "Regular"
                or (source.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
                or not _is_movable_regular(piece)
                or not _is_movable_regular({**piece, **source})
                or any(source.get(key) or piece.get(key) for key in _ATTACHED_GEOMETRY_KEYS)):
            return False
    return bool(sheet.get("pieces"))


def protect_plan_edges(
    plan: dict[str, Any], sources: list[dict[str, Any]],
    width_cm: float, length_cm: float, kerf_cm: float, *,
    policy: EdgeProtectionPolicy, max_centerable_edge_gap_cm: float,
    machine_type: str, mirroring_allowed: bool, metric_options: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return the accepted geometry and concise axis decisions, without mutating input."""
    if not (policy.horizontal_mm or policy.vertical_mm):
        return plan, []
    best = plan
    decisions: list[dict[str, Any]] = []
    by_id = {piece["id"]: piece for piece in sources}
    locked = _locked_piece_ids(plan)
    remnant_options = {**metric_options, "machine_type": machine_type}
    for index in range(len(plan.get("sheets") or [])):
        for axis, protection in (("x", policy.horizontal_mm), ("y", policy.vertical_mm)):
            if protection == 0:
                continue
            sheet = best["sheets"][index]
            record = {"sheet_no": sheet.get("sheet_no", index + 1), "axis": axis,
                      "reason": "UNSAFE_MOVE", "shift_mm": 0.0}
            decisions.append(record)
            if (any(plan.get(key) for key in _ATTACHED_GEOMETRY_KEYS)
                    or not _movable_sheet(sheet, by_id, locked)):
                record["detail"] = "protected_geometry"
                continue
            trim = resolved_sheet_trim_cm(sheet, axis=axis)
            full_key = "full_width_cm" if axis == "x" else "full_length_cm"
            size_key = "w" if axis == "x" else "h"
            frame = float(sheet[full_key]) - 2 * trim
            if frame <= 0 or abs(frame - float(sheet[size_key])) > _EPS_CM:
                record["detail"] = "physical_frame"
                continue
            pieces = sheet["pieces"]
            decision = decide_axis_placement(
                *_occupied_span(pieces, axis), frame, trim_cm=trim,
                max_centerable_edge_gap_cm=max_centerable_edge_gap_cm, protection_mm=protection,
            )
            record["reason"] = decision.reason
            # Existing centering always wins. Its application remains in the
            # established pre-alignment stage; do not recenter its result here.
            if decision.reason != "EDGE_PROTECTED":
                if decision.reason == "CENTERED" and abs(decision.delta_cm) > _EPS_CM:
                    record.update(reason="REMNANT_PRESERVED", detail="centering_priority")
                continue
            before = sheet_cut_line_quality(sheet, kerf_cm)
            if before is None:
                # Respect the shared topology metric's bounded work limit
                # before attempting expensive free-space reconstruction.
                record.update(reason="UNSAFE_MOVE", detail="cut_line_quality")
                continue
            candidate = deepcopy(best)
            moved = candidate["sheets"][index]
            for piece in moved["pieces"]:
                piece[axis] = float(piece[axis]) + decision.delta_cm
            for key in ("free_rects", "skyline", "shelves"):
                moved.pop(key, None)
            if not _remnants_preserved(sheet, moved, axis=axis, delta_cm=decision.delta_cm,
                                       options=remnant_options):
                record.update(reason="REMNANT_PRESERVED", detail="useful_remnant")
                continue
            after = sheet_cut_line_quality(moved, kerf_cm)
            if (after is None
                    or after[0] > before[0] + _NETWORK_TOL_MM or after[1] > before[1]
                    or after[2] + _NETWORK_TOL_MM < before[2]):
                record.update(reason="UNSAFE_MOVE", detail="cut_line_quality")
                continue
            if (validate_plan(candidate, sources, width_cm, length_cm, kerf_cm=kerf_cm)
                    or placement_permission_errors(candidate, sources, mirroring_allowed=mirroring_allowed)):
                record.update(reason="UNSAFE_MOVE", detail="manufacturing_validation")
                continue
            best = enrich_plan_metrics(candidate, str(plan.get("method_key") or ""), **remnant_options)
            record["shift_mm"] = round(decision.delta_cm * 10, 6)
    return best, decisions
