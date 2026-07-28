from __future__ import annotations

from typing import Any

from ..primitives import make_placed_piece, orientations_for, round_value


def create_skyline_sheet(
    sheet_no: int,
    board_w_cm: float,
    board_h_cm: float,
) -> dict[str, Any]:
    return {
        "sheet_no": sheet_no,
        "w": board_w_cm,
        "h": board_h_cm,
        "pieces": [],
        "skyline": [{"x": 0.0, "y": 0.0, "w": board_w_cm}],
    }


def skyline_rect_fits(
    sheet: dict[str, Any],
    index: int,
    w: float,
    h: float,
) -> dict[str, float] | None:
    x = sheet["skyline"][index]["x"]
    if x + w > sheet["w"]:
        return None
    width_left = w
    y = sheet["skyline"][index]["y"]
    current_index = index
    while width_left > 0:
        if current_index >= len(sheet["skyline"]):
            return None
        y = max(y, sheet["skyline"][current_index]["y"])
        if y + h > sheet["h"]:
            return None
        width_left -= sheet["skyline"][current_index]["w"]
        current_index += 1
    return {"x": x, "y": y}


def skyline_find_position(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    mode: str,
) -> dict[str, Any] | None:
    best = None
    for index in range(len(sheet["skyline"])):
        for orientation in orientations_for(piece):
            position = skyline_rect_fits(
                sheet,
                index,
                orientation["w"],
                orientation["h"],
            )
            if not position:
                continue
            if mode == "best_fit":
                waste = position["y"] * sheet["w"]
                score = position["y"] * 100000 + waste + position["x"]
            else:
                score = position["y"] * 100000 + position["x"]
            if best is None or score < best["score"]:
                best = {
                    "index": index,
                    "x": position["x"],
                    "y": position["y"],
                    "w": orientation["w"],
                    "h": orientation["h"],
                    "rotated": orientation["rotated"],
                    "score": score,
                }
    return best


def skyline_merge(sheet: dict[str, Any]) -> None:
    index = 0
    while index < len(sheet["skyline"]) - 1:
        if round_value(sheet["skyline"][index]["y"], 3) == round_value(
            sheet["skyline"][index + 1]["y"], 3
        ):
            sheet["skyline"][index]["w"] += sheet["skyline"][index + 1]["w"]
            sheet["skyline"].pop(index + 1)
        else:
            index += 1


def skyline_add_level(
    sheet: dict[str, Any],
    position: dict[str, Any],
    kerf_cm: float,
) -> None:
    new_node = {
        "x": position["x"],
        "y": position["y"] + position["h"] + kerf_cm,
        "w": min(
            position["w"] + kerf_cm,
            sheet["w"] - position["x"],
        ),
    }
    sheet["skyline"].insert(position["index"], new_node)
    index = position["index"] + 1
    while index < len(sheet["skyline"]):
        previous = sheet["skyline"][index - 1]
        current = sheet["skyline"][index]
        if current["x"] < previous["x"] + previous["w"]:
            shrink = previous["x"] + previous["w"] - current["x"]
            current["x"] += shrink
            current["w"] -= shrink
            if current["w"] <= 0:
                sheet["skyline"].pop(index)
                continue
            break
        break
    skyline_merge(sheet)


def pack_skyline(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    mode: str,
) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    for piece in pieces:
        placed = False
        for sheet in sheets:
            position = skyline_find_position(sheet, piece, mode)
            if position:
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
                skyline_add_level(sheet, position, kerf_cm)
                placed = True
                break
        if not placed:
            sheet = create_skyline_sheet(
                len(sheets) + 1,
                board_w_cm,
                board_h_cm,
            )
            position = skyline_find_position(sheet, piece, mode)
            if position:
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
                skyline_add_level(sheet, position, kerf_cm)
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("skyline", None)
    return {"sheets": sheets, "unplaced": unplaced}


__all__ = [
    "create_skyline_sheet",
    "pack_skyline",
    "skyline_add_level",
    "skyline_find_position",
    "skyline_merge",
    "skyline_rect_fits",
]
