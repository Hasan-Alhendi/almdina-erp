"""Cross-board repack after the base search.

A board is cancelled only when every piece on it fits the remaining boards,
the piece count is unchanged, and validation reports no overlap or kerf fault.
A move that keeps the same number of boards is discarded.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .primitives import (
    make_placed_piece,
    num,
    orientations_for,
    prune_free_rects,
    rects_have_clearance,
    split_free_rect,
)


def improve_plan_search(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    time_limit_sec: float,
    min_remnant_width_cm: float,
    min_remnant_length_cm: float,
    min_remnant_area_m2: float,
) -> dict[str, Any]:
    """Try to drop the most cancellable boards inside the caller's time limit."""

    if machine_type == "Panel Saw" or time_limit_sec <= 0:
        return plan
    sheets = list(plan.get("sheets") or [])
    if len(sheets) < 2 or plan.get("unplaced"):
        return plan
    from .evaluation import validate_plan
    from .optimizer import enrich_plan_metrics

    ordered = sorted(
        sheets,
        key=lambda sheet: (
            len(sheet.get("pieces") or []),
            sum(num(piece.get("area_m2")) for piece in sheet.get("pieces") or []),
        ),
    )
    best = plan
    for victim in ordered[:3]:
        candidate = _move_sheet_onto_others(best, victim, kerf_cm)
        if candidate is None:
            continue
        if len(candidate.get("sheets") or []) >= len(best.get("sheets") or []):
            continue
        candidate = enrich_plan_metrics(
            candidate,
            str(best.get("method_key") or ""),
            machine_type,
            min_remnant_width_cm=min_remnant_width_cm,
            min_remnant_length_cm=min_remnant_length_cm,
            min_remnant_area_m2=min_remnant_area_m2,
        )
        for key in (
            "method_key",
            "method_label",
            "optimization_mode",
            "ordering_strategy",
            "attempts",
            "complexity",
            "search_elapsed_sec",
            "search_time_limit_sec",
            "solver_status",
            "solver_wall_time_sec",
            "glass_nesting_diagnostics",
        ):
            if key in best and key not in candidate:
                candidate[key] = best[key]
        if validate_plan(candidate, pieces, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
            continue
        best = candidate
    return best


def _move_sheet_onto_others(
    plan: dict[str, Any],
    victim: dict[str, Any],
    kerf_cm: float,
) -> dict[str, Any] | None:
    moving = [dict(piece) for piece in victim.get("pieces") or []]
    if not moving:
        return None
    copied = deepcopy(plan)
    kept = [
        sheet
        for sheet in copied.get("sheets") or []
        if sheet.get("sheet_no") != victim.get("sheet_no")
    ]
    if len(kept) == len(copied.get("sheets") or []):
        return None
    moving.sort(
        key=lambda piece: num(piece.get("w")) * num(piece.get("h")),
        reverse=True,
    )
    for piece in moving:
        source = _source_from_placed(piece)
        destination = None
        for sheet in kept:
            spot = _spot_on_sheet(sheet, source, kerf_cm)
            if spot is None:
                continue
            placed = make_placed_piece(
                source,
                spot["x"],
                spot["y"],
                spot["w"],
                spot["h"],
                bool(spot["rotated"]),
            )
            sheet.setdefault("pieces", []).append(placed)
            destination = sheet
            break
        if destination is None:
            return None
    for index, sheet in enumerate(kept, start=1):
        sheet["sheet_no"] = index
    copied["sheets"] = kept
    copied["unplaced"] = list(plan.get("unplaced") or [])
    return copied


def _source_from_placed(piece: dict[str, Any]) -> dict[str, Any]:
    source = dict(piece)
    if num(source.get("width_cm")) <= 0:
        source["width_cm"] = num(source.get("original_w") or source.get("w"))
    if num(source.get("length_cm")) <= 0:
        source["length_cm"] = num(source.get("original_h") or source.get("h"))
    return source


def _spot_on_sheet(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    kerf_cm: float,
) -> dict[str, float] | None:
    occupied = [
        {
            "x": num(item.get("x")),
            "y": num(item.get("y")),
            "w": num(item.get("w")),
            "h": num(item.get("h")),
        }
        for item in sheet.get("pieces") or []
    ]
    for rect in _free_rectangles(sheet):
        inset = _inset(rect, kerf_cm)
        if inset is None:
            continue
        for orientation in orientations_for(piece):
            if orientation["w"] > inset["w"] + 1e-6 or orientation["h"] > inset["h"] + 1e-6:
                continue
            trial = {
                "x": inset["x"],
                "y": inset["y"],
                "w": orientation["w"],
                "h": orientation["h"],
                "rotated": bool(orientation["rotated"]),
            }
            if any(
                not rects_have_clearance(trial, other, kerf_cm, 1e-6)
                for other in occupied
            ):
                continue
            return trial
    return None


def _free_rectangles(sheet: dict[str, Any]) -> list[dict[str, float]]:
    free: list[dict[str, float]] = [
        {
            "x": 0.0,
            "y": 0.0,
            "w": num(sheet.get("w")),
            "h": num(sheet.get("h")),
        }
    ]
    for piece in sheet.get("pieces") or []:
        used = {
            "x": num(piece.get("x")),
            "y": num(piece.get("y")),
            "w": num(piece.get("w")),
            "h": num(piece.get("h")),
        }
        nxt: list[dict[str, float]] = []
        for rect in free:
            nxt.extend(split_free_rect(rect, used))
        free = prune_free_rects(nxt)
    return sorted(free, key=lambda rect: rect["w"] * rect["h"], reverse=True)


def _inset(rect: dict[str, float], kerf_cm: float) -> dict[str, float] | None:
    gap = max(0.0, kerf_cm)
    width = rect["w"] - 2 * gap
    height = rect["h"] - 2 * gap
    if width <= 1e-6 or height <= 1e-6:
        return None
    return {
        "x": rect["x"] + gap,
        "y": rect["y"] + gap,
        "w": width,
        "h": height,
    }


__all__ = ["improve_plan_search"]
