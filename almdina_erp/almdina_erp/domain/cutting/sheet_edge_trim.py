"""Turn leftover sheet slack into symmetric edge trim without repacking.

Adaptive Trim may drop the preferred margin for the whole plan so one full-size
door still fits. Another sheet on that plan can still have enough free edge
space for the preferred margin. This step translates each sheet's placed group
so that free space is split across both ends of an axis, up to the preferred
trim. Doors keep their order, rotation, and kerf gaps. No board is added.
"""

from __future__ import annotations

import math
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import TRIM_PRECISION_CM
from almdina_erp.almdina_erp.domain.cutting.primitives import num


def realize_sheet_edge_trim(
    sheets: list[dict[str, Any]],
    *,
    full_width_cm: float,
    full_length_cm: float,
    preferred_width_trim_cm: float,
    preferred_length_trim_cm: float,
    precision_cm: float = TRIM_PRECISION_CM,
) -> None:
    """Write the largest symmetric trim each sheet can actually hold."""

    for sheet in sheets:
        if str(sheet.get("resource_kind") or "FULL_BOARD").upper() == "OFFCUT":
            continue
        pieces = list(sheet.get("pieces") or [])
        if not pieces:
            continue
        _realize_axis(
            sheet,
            pieces,
            axis="x",
            full_cm=full_width_cm,
            preferred_cm=preferred_width_trim_cm,
            current_cm=max(0.0, num(sheet.get("applied_trim_width_cm"))),
            precision_cm=precision_cm,
        )
        _realize_axis(
            sheet,
            pieces,
            axis="y",
            full_cm=full_length_cm,
            preferred_cm=preferred_length_trim_cm,
            current_cm=max(0.0, num(sheet.get("applied_trim_length_cm"))),
            precision_cm=precision_cm,
        )


def _realize_axis(
    sheet: dict[str, Any],
    pieces: list[dict[str, Any]],
    *,
    axis: str,
    full_cm: float,
    preferred_cm: float,
    current_cm: float,
    precision_cm: float,
) -> None:
    span_start, span_end = _occupied_span(pieces, axis)
    span = max(0.0, span_end - span_start)
    free_cm = max(0.0, full_cm - span)
    target = _symmetric_trim(free_cm, preferred_cm, precision_cm)
    target = max(target, current_cm)
    if target <= current_cm + (precision_cm / 10.0):
        return

    frame = max(0.0, full_cm - (target * 2.0))
    sheet.pop("free_rects", None)
    sheet.pop("skyline", None)
    sheet.pop("shelves", None)
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
