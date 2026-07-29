from __future__ import annotations

from typing import Any

from ..primitives import (
    create_sheet,
    make_placed_piece,
    orientations_for,
    prune_free_rects,
    round_value,
    split_free_rect,
)


def contact_point_score(
    sheet: dict[str, Any],
    x: float,
    y: float,
    w: float,
    h: float,
) -> float:
    score = 0.0
    if x == 0 or round_value(x + w, 3) == round_value(sheet["w"], 3):
        score += h
    if y == 0 or round_value(y + h, 3) == round_value(sheet["h"], 3):
        score += w

    for placed in sheet["pieces"]:
        if round_value(placed["x"] + placed["w"], 3) == round_value(
            x, 3
        ) or round_value(x + w, 3) == round_value(placed["x"], 3):
            score += max(
                0.0,
                min(y + h, placed["y"] + placed["h"]) - max(y, placed["y"]),
            )
        if round_value(placed["y"] + placed["h"], 3) == round_value(
            y, 3
        ) or round_value(y + h, 3) == round_value(placed["y"], 3):
            score += max(
                0.0,
                min(x + w, placed["x"] + placed["w"]) - max(x, placed["x"]),
            )
    return score


def maxrects_score(
    sheet: dict[str, Any],
    free: dict[str, float],
    orientation: dict[str, Any],
    heuristic: str,
) -> float:
    leftover_area = (free["w"] * free["h"]) - (
        orientation["w"] * orientation["h"]
    )
    short_side = min(
        free["w"] - orientation["w"],
        free["h"] - orientation["h"],
    )
    long_side = max(
        free["w"] - orientation["w"],
        free["h"] - orientation["h"],
    )
    if heuristic == "best_area":
        return leftover_area * 100000 + short_side * 100 + long_side
    if heuristic == "bottom_left":
        return free["y"] * 100000 + free["x"]
    if heuristic == "contact_point":
        contact = contact_point_score(
            sheet,
            free["x"],
            free["y"],
            orientation["w"],
            orientation["h"],
        )
        return -contact * 100000 + leftover_area
    return short_side * 100000 + long_side * 100 + leftover_area


def find_best_position_maxrects(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    heuristic: str,
) -> dict[str, Any] | None:
    best = None
    for free_index, free in enumerate(sheet["free_rects"]):
        for orientation in orientations_for(piece):
            if orientation["w"] <= free["w"] and orientation["h"] <= free["h"]:
                score = maxrects_score(sheet, free, orientation, heuristic)
                if best is None or score < best["score"]:
                    best = {
                        "x": free["x"],
                        "y": free["y"],
                        "w": orientation["w"],
                        "h": orientation["h"],
                        "rotated": orientation["rotated"],
                        "free_index": free_index,
                        "score": score,
                    }
    return best


def place_piece_maxrects(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    position: dict[str, Any],
    kerf_cm: float,
) -> None:
    sheet["pieces"].append(
        make_placed_piece(
            piece,
            position["x"],
            position["y"],
            position["w"],
            position["h"],
            position["rotated"],
        )
    )
    used = {
        "x": position["x"],
        "y": position["y"],
        "w": position["w"] + kerf_cm,
        "h": position["h"] + kerf_cm,
    }
    new_free_rects: list[dict[str, float]] = []
    for free in sheet["free_rects"]:
        new_free_rects.extend(split_free_rect(free, used))
    sheet["free_rects"] = prune_free_rects(new_free_rects)


def pack_maxrects(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    heuristic: str,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    for piece in pieces:
        placed = False
        for sheet in sheets:
            position = find_best_position_maxrects(sheet, piece, heuristic)
            if position:
                place_piece_maxrects(sheet, piece, position, kerf_cm)
                placed = True
                break
        if not placed:
            sheet = create_sheet(len(sheets) + 1, board_w_cm, board_h_cm)
            position = find_best_position_maxrects(sheet, piece, heuristic)
            if position:
                place_piece_maxrects(sheet, piece, position, kerf_cm)
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    return {"sheets": sheets, "unplaced": unplaced}


__all__ = [
    "contact_point_score",
    "find_best_position_maxrects",
    "maxrects_score",
    "pack_maxrects",
    "place_piece_maxrects",
]
