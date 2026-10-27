"""Cross-board repack after the base search.

A board is cancelled only when every piece on it fits the remaining boards,
the piece count is unchanged, and validation reports no overlap or kerf fault.
When the board count stays the same, a short local search may still move or
swap a few regular pieces so the largest separable remnant grows. Fewer
boards remain better than a larger remnant. Glass nests, corner outlines, and
the clipped-void angle are left where they are.
"""

from __future__ import annotations

import time
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


_MAX_REMNANT_ATTEMPTS = 12
_LOCKED_PIECE_TYPES = frozenset({"Clipped Corner", "L-Shaped Corner", "Glass"})
_PRESERVED_PLAN_KEYS = (
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
    mirroring_allowed: bool = False,
) -> dict[str, Any]:
    """Drop cancellable boards, then try a few same-count remnant moves."""

    if machine_type == "Panel Saw" or time_limit_sec <= 0:
        return plan
    sheets = list(plan.get("sheets") or [])
    if len(sheets) < 2 or plan.get("unplaced"):
        return plan
    from .evaluation import placement_permission_errors, validate_plan
    from .optimizer import _candidate_is_better, enrich_plan_metrics

    metric_kwargs = {
        "min_remnant_width_cm": min_remnant_width_cm,
        "min_remnant_length_cm": min_remnant_length_cm,
        "min_remnant_area_m2": min_remnant_area_m2,
    }
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
        accepted = _accept_candidate(
            candidate,
            best,
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type=machine_type,
            mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs,
            enrich_plan_metrics=enrich_plan_metrics,
            validate_plan=validate_plan,
            permission_errors=placement_permission_errors,
            is_better=_candidate_is_better,
        )
        if accepted is not None:
            best = accepted
    deadline = time.monotonic() + min(time_limit_sec, max(0.05, 0.15 * time_limit_sec))
    return _improve_remnants(
        best,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type=machine_type,
        mirroring_allowed=mirroring_allowed,
        metric_kwargs=metric_kwargs,
        deadline=deadline,
        enrich_plan_metrics=enrich_plan_metrics,
        validate_plan=validate_plan,
        permission_errors=placement_permission_errors,
        is_better=_candidate_is_better,
    )


def _move_sheet_onto_others(
    plan: dict[str, Any],
    victim: dict[str, Any],
    kerf_cm: float,
) -> dict[str, Any] | None:
    preserved = _shape_nest_ids(plan)
    moving = [dict(piece) for piece in victim.get("pieces") or []]
    if not moving or any(int(piece["id"]) in preserved for piece in moving):
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


def _accept_candidate(
    candidate: dict[str, Any],
    best: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    mirroring_allowed: bool,
    metric_kwargs: dict[str, float],
    enrich_plan_metrics: Any,
    validate_plan: Any,
    permission_errors: Any,
    is_better: Any,
    deadline: float | None = None,
) -> dict[str, Any] | None:
    if len(candidate.get("sheets") or []) > len(best.get("sheets") or []):
        return None
    if candidate.get("unplaced"):
        return None
    enriched = enrich_plan_metrics(
        candidate,
        str(best.get("method_key") or ""),
        machine_type,
        **metric_kwargs,
    )
    for key in _PRESERVED_PLAN_KEYS:
        if key in best and key not in enriched:
            enriched[key] = best[key]
    baseline = best if best.get("industrial_rank") else enrich_plan_metrics(
        best,
        str(best.get("method_key") or ""),
        machine_type,
        **metric_kwargs,
    )
    if not is_better(enriched, baseline):
        return None
    if validate_plan(
        enriched,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm=kerf_cm,
        deadline_monotonic=deadline,
    ):
        return None
    if permission_errors(enriched, pieces, mirroring_allowed=mirroring_allowed):
        return None
    return enriched


def _improve_remnants(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    mirroring_allowed: bool,
    metric_kwargs: dict[str, float],
    deadline: float,
    enrich_plan_metrics: Any,
    validate_plan: Any,
    permission_errors: Any,
    is_better: Any,
) -> dict[str, Any]:
    """Move or swap a few regular pieces while the board count does not rise."""

    best = plan
    attempts = 0
    for move in _remnant_moves(best):
        if attempts >= _MAX_REMNANT_ATTEMPTS or time.monotonic() > deadline:
            break
        attempts += 1
        candidate = _relocate(best, move, kerf_cm)
        if candidate is None:
            continue
        accepted = _accept_candidate(
            candidate,
            best,
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type=machine_type,
            mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs,
            enrich_plan_metrics=enrich_plan_metrics,
            validate_plan=validate_plan,
            permission_errors=permission_errors,
            is_better=is_better,
            deadline=deadline,
        )
        if accepted is not None:
            best = accepted
    return best


def _remnant_moves(plan: dict[str, Any]) -> list[tuple[tuple[int, int], ...]]:
    """A bounded list of piece moves and swaps, largest newly freed area first."""

    locked = _locked_piece_ids(plan)
    sheets = list(plan.get("sheets") or [])
    ranked: list[tuple[float, tuple[tuple[int, int], ...]]] = []
    for source in sheets:
        movable = [
            piece
            for piece in source.get("pieces") or []
            if int(piece["id"]) not in locked
        ]
        movable.sort(
            key=lambda piece: _freed_area(source, piece),
            reverse=True,
        )
        chosen = movable[:2]
        for piece in chosen:
            for destination in sheets:
                if destination.get("sheet_no") == source.get("sheet_no"):
                    continue
                ranked.append(
                    (
                        _freed_area(source, piece),
                        ((int(piece["id"]), int(destination["sheet_no"])),),
                    )
                )
        if len(chosen) == 2:
            for destination in sheets:
                if destination.get("sheet_no") == source.get("sheet_no"):
                    continue
                ranked.append(
                    (
                        _freed_area(source, chosen[0]) + _freed_area(source, chosen[1]),
                        tuple(
                            (int(piece["id"]), int(destination["sheet_no"]))
                            for piece in chosen
                        ),
                    )
                )
    for left_index, left in enumerate(sheets):
        for right in sheets[left_index + 1 :]:
            left_piece = _smallest_movable(left, locked)
            right_piece = _smallest_movable(right, locked)
            if left_piece is None or right_piece is None:
                continue
            ranked.append(
                (
                    0.0,
                    (
                        (int(left_piece["id"]), int(right["sheet_no"])),
                        (int(right_piece["id"]), int(left["sheet_no"])),
                    ),
                )
            )
    ranked.sort(key=lambda item: item[0], reverse=True)
    unique: list[tuple[tuple[int, int], ...]] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for _score, move in ranked:
        if move in seen:
            continue
        seen.add(move)
        unique.append(move)
        if len(unique) >= _MAX_REMNANT_ATTEMPTS:
            break
    return unique


def _relocate(
    plan: dict[str, Any],
    move: tuple[tuple[int, int], ...],
    kerf_cm: float,
) -> dict[str, Any] | None:
    copied = deepcopy(plan)
    located: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for sheet in copied.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            located[int(piece["id"])] = (sheet, piece)
    removed: list[tuple[dict[str, Any], int]] = []
    for piece_id, destination_no in move:
        found = located.get(int(piece_id))
        if found is None:
            return None
        source, piece = found
        source_pieces = source.setdefault("pieces", [])
        source_pieces.remove(piece)
        removed.append((piece, int(destination_no)))
    removed.sort(
        key=lambda item: num(item[0].get("w")) * num(item[0].get("h")),
        reverse=True,
    )
    sheets_by_no = {
        int(sheet.get("sheet_no")): sheet for sheet in copied.get("sheets") or []
    }
    for piece, destination_no in removed:
        destination = sheets_by_no.get(destination_no)
        if destination is None:
            return None
        source = _source_from_placed(piece)
        spot = _spot_on_sheet(destination, source, kerf_cm)
        if spot is None:
            return None
        destination.setdefault("pieces", []).append(
            make_placed_piece(
                source,
                spot["x"],
                spot["y"],
                spot["w"],
                spot["h"],
                bool(spot["rotated"]),
            )
        )
    kept = [sheet for sheet in copied.get("sheets") or [] if sheet.get("pieces")]
    if len(kept) != len(copied.get("sheets") or []):
        for index, sheet in enumerate(kept, start=1):
            sheet["sheet_no"] = index
        copied["sheets"] = kept
    copied["unplaced"] = list(plan.get("unplaced") or [])
    return copied


def _locked_piece_ids(plan: dict[str, Any]) -> set[int]:
    locked: set[int] = set()
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            try:
                piece_id = int(piece["id"])
            except (TypeError, ValueError):
                continue
            host = piece.get("glass_host_piece_id")
            if host not in (None, ""):
                locked.add(piece_id)
                try:
                    locked.add(int(host))
                except (TypeError, ValueError):
                    pass
            if piece.get("placement_outline_cm"):
                locked.add(piece_id)
            if str(piece.get("piece_type") or "") in _LOCKED_PIECE_TYPES:
                locked.add(piece_id)
    locked.update(_shape_nest_ids(plan))
    return locked


def _shape_nest_ids(plan: dict[str, Any]) -> set[int]:
    """Pieces placed by a corner or glass nest, including guests in that void."""

    locked: set[int] = set()
    for sheet in plan.get("sheets") or []:
        pieces = list(sheet.get("pieces") or [])
        nested = [piece for piece in pieces if _records_shape_nest(piece)]
        for piece in nested:
            try:
                locked.add(int(piece["id"]))
            except (TypeError, ValueError):
                continue
        if not nested:
            continue
        min_x = min(num(piece.get("x")) for piece in nested)
        min_y = min(num(piece.get("y")) for piece in nested)
        max_x = max(num(piece.get("x")) + num(piece.get("w")) for piece in nested)
        max_y = max(num(piece.get("y")) + num(piece.get("h")) for piece in nested)
        for piece in pieces:
            if piece in nested:
                continue
            center_x = num(piece.get("x")) + num(piece.get("w")) / 2
            center_y = num(piece.get("y")) + num(piece.get("h")) / 2
            if min_x - 1e-6 <= center_x <= max_x + 1e-6 and min_y - 1e-6 <= center_y <= max_y + 1e-6:
                try:
                    locked.add(int(piece["id"]))
                except (TypeError, ValueError):
                    continue
    return locked


def _records_shape_nest(piece: dict[str, Any]) -> bool:
    if piece.get("glass_host_piece_id") not in (None, ""):
        return True
    if piece.get("placement_outline_cm") or piece.get("placement_rotation_deg"):
        return True
    if piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored"):
        return True
    return "corner_rotation_quarter_turns" in piece or "placement_quarter_turns" in piece


def _smallest_movable(
    sheet: dict[str, Any],
    locked: set[int],
) -> dict[str, Any] | None:
    movable = [
        piece
        for piece in sheet.get("pieces") or []
        if int(piece["id"]) not in locked
    ]
    if not movable:
        return None
    return min(movable, key=lambda piece: num(piece.get("w")) * num(piece.get("h")))


def _freed_area(sheet: dict[str, Any], piece: dict[str, Any]) -> float:
    before = _largest_free_area(sheet)
    remaining = [
        item for item in sheet.get("pieces") or [] if item.get("id") != piece.get("id")
    ]
    after = _largest_free_area({**sheet, "pieces": remaining})
    return after - before


def _largest_free_area(sheet: dict[str, Any]) -> float:
    return max(
        (rect["w"] * rect["h"] for rect in _free_rectangles(sheet)),
        default=0.0,
    )


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
