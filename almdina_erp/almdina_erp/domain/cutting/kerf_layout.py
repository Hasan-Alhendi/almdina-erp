from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .primitives import num, rects_have_clearance

Packer = Callable[..., dict[str, Any]]
_TOLERANCE = 1e-6


def pack_with_stable_kerf(
    packer: Packer,
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    args: tuple[Any, ...],
) -> dict[str, Any]:
    """Keep the zero-kerf arrangement and widen its saw gaps when that still fits.

    Heuristic scores treat leftover free-rectangle size as the placement key.
    Growing the kerf shrinks those rectangles by different amounts, so the same
    doors can jump to another slot or rotation even though the previous
    arrangement still fits with a larger gap. Packing once at zero kerf and
    then separating that arrangement preserves door order. The direct kerf
    pack remains the result when separation would add a board or leave a piece
    unplaced.
    """

    kerf = max(0.0, num(kerf_cm))
    direct = packer(deepcopy(pieces), board_w_cm, board_h_cm, kerf, *args)
    if kerf <= _TOLERANCE:
        return direct

    base = packer(deepcopy(pieces), board_w_cm, board_h_cm, 0.0, *args)
    expanded = expand_plan_kerf(
        base,
        kerf,
        board_w_cm=board_w_cm,
        board_h_cm=board_h_cm,
    )
    if expanded is not None and _placement_quality(expanded) <= _placement_quality(direct):
        return expanded
    return direct


def expand_plan_kerf(
    plan: dict[str, Any],
    kerf_cm: float,
    *,
    board_w_cm: float,
    board_h_cm: float,
) -> dict[str, Any] | None:
    """Return a copy whose existing neighbors are at least ``kerf_cm`` apart."""

    kerf = max(0.0, num(kerf_cm))
    expanded = deepcopy(plan)
    for sheet in expanded.get("sheets") or []:
        width = num(sheet.get("w")) or num(board_w_cm)
        height = num(sheet.get("h")) or num(board_h_cm)
        moved = _separate_sheet(sheet.get("pieces") or [], kerf, width, height)
        if moved is None:
            return None
        sheet["pieces"] = moved
        sheet.pop("free_rects", None)
        sheet.pop("skyline", None)
        sheet.pop("shelves", None)
    return expanded


def _placement_quality(plan: dict[str, Any]) -> tuple[int, int]:
    return (
        len(plan.get("unplaced") or []),
        len(plan.get("sheets") or []),
    )


def _ranges_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return min(end_a, end_b) - max(start_a, start_b) > _TOLERANCE


def _separate_sheet(
    pieces: list[dict[str, Any]],
    kerf: float,
    board_w: float,
    board_h: float,
) -> list[dict[str, Any]] | None:
    items = [dict(piece) for piece in pieces]
    original = [
        (num(piece.get("x")), num(piece.get("y")), num(piece.get("w")), num(piece.get("h")))
        for piece in items
    ]
    count = len(items)
    for _ in range(count * count + 1):
        moved = False
        for index, (origin_x, origin_y, width, height) in enumerate(original):
            for other_index, (other_x, other_y, other_w, other_h) in enumerate(original):
                if index == other_index:
                    continue
                piece = items[index]
                other = items[other_index]
                if other_x >= origin_x + width - _TOLERANCE and _ranges_overlap(
                    origin_y,
                    origin_y + height,
                    other_y,
                    other_y + other_h,
                ):
                    minimum_x = num(piece.get("x")) + num(piece.get("w")) + kerf
                    if num(other.get("x")) + _TOLERANCE < minimum_x:
                        other["x"] = minimum_x
                        moved = True
                if other_y >= origin_y + height - _TOLERANCE and _ranges_overlap(
                    origin_x,
                    origin_x + width,
                    other_x,
                    other_x + other_w,
                ):
                    minimum_y = num(piece.get("y")) + num(piece.get("h")) + kerf
                    if num(other.get("y")) + _TOLERANCE < minimum_y:
                        other["y"] = minimum_y
                        moved = True
        if not moved:
            break
    else:
        return None

    for piece in items:
        x = num(piece.get("x"))
        y = num(piece.get("y"))
        width = num(piece.get("w"))
        height = num(piece.get("h"))
        if (
            x < -_TOLERANCE
            or y < -_TOLERANCE
            or x + width > board_w + _TOLERANCE
            or y + height > board_h + _TOLERANCE
        ):
            return None

    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            if not rects_have_clearance(first, second, kerf):
                return None
    return items


__all__ = [
    "expand_plan_kerf",
    "pack_with_stable_kerf",
]
