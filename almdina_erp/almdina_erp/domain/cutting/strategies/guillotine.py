from __future__ import annotations

from typing import Any

from ..primitives import (
    create_sheet,
    make_placed_piece,
    orientations_for,
    prune_free_rects,
)


def find_best_position_guillotine(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    fit_mode: str,
) -> dict[str, Any] | None:
    best = None
    for free_index, free in enumerate(sheet["free_rects"]):
        for orientation in orientations_for(piece):
            if orientation["w"] <= free["w"] and orientation["h"] <= free["h"]:
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
                score = leftover_area * 1000 + short_side
                if fit_mode == "best_area":
                    score = leftover_area * 100000 + short_side
                if fit_mode == "best_short_side":
                    score = short_side * 100000 + leftover_area
                if fit_mode == "best_long_side":
                    score = long_side * 100000 + leftover_area
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


def place_piece_guillotine(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    position: dict[str, Any],
    kerf_cm: float,
    split_mode: str,
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
    free = sheet["free_rects"].pop(position["free_index"])
    remaining_w = free["w"] - position["w"] - kerf_cm
    remaining_h = free["h"] - position["h"] - kerf_cm
    min_size = 0.01
    right_full = {
        "x": free["x"] + position["w"] + kerf_cm,
        "y": free["y"],
        "w": remaining_w,
        "h": free["h"],
    }
    bottom_trimmed = {
        "x": free["x"],
        "y": free["y"] + position["h"] + kerf_cm,
        "w": position["w"],
        "h": remaining_h,
    }
    right_trimmed = {
        "x": free["x"] + position["w"] + kerf_cm,
        "y": free["y"],
        "w": remaining_w,
        "h": position["h"],
    }
    bottom_full = {
        "x": free["x"],
        "y": free["y"] + position["h"] + kerf_cm,
        "w": free["w"],
        "h": remaining_h,
    }

    def add(rect: dict[str, float]) -> None:
        if rect["w"] > min_size and rect["h"] > min_size:
            sheet["free_rects"].append(rect)

    if split_mode == "long_axis":
        if remaining_w > remaining_h:
            add(right_full)
            add(bottom_trimmed)
        else:
            add(right_trimmed)
            add(bottom_full)
    else:
        if remaining_w < remaining_h:
            add(right_full)
            add(bottom_trimmed)
        else:
            add(right_trimmed)
            add(bottom_full)
    sheet["free_rects"] = prune_free_rects(sheet["free_rects"])


def pack_guillotine(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    split_mode: str,
    fit_mode: str,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    for piece in pieces:
        placed = False
        for sheet in sheets:
            position = find_best_position_guillotine(sheet, piece, fit_mode)
            if position:
                place_piece_guillotine(
                    sheet,
                    piece,
                    position,
                    kerf_cm,
                    split_mode,
                )
                placed = True
                break
        if not placed:
            sheet = create_sheet(len(sheets) + 1, board_w_cm, board_h_cm)
            position = find_best_position_guillotine(sheet, piece, fit_mode)
            if position:
                place_piece_guillotine(
                    sheet,
                    piece,
                    position,
                    kerf_cm,
                    split_mode,
                )
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    return {"sheets": sheets, "unplaced": unplaced}


__all__ = [
    "find_best_position_guillotine",
    "pack_guillotine",
    "place_piece_guillotine",
]
