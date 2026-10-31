"""Turn leftover sheet slack into symmetric edge trim without repacking.

Adaptive Trim may drop the preferred margin for the whole plan so one full-size
door still fits. Another sheet on that plan can still have enough free edge
space for the preferred margin. This step translates each sheet's placed group
so that free space is split across both ends of an axis, up to the preferred
trim. Doors keep their order, rotation, and kerf gaps. No board is added.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import TRIM_PRECISION_CM
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import DxfGeometrySnapshotError
from almdina_erp.almdina_erp.domain.cutting.primitives import num


def realize_sheet_edge_trim(
    sheets: list[dict[str, Any]],
    *,
    full_width_cm: float,
    full_length_cm: float,
    preferred_width_trim_cm: float,
    preferred_length_trim_cm: float,
    precision_cm: float = TRIM_PRECISION_CM,
    balance_existing_applied: bool = False,
    machine_type: str = "Auto",
    min_remnant_width_cm: float = 30.0,
    min_remnant_length_cm: float = 30.0,
    min_remnant_area_m2: float = 0.09,
    max_centerable_edge_gap_cm: float = 5.0,
) -> None:
    """Write the largest symmetric trim each sheet can actually hold."""

    for sheet in sheets:
        if str(sheet.get("resource_kind") or "FULL_BOARD").upper() == "OFFCUT":
            continue
        pieces = list(sheet.get("pieces") or [])
        if not pieces:
            continue
        for axis, full_cm, preferred_cm in (
            ("x", full_width_cm, preferred_width_trim_cm),
            ("y", full_length_cm, preferred_length_trim_cm),
        ):
            # Centering is evaluated as a physical translation on one axis at
            # a time. A useful remnant on the other axis must not block a move
            # that preserves its separable area.
            original = deepcopy(sheet)
            original_piece_refs = list(sheet.get("pieces") or [])
            original_piece_values = [deepcopy(piece) for piece in original_piece_refs]
            before = _largest_reusable_area(
                sheet, machine_type, min_remnant_width_cm,
                min_remnant_length_cm, min_remnant_area_m2,
            )
            _realize_axis(
                sheet, list(sheet.get("pieces") or []), axis=axis,
                full_cm=full_cm, preferred_cm=preferred_cm,
                current_cm=max(0.0, num(sheet.get(
                    "applied_trim_width_cm" if axis == "x" else "applied_trim_length_cm"
                ))),
                precision_cm=precision_cm,
                balance_existing_applied=balance_existing_applied,
                max_centerable_edge_gap_cm=max(0.0, num(max_centerable_edge_gap_cm)),
            )
            after = _largest_reusable_area(
                sheet, machine_type, min_remnant_width_cm,
                min_remnant_length_cm, min_remnant_area_m2,
            )
            if balance_existing_applied and after + 1e-9 < before:
                sheet.clear()
                sheet.update(original)
                for piece, values in zip(original_piece_refs, original_piece_values):
                    piece.clear()
                    piece.update(values)
                sheet["pieces"] = original_piece_refs


def _largest_reusable_area(
    sheet: dict[str, Any],
    machine_type: str,
    min_remnant_width_cm: float,
    min_remnant_length_cm: float,
    min_remnant_area_m2: float,
) -> float:
    # Share the factory thresholds and separability rules with industrial rank.
    from .optimizer import _largest_reusable_free_area

    return _largest_reusable_free_area(
        {"sheets": [sheet]}, min_remnant_width_cm, min_remnant_length_cm,
        min_remnant_area_m2, machine_type=machine_type,
    )


def resolved_sheet_trim_cm(
    sheet: dict[str, Any] | None,
    plan: dict[str, Any] | None = None,
    *,
    axis: str,
) -> float:
    """Trim that places usable-frame coordinates on the physical board.

    Piece ``x``/``y`` stay in the sheet's usable frame: top-left origin, x to
    the right, y downward, centimetres. Physical position is that coordinate
    plus this trim. An explicit sheet value, including zero, wins. A missing
    value is recovered from ``full - usable`` before the plan-level applied
    trim, so a plan-wide zero does not erase a sheet that recovered slack.
    Equal full/usable dimensions prove zero trim; preferred trim must not
    invent an inset. Contradictory dimensions cannot prove a physical frame.
    """

    source = sheet or {}
    owner = plan or {}
    trim_key = "applied_trim_width_cm" if axis == "x" else "applied_trim_length_cm"
    if trim_key in source and source.get(trim_key) is not None:
        return max(0.0, num(source.get(trim_key)))

    kind = str(source.get("source_type") or "Full Board").strip().lower()
    if kind not in {"", "full board", "full_board"}:
        if trim_key in owner and owner.get(trim_key) is not None:
            return max(0.0, num(owner.get(trim_key)))
        return 0.0

    full_key = "full_width_cm" if axis == "x" else "full_length_cm"
    usable_key = "usable_width_cm" if axis == "x" else "usable_length_cm"
    size_key = "w" if axis == "x" else "h"
    sheet_full = num(source.get(full_key))
    sheet_usable = num(source.get(usable_key)) or num(source.get(size_key))
    if sheet_full > 0 and sheet_usable > 0:
        if sheet_usable > sheet_full:
            raise DxfGeometrySnapshotError("sheet usable dimensions exceed physical dimensions.")
        return (sheet_full - sheet_usable) / 2.0

    if trim_key in owner and owner.get(trim_key) is not None:
        return max(0.0, num(owner.get(trim_key)))

    plan_full_key = "full_board_width_cm" if axis == "x" else "full_board_length_cm"
    plan_usable_key = "usable_board_width_cm" if axis == "x" else "usable_board_length_cm"
    plan_full = num(owner.get(plan_full_key))
    plan_usable = num(owner.get(plan_usable_key))
    if plan_full > 0 and plan_usable > 0:
        if plan_usable > plan_full:
            raise DxfGeometrySnapshotError("plan usable dimensions exceed physical dimensions.")
        return (plan_full - plan_usable) / 2.0
    return max(0.0, num(owner.get("trim_cm")))


def physical_edge_margins_mm(
    sheet: dict[str, Any],
    plan: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Door-to-board gaps in millimetres, in the physical sheet frame.

    ``top`` is the gap above the highest door. ``bottom`` is the gap under the
    lowest door. A gap of zero is an original board edge.
    """

    pieces = list(sheet.get("pieces") or [])
    trim_w = resolved_sheet_trim_cm(sheet, plan, axis="x")
    trim_h = resolved_sheet_trim_cm(sheet, plan, axis="y")
    full_w = num(sheet.get("full_width_cm")) or num((plan or {}).get("full_board_width_cm"))
    full_h = num(sheet.get("full_length_cm")) or num((plan or {}).get("full_board_length_cm"))
    if not pieces:
        return {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    min_x = min(num(piece.get("x")) for piece in pieces)
    max_x = max(num(piece.get("x")) + num(piece.get("w")) for piece in pieces)
    min_y = min(num(piece.get("y")) for piece in pieces)
    max_y = max(num(piece.get("y")) + num(piece.get("h")) for piece in pieces)
    return {
        "left": round((trim_w + min_x) * 10, 3),
        "right": round((full_w - trim_w - max_x) * 10, 3),
        "top": round((trim_h + min_y) * 10, 3),
        "bottom": round((full_h - trim_h - max_y) * 10, 3),
    }


def _realize_axis(
    sheet: dict[str, Any],
    pieces: list[dict[str, Any]],
    *,
    axis: str,
    full_cm: float,
    preferred_cm: float,
    current_cm: float,
    precision_cm: float,
    balance_existing_applied: bool,
    max_centerable_edge_gap_cm: float,
) -> None:
    span_start, span_end = _occupied_span(pieces, axis)
    coordinate = "x" if axis == "x" else "y"
    size = "w" if axis == "x" else "h"
    if full_cm <= 0 or any(
        piece.get(coordinate) is None or piece.get(size) is None
        for piece in pieces
    ):
        # Incomplete legacy/test snapshots do not carry movable geometry.
        return
    span = max(0.0, span_end - span_start)
    if balance_existing_applied and any(
        piece.get("placement_outline_cm")
        or piece.get("geometry")
        or piece.get("overlays")
        or str(piece.get("piece_type") or "Regular") != "Regular"
        for piece in pieces
    ):
        # Until every attached outline can be translated as one solid unit,
        # keep shape-aware layouts untouched.
        return
    # Compatibility: older snapshots may have no applied trim. Keep their
    # historical edge realization behavior; new snapshots already carry M.
    if current_cm + precision_cm / 10.0 < preferred_cm:
        free_cm = max(0.0, full_cm - span)
        target = max(current_cm, _symmetric_trim(free_cm, preferred_cm, precision_cm))
        if target <= current_cm + precision_cm / 10.0:
            return
        frame = max(0.0, full_cm - target * 2.0)
        if axis == "x":
            delta = span_start
            for piece in pieces:
                piece["x"] = num(piece.get("x")) - delta
            sheet["w"] = frame
            sheet["usable_width_cm"] = frame
            sheet["applied_trim_width_cm"] = target
            return
        delta = span_end - frame
        for piece in pieces:
            piece["y"] = num(piece.get("y")) - delta
        sheet["h"] = frame
        sheet["usable_length_cm"] = frame
        sheet["applied_trim_length_cm"] = target
        return
    if not balance_existing_applied:
        return
    target = max(0.0, preferred_cm, current_cm)
    frame = full_cm - (target * 2.0)
    if frame <= 0:
        return
    perpendicular = "y" if axis == "x" else "x"
    translations: list[tuple[list[dict[str, Any]], float]] = []
    for group in _projection_groups(pieces, axis=perpendicular):
        start = min(num(piece.get(coordinate)) for piece in group)
        end = max(num(piece.get(coordinate)) + num(piece.get(size)) for piece in group)
        span = end - start
        if span > frame + precision_cm:
            return
        left_gap = max(0.0, start)
        right_gap = max(0.0, frame - end)
        if max(left_gap, right_gap) > max_centerable_edge_gap_cm + 1e-7:
            continue
        # Keep the mandatory inset fixed and split only this row/column's slack.
        delta = ((frame - span) / 2.0) - start
        if abs(delta) <= precision_cm / 10.0:
            continue
        if start + delta < -precision_cm or end + delta > frame + precision_cm:
            return
        translations.append((group, delta))
    sheet.pop("free_rects", None)
    sheet.pop("skyline", None)
    sheet.pop("shelves", None)
    for group, delta in translations:
        for piece in group:
            piece[coordinate] = num(piece.get(coordinate)) + delta
    if axis == "x":
        sheet["w"] = frame
        sheet["usable_width_cm"] = frame
        sheet["applied_trim_width_cm"] = target
    else:
        sheet["h"] = frame
        sheet["usable_length_cm"] = frame
        sheet["applied_trim_length_cm"] = target


def _projection_groups(pieces: list[dict[str, Any]], *, axis: str) -> list[list[dict[str, Any]]]:
    """Group pieces whose perpendicular spans overlap; only disjoint rows/columns move independently."""
    coordinate = "x" if axis == "x" else "y"
    size = "w" if axis == "x" else "h"
    ordered = sorted(pieces, key=lambda piece: num(piece.get(coordinate)))
    groups: list[list[dict[str, Any]]] = []
    group_end = -math.inf
    for piece in ordered:
        start = num(piece.get(coordinate))
        end = start + num(piece.get(size))
        if not groups or start >= group_end - 1e-9:
            groups.append([piece])
            group_end = end
        else:
            groups[-1].append(piece)
            group_end = max(group_end, end)
    return groups


def _occupied_span(pieces: list[dict[str, Any]], axis: str) -> tuple[float, float]:
    if axis == "x":
        start = min(num(piece.get("x")) for piece in pieces)
        end = max(num(piece.get("x")) + num(piece.get("w")) for piece in pieces)
        return start, end
    start = min(num(piece.get("y")) for piece in pieces)
    end = max(num(piece.get("y")) + num(piece.get("h")) for piece in pieces)
    return start, end


def _symmetric_trim(free_cm: float, preferred_cm: float, precision_cm: float) -> float:
    """Largest trim that fits on both ends, stepped down to the given precision."""

    if free_cm <= 0 or preferred_cm <= 0 or precision_cm <= 0:
        return 0.0
    capped = min(max(0.0, preferred_cm), free_cm / 2.0)
    steps = math.floor((capped + 1e-6) / precision_cm)
    return round(steps * precision_cm, 4)
