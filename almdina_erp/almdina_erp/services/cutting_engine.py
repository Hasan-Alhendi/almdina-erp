from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

PACKING_OPTIONS = (
    "Auto",
    "MaxRects Best Short Side",
    "MaxRects Best Area",
    "MaxRects Bottom Left",
    "MaxRects Contact Point",
    "MaxRects Width",
    "MaxRects Length",
    "Shelf Horizontal",
    "Shelf Vertical",
    "Shelf First Fit",
    "Shelf Next Fit",
    "Guillotine Short Axis",
    "Guillotine Long Axis",
    "Guillotine Best Area Fit",
    "Guillotine Best Short Side Fit",
    "Guillotine Best Long Side Fit",
    "Skyline Bottom Left",
    "Skyline Best Fit",
)


def num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        if not value:
            return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def round_value(value: Any, decimals: int = 3) -> float:
    """Match the positive-number rounding behavior used by the legacy JS."""
    factor = 10**decimals
    value_f = num(value)
    if value_f >= 0:
        return math.floor((value_f * factor) + 0.5) / factor
    return math.ceil((value_f * factor) - 0.5) / factor


def normalize_mode(mode: str | None) -> str:
    aliases = {
        "تلقائي": "Auto",
        "MaxRects Area": "MaxRects Best Area",
        "MaxRects Long Side": "MaxRects Best Short Side",
    }
    return aliases.get(mode or "", mode or "Auto")


def clone_pieces(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return deepcopy(pieces)


def expand_piece_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    serial = 1
    for row_index, row in enumerate(rows or []):
        qty = max(0, math.floor(num(row.get("qty"))))
        width_cm = num(row.get("width_cm"))
        length_cm = num(row.get("length_cm"))
        group_no = row_index + 1

        if not width_cm or not length_cm or not qty:
            continue

        for copy_no in range(1, qty + 1):
            pieces.append(
                {
                    "id": serial,
                    "label": f"{group_no}.{copy_no}",
                    "source_piece_no": group_no,
                    "copy_no": copy_no,
                    "group_qty": qty,
                    "width_cm": width_cm,
                    "length_cm": length_cm,
                    "allow_rotation": 1 if row.get("allow_rotation") else 0,
                    "area_m2": (width_cm * length_cm) / 10000,
                    "notes": row.get("notes") or "",
                    "edge_long_right": 1 if row.get("edge_long_right") else 0,
                    "edge_long_left": 1 if row.get("edge_long_left") else 0,
                    "edge_width_top": 1 if row.get("edge_width_top") else 0,
                    "edge_width_bottom": 1 if row.get("edge_width_bottom") else 0,
                    "edge_type": row.get("edge_type") or "",
                    "edge_rate_usd": num(row.get("edge_rate_usd")),
                    "edge_cost_usd": num(row.get("edge_cost_usd")),
                }
            )
            serial += 1
    return pieces


def orientations_for(piece: dict[str, Any]) -> list[dict[str, Any]]:
    result = [
        {
            "w": num(piece.get("width_cm")),
            "h": num(piece.get("length_cm")),
            "rotated": False,
        }
    ]
    if piece.get("allow_rotation") and num(piece.get("width_cm")) != num(piece.get("length_cm")):
        result.append(
            {
                "w": num(piece.get("length_cm")),
                "h": num(piece.get("width_cm")),
                "rotated": True,
            }
        )
    return result


def make_placed_piece(
    piece: dict[str, Any], x: float, y: float, w: float, h: float, rotated: bool
) -> dict[str, Any]:
    return {
        "id": piece["id"],
        "label": piece["label"],
        "source_piece_no": piece["source_piece_no"],
        "copy_no": piece["copy_no"],
        "group_qty": piece["group_qty"],
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "original_w": num(piece.get("width_cm")),
        "original_h": num(piece.get("length_cm")),
        "rotated": bool(rotated),
        "area_m2": num(piece.get("area_m2")),
        "notes": piece.get("notes") or "",
        "edge_long_right": 1 if piece.get("edge_long_right") else 0,
        "edge_long_left": 1 if piece.get("edge_long_left") else 0,
        "edge_width_top": 1 if piece.get("edge_width_top") else 0,
        "edge_width_bottom": 1 if piece.get("edge_width_bottom") else 0,
        "edge_type": piece.get("edge_type") or "",
        "edge_rate_usd": num(piece.get("edge_rate_usd")),
        "edge_cost_usd": num(piece.get("edge_cost_usd")),
    }


def sort_pieces(pieces: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    items = clone_pieces(pieces)
    if method == "area_desc":
        items.sort(key=lambda p: num(p.get("width_cm")) * num(p.get("length_cm")), reverse=True)
    elif method == "long_side_desc":
        items.sort(key=lambda p: max(num(p.get("width_cm")), num(p.get("length_cm"))), reverse=True)
    elif method == "length_desc":
        items.sort(key=lambda p: num(p.get("length_cm")), reverse=True)
    elif method == "width_desc":
        items.sort(key=lambda p: num(p.get("width_cm")), reverse=True)
    elif method == "perimeter_desc":
        items.sort(
            key=lambda p: (num(p.get("width_cm")) + num(p.get("length_cm"))) * 2,
            reverse=True,
        )
    return items


def create_sheet(sheet_no: int, board_w_cm: float, board_h_cm: float) -> dict[str, Any]:
    return {
        "sheet_no": sheet_no,
        "w": board_w_cm,
        "h": board_h_cm,
        "pieces": [],
        "free_rects": [{"x": 0.0, "y": 0.0, "w": board_w_cm, "h": board_h_cm}],
    }


def rect_intersects(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        b["x"] >= a["x"] + a["w"]
        or b["x"] + b["w"] <= a["x"]
        or b["y"] >= a["y"] + a["h"]
        or b["y"] + b["h"] <= a["y"]
    )


def is_contained(a: dict[str, float], b: dict[str, float]) -> bool:
    return (
        a["x"] >= b["x"]
        and a["y"] >= b["y"]
        and a["x"] + a["w"] <= b["x"] + b["w"]
        and a["y"] + a["h"] <= b["y"] + b["h"]
    )


def split_free_rect(free: dict[str, float], used: dict[str, float]) -> list[dict[str, float]]:
    if not rect_intersects(free, used):
        return [free]

    result: list[dict[str, float]] = []
    min_size = 0.01

    if used["x"] > free["x"]:
        result.append({"x": free["x"], "y": free["y"], "w": used["x"] - free["x"], "h": free["h"]})
    if used["x"] + used["w"] < free["x"] + free["w"]:
        result.append(
            {
                "x": used["x"] + used["w"],
                "y": free["y"],
                "w": (free["x"] + free["w"]) - (used["x"] + used["w"]),
                "h": free["h"],
            }
        )
    if used["y"] > free["y"]:
        result.append({"x": free["x"], "y": free["y"], "w": free["w"], "h": used["y"] - free["y"]})
    if used["y"] + used["h"] < free["y"] + free["h"]:
        result.append(
            {
                "x": free["x"],
                "y": used["y"] + used["h"],
                "w": free["w"],
                "h": (free["y"] + free["h"]) - (used["y"] + used["h"]),
            }
        )
    return [r for r in result if r["w"] > min_size and r["h"] > min_size]


def prune_free_rects(free_rects: list[dict[str, float]]) -> list[dict[str, float]]:
    pruned: list[dict[str, float]] = []
    for i, rect in enumerate(free_rects):
        if any(i != j and is_contained(rect, other) for j, other in enumerate(free_rects)):
            continue
        pruned.append(rect)
    return pruned


def contact_point_score(sheet: dict[str, Any], x: float, y: float, w: float, h: float) -> float:
    score = 0.0
    if x == 0 or round_value(x + w, 3) == round_value(sheet["w"], 3):
        score += h
    if y == 0 or round_value(y + h, 3) == round_value(sheet["h"], 3):
        score += w

    for p in sheet["pieces"]:
        if round_value(p["x"] + p["w"], 3) == round_value(x, 3) or round_value(x + w, 3) == round_value(p["x"], 3):
            score += max(0.0, min(y + h, p["y"] + p["h"]) - max(y, p["y"]))
        if round_value(p["y"] + p["h"], 3) == round_value(y, 3) or round_value(y + h, 3) == round_value(p["y"], 3):
            score += max(0.0, min(x + w, p["x"] + p["w"]) - max(x, p["x"]))
    return score


def maxrects_score(sheet: dict[str, Any], free: dict[str, float], orientation: dict[str, Any], heuristic: str) -> float:
    leftover_area = (free["w"] * free["h"]) - (orientation["w"] * orientation["h"])
    short_side = min(free["w"] - orientation["w"], free["h"] - orientation["h"])
    long_side = max(free["w"] - orientation["w"], free["h"] - orientation["h"])
    if heuristic == "best_area":
        return leftover_area * 100000 + short_side * 100 + long_side
    if heuristic == "bottom_left":
        return free["y"] * 100000 + free["x"]
    if heuristic == "contact_point":
        contact = contact_point_score(sheet, free["x"], free["y"], orientation["w"], orientation["h"])
        return -contact * 100000 + leftover_area
    return short_side * 100000 + long_side * 100 + leftover_area


def find_best_position_maxrects(sheet: dict[str, Any], piece: dict[str, Any], heuristic: str) -> dict[str, Any] | None:
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


def place_piece_maxrects(sheet: dict[str, Any], piece: dict[str, Any], position: dict[str, Any], kerf_cm: float) -> None:
    sheet["pieces"].append(
        make_placed_piece(piece, position["x"], position["y"], position["w"], position["h"], position["rotated"])
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


def pack_maxrects(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float, heuristic: str) -> dict[str, Any]:
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


def pack_shelf_horizontal(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    def new_sheet() -> dict[str, Any]:
        return {"sheet_no": len(sheets) + 1, "w": board_w_cm, "h": board_h_cm, "pieces": [], "_x": 0.0, "_y": 0.0, "_row_h": 0.0}

    def try_place(sheet: dict[str, Any], piece: dict[str, Any]) -> bool:
        for o in orientations_for(piece):
            if sheet["_x"] + o["w"] <= board_w_cm and sheet["_y"] + o["h"] <= board_h_cm:
                sheet["pieces"].append(make_placed_piece(piece, sheet["_x"], sheet["_y"], o["w"], o["h"], o["rotated"]))
                sheet["_x"] += o["w"] + kerf_cm
                sheet["_row_h"] = max(sheet["_row_h"], o["h"] + kerf_cm)
                return True
        sheet["_x"] = 0.0
        sheet["_y"] += sheet["_row_h"]
        sheet["_row_h"] = 0.0
        for o in orientations_for(piece):
            if sheet["_x"] + o["w"] <= board_w_cm and sheet["_y"] + o["h"] <= board_h_cm:
                sheet["pieces"].append(make_placed_piece(piece, sheet["_x"], sheet["_y"], o["w"], o["h"], o["rotated"]))
                sheet["_x"] += o["w"] + kerf_cm
                sheet["_row_h"] = max(sheet["_row_h"], o["h"] + kerf_cm)
                return True
        return False

    for piece in pieces:
        placed = False
        for sheet in sheets:
            if try_place(sheet, piece):
                placed = True
                break
        if not placed:
            sheet = new_sheet()
            if try_place(sheet, piece):
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("_x", None)
        sheet.pop("_y", None)
        sheet.pop("_row_h", None)
    return {"sheets": sheets, "unplaced": unplaced}


def pack_shelf_vertical(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    def new_sheet() -> dict[str, Any]:
        return {"sheet_no": len(sheets) + 1, "w": board_w_cm, "h": board_h_cm, "pieces": [], "_x": 0.0, "_y": 0.0, "_col_w": 0.0}

    def try_place(sheet: dict[str, Any], piece: dict[str, Any]) -> bool:
        for o in orientations_for(piece):
            if sheet["_x"] + o["w"] <= board_w_cm and sheet["_y"] + o["h"] <= board_h_cm:
                sheet["pieces"].append(make_placed_piece(piece, sheet["_x"], sheet["_y"], o["w"], o["h"], o["rotated"]))
                sheet["_y"] += o["h"] + kerf_cm
                sheet["_col_w"] = max(sheet["_col_w"], o["w"] + kerf_cm)
                return True
        sheet["_y"] = 0.0
        sheet["_x"] += sheet["_col_w"]
        sheet["_col_w"] = 0.0
        for o in orientations_for(piece):
            if sheet["_x"] + o["w"] <= board_w_cm and sheet["_y"] + o["h"] <= board_h_cm:
                sheet["pieces"].append(make_placed_piece(piece, sheet["_x"], sheet["_y"], o["w"], o["h"], o["rotated"]))
                sheet["_y"] += o["h"] + kerf_cm
                sheet["_col_w"] = max(sheet["_col_w"], o["w"] + kerf_cm)
                return True
        return False

    for piece in pieces:
        placed = False
        for sheet in sheets:
            if try_place(sheet, piece):
                placed = True
                break
        if not placed:
            sheet = new_sheet()
            if try_place(sheet, piece):
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("_x", None)
        sheet.pop("_y", None)
        sheet.pop("_col_w", None)
    return {"sheets": sheets, "unplaced": unplaced}


def pack_shelf_first_fit(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []

    def new_sheet() -> dict[str, Any]:
        return {"sheet_no": len(sheets) + 1, "w": board_w_cm, "h": board_h_cm, "pieces": [], "shelves": []}

    def try_place(sheet: dict[str, Any], piece: dict[str, Any]) -> bool:
        for shelf in sheet["shelves"]:
            for o in orientations_for(piece):
                if o["h"] <= shelf["h"] and shelf["x"] + o["w"] <= board_w_cm:
                    sheet["pieces"].append(make_placed_piece(piece, shelf["x"], shelf["y"], o["w"], o["h"], o["rotated"]))
                    shelf["x"] += o["w"] + kerf_cm
                    return True
        current_y = 0.0
        for shelf in sheet["shelves"]:
            current_y = max(current_y, shelf["y"] + shelf["h"] + kerf_cm)
        for o in orientations_for(piece):
            if current_y + o["h"] <= board_h_cm and o["w"] <= board_w_cm:
                sheet["pieces"].append(make_placed_piece(piece, 0.0, current_y, o["w"], o["h"], o["rotated"]))
                sheet["shelves"].append({"y": current_y, "h": o["h"], "x": o["w"] + kerf_cm})
                return True
        return False

    for piece in pieces:
        placed = False
        for sheet in sheets:
            if try_place(sheet, piece):
                placed = True
                break
        if not placed:
            sheet = new_sheet()
            if try_place(sheet, piece):
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("shelves", None)
    return {"sheets": sheets, "unplaced": unplaced}


def pack_shelf_next_fit(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    sheet: dict[str, Any] | None = None
    x = y = row_h = 0.0

    def start_new_sheet() -> dict[str, Any]:
        nonlocal sheet, x, y, row_h
        sheet = {"sheet_no": len(sheets) + 1, "w": board_w_cm, "h": board_h_cm, "pieces": []}
        sheets.append(sheet)
        x = y = row_h = 0.0
        return sheet

    def place(piece: dict[str, Any], o: dict[str, Any]) -> None:
        nonlocal x, row_h
        assert sheet is not None
        sheet["pieces"].append(make_placed_piece(piece, x, y, o["w"], o["h"], o["rotated"]))
        x += o["w"] + kerf_cm
        row_h = max(row_h, o["h"] + kerf_cm)

    for piece in pieces:
        if sheet is None:
            start_new_sheet()
        placed = False
        for o in orientations_for(piece):
            if x + o["w"] <= board_w_cm and y + o["h"] <= board_h_cm:
                place(piece, o)
                placed = True
                break
        if not placed:
            x = 0.0
            y += row_h
            row_h = 0.0
            for o in orientations_for(piece):
                if x + o["w"] <= board_w_cm and y + o["h"] <= board_h_cm:
                    place(piece, o)
                    placed = True
                    break
        if not placed:
            start_new_sheet()
            for o in orientations_for(piece):
                if x + o["w"] <= board_w_cm and y + o["h"] <= board_h_cm:
                    place(piece, o)
                    placed = True
                    break
        if not placed:
            unplaced.append(piece)
    return {"sheets": sheets, "unplaced": unplaced}


def find_best_position_guillotine(sheet: dict[str, Any], piece: dict[str, Any], fit_mode: str) -> dict[str, Any] | None:
    best = None
    for free_index, free in enumerate(sheet["free_rects"]):
        for o in orientations_for(piece):
            if o["w"] <= free["w"] and o["h"] <= free["h"]:
                leftover_area = (free["w"] * free["h"]) - (o["w"] * o["h"])
                short_side = min(free["w"] - o["w"], free["h"] - o["h"])
                long_side = max(free["w"] - o["w"], free["h"] - o["h"])
                score = leftover_area * 1000 + short_side
                if fit_mode == "best_area":
                    score = leftover_area * 100000 + short_side
                if fit_mode == "best_short_side":
                    score = short_side * 100000 + leftover_area
                if fit_mode == "best_long_side":
                    score = long_side * 100000 + leftover_area
                if best is None or score < best["score"]:
                    best = {"x": free["x"], "y": free["y"], "w": o["w"], "h": o["h"], "rotated": o["rotated"], "free_index": free_index, "score": score}
    return best


def place_piece_guillotine(sheet: dict[str, Any], piece: dict[str, Any], position: dict[str, Any], kerf_cm: float, split_mode: str) -> None:
    sheet["pieces"].append(make_placed_piece(piece, position["x"], position["y"], position["w"], position["h"], position["rotated"]))
    free = sheet["free_rects"].pop(position["free_index"])
    remaining_w = free["w"] - position["w"] - kerf_cm
    remaining_h = free["h"] - position["h"] - kerf_cm
    min_size = 0.01
    right_full = {"x": free["x"] + position["w"] + kerf_cm, "y": free["y"], "w": remaining_w, "h": free["h"]}
    bottom_trimmed = {"x": free["x"], "y": free["y"] + position["h"] + kerf_cm, "w": position["w"], "h": remaining_h}
    right_trimmed = {"x": free["x"] + position["w"] + kerf_cm, "y": free["y"], "w": remaining_w, "h": position["h"]}
    bottom_full = {"x": free["x"], "y": free["y"] + position["h"] + kerf_cm, "w": free["w"], "h": remaining_h}

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


def pack_guillotine(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float, split_mode: str, fit_mode: str) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    for piece in pieces:
        placed = False
        for sheet in sheets:
            pos = find_best_position_guillotine(sheet, piece, fit_mode)
            if pos:
                place_piece_guillotine(sheet, piece, pos, kerf_cm, split_mode)
                placed = True
                break
        if not placed:
            sheet = create_sheet(len(sheets) + 1, board_w_cm, board_h_cm)
            pos = find_best_position_guillotine(sheet, piece, fit_mode)
            if pos:
                place_piece_guillotine(sheet, piece, pos, kerf_cm, split_mode)
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    return {"sheets": sheets, "unplaced": unplaced}


def create_skyline_sheet(sheet_no: int, board_w_cm: float, board_h_cm: float) -> dict[str, Any]:
    return {"sheet_no": sheet_no, "w": board_w_cm, "h": board_h_cm, "pieces": [], "skyline": [{"x": 0.0, "y": 0.0, "w": board_w_cm}]}


def skyline_rect_fits(sheet: dict[str, Any], index: int, w: float, h: float) -> dict[str, float] | None:
    x = sheet["skyline"][index]["x"]
    if x + w > sheet["w"]:
        return None
    width_left = w
    y = sheet["skyline"][index]["y"]
    i = index
    while width_left > 0:
        if i >= len(sheet["skyline"]):
            return None
        y = max(y, sheet["skyline"][i]["y"])
        if y + h > sheet["h"]:
            return None
        width_left -= sheet["skyline"][i]["w"]
        i += 1
    return {"x": x, "y": y}


def skyline_find_position(sheet: dict[str, Any], piece: dict[str, Any], mode: str) -> dict[str, Any] | None:
    best = None
    for index in range(len(sheet["skyline"])):
        for o in orientations_for(piece):
            pos = skyline_rect_fits(sheet, index, o["w"], o["h"])
            if not pos:
                continue
            if mode == "best_fit":
                waste = pos["y"] * sheet["w"]
                score = pos["y"] * 100000 + waste + pos["x"]
            else:
                score = pos["y"] * 100000 + pos["x"]
            if best is None or score < best["score"]:
                best = {"index": index, "x": pos["x"], "y": pos["y"], "w": o["w"], "h": o["h"], "rotated": o["rotated"], "score": score}
    return best


def skyline_merge(sheet: dict[str, Any]) -> None:
    i = 0
    while i < len(sheet["skyline"]) - 1:
        if round_value(sheet["skyline"][i]["y"], 3) == round_value(sheet["skyline"][i + 1]["y"], 3):
            sheet["skyline"][i]["w"] += sheet["skyline"][i + 1]["w"]
            sheet["skyline"].pop(i + 1)
        else:
            i += 1


def skyline_add_level(sheet: dict[str, Any], pos: dict[str, Any], kerf_cm: float) -> None:
    new_node = {"x": pos["x"], "y": pos["y"] + pos["h"] + kerf_cm, "w": min(pos["w"] + kerf_cm, sheet["w"] - pos["x"])}
    sheet["skyline"].insert(pos["index"], new_node)
    i = pos["index"] + 1
    while i < len(sheet["skyline"]):
        prev = sheet["skyline"][i - 1]
        curr = sheet["skyline"][i]
        if curr["x"] < prev["x"] + prev["w"]:
            shrink = prev["x"] + prev["w"] - curr["x"]
            curr["x"] += shrink
            curr["w"] -= shrink
            if curr["w"] <= 0:
                sheet["skyline"].pop(i)
                continue
            break
        break
    skyline_merge(sheet)


def pack_skyline(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float, mode: str) -> dict[str, Any]:
    sheets: list[dict[str, Any]] = []
    unplaced: list[dict[str, Any]] = []
    for piece in pieces:
        placed = False
        for sheet in sheets:
            pos = skyline_find_position(sheet, piece, mode)
            if pos:
                sheet["pieces"].append(make_placed_piece(piece, pos["x"], pos["y"], pos["w"], pos["h"], pos["rotated"]))
                skyline_add_level(sheet, pos, kerf_cm)
                placed = True
                break
        if not placed:
            sheet = create_skyline_sheet(len(sheets) + 1, board_w_cm, board_h_cm)
            pos = skyline_find_position(sheet, piece, mode)
            if pos:
                sheet["pieces"].append(make_placed_piece(piece, pos["x"], pos["y"], pos["w"], pos["h"], pos["rotated"]))
                skyline_add_level(sheet, pos, kerf_cm)
                sheets.append(sheet)
            else:
                unplaced.append(piece)
    for sheet in sheets:
        sheet.pop("skyline", None)
    return {"sheets": sheets, "unplaced": unplaced}


def evaluate_plan(plan: dict[str, Any], pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, method_label: str, method_key: str, complexity: int = 1) -> dict[str, Any]:
    used_area = sum(num(p.get("area_m2")) for p in pieces)
    total_board_area = len(plan["sheets"]) * (board_w_cm * board_h_cm / 10000)
    waste_area = max(0.0, total_board_area - used_area)
    score = len(plan["unplaced"]) * 1_000_000_000 + len(plan["sheets"]) * 1_000_000 + waste_area * 1000 + complexity
    return {
        "method_key": method_key,
        "method_label": method_label,
        "sheets": plan["sheets"],
        "unplaced": plan["unplaced"],
        "used_area_m2": used_area,
        "total_board_area_m2": total_board_area,
        "waste_area_m2": waste_area,
        "score": score,
        "complexity": complexity,
    }


def run_single_method(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float, method_key: str) -> dict[str, Any]:
    method_key = normalize_mode(method_key)
    configs: dict[str, tuple[str, str, Any, tuple[Any, ...], int]] = {
        "MaxRects Best Short Side": ("area_desc", "MaxRects - Best Short Side", pack_maxrects, ("best_short_side",), 3),
        "MaxRects Best Area": ("area_desc", "MaxRects - Best Area", pack_maxrects, ("best_area",), 4),
        "MaxRects Bottom Left": ("long_side_desc", "MaxRects - Bottom Left", pack_maxrects, ("bottom_left",), 5),
        "MaxRects Contact Point": ("area_desc", "MaxRects - Contact Point", pack_maxrects, ("contact_point",), 4),
        "MaxRects Width": ("width_desc", "MaxRects - الأعرض أولاً", pack_maxrects, ("best_short_side",), 3),
        "MaxRects Length": ("length_desc", "MaxRects - الأطول أولاً", pack_maxrects, ("best_short_side",), 3),
        "Shelf Horizontal": ("long_side_desc", "Shelf Packing - صفوف أفقية", pack_shelf_horizontal, (), 20),
        "Shelf Vertical": ("long_side_desc", "Shelf Packing - أعمدة عمودية", pack_shelf_vertical, (), 20),
        "Shelf First Fit": ("long_side_desc", "Shelf Packing - First Fit", pack_shelf_first_fit, (), 18),
        "Shelf Next Fit": ("long_side_desc", "Shelf Packing - Next Fit", pack_shelf_next_fit, (), 22),
        "Guillotine Short Axis": ("area_desc", "Guillotine - Short Axis Split", pack_guillotine, ("short_axis", "best_area"), 10),
        "Guillotine Long Axis": ("area_desc", "Guillotine - Long Axis Split", pack_guillotine, ("long_axis", "best_area"), 10),
        "Guillotine Best Area Fit": ("area_desc", "Guillotine - Best Area Fit", pack_guillotine, ("short_axis", "best_area"), 9),
        "Guillotine Best Short Side Fit": ("long_side_desc", "Guillotine - Best Short Side Fit", pack_guillotine, ("short_axis", "best_short_side"), 9),
        "Guillotine Best Long Side Fit": ("long_side_desc", "Guillotine - Best Long Side Fit", pack_guillotine, ("long_axis", "best_long_side"), 9),
        "Skyline Bottom Left": ("long_side_desc", "Skyline - Bottom Left", pack_skyline, ("bottom_left",), 12),
        "Skyline Best Fit": ("area_desc", "Skyline - Best Fit", pack_skyline, ("best_fit",), 12),
    }
    if method_key not in configs:
        return run_single_method(pieces, board_w_cm, board_h_cm, kerf_cm, "MaxRects Best Short Side")
    sort_method, label, packer, args, complexity = configs[method_key]
    sorted_pieces = sort_pieces(pieces, sort_method)
    plan = packer(sorted_pieces, board_w_cm, board_h_cm, kerf_cm, *args)
    return evaluate_plan(plan, pieces, board_w_cm, board_h_cm, label, method_key, complexity)


def choose_best_plan(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float, selected_mode: str | None = "Auto") -> dict[str, Any]:
    mode = normalize_mode(selected_mode)
    if mode != "Auto":
        return run_single_method(pieces, board_w_cm, board_h_cm, kerf_cm, mode)
    best = None
    for method in PACKING_OPTIONS[1:]:
        result = run_single_method(pieces, board_w_cm, board_h_cm, kerf_cm, method)
        if best is None or result["score"] < best["score"]:
            best = result
    assert best is not None
    best["method_label"] = "Auto اختار: " + best["method_label"]
    return best


def validate_plan(plan: dict[str, Any], requested_pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, tolerance: float = 1e-7) -> list[str]:
    """Independent geometry validator required before a plan can be approved."""
    errors: list[str] = []
    expected = {int(p["id"]): p for p in requested_pieces}
    seen: dict[int, int] = {}

    for sheet in plan.get("sheets", []):
        pieces = sheet.get("pieces", [])
        for placed in pieces:
            piece_id = int(placed["id"])
            seen[piece_id] = seen.get(piece_id, 0) + 1
            x, y, w, h = map(num, (placed.get("x"), placed.get("y"), placed.get("w"), placed.get("h")))
            if x < -tolerance or y < -tolerance or x + w > board_w_cm + tolerance or y + h > board_h_cm + tolerance:
                errors.append(f"Piece {placed.get('label')} exceeds usable board bounds on sheet {sheet.get('sheet_no')}.")
            source = expected.get(piece_id)
            if not source:
                errors.append(f"Unknown piece id {piece_id} exists in plan.")
                continue
            allowed = {(num(source["width_cm"]), num(source["length_cm"]), False)}
            if source.get("allow_rotation") and num(source["width_cm"]) != num(source["length_cm"]):
                allowed.add((num(source["length_cm"]), num(source["width_cm"]), True))
            actual = (w, h, bool(placed.get("rotated")))
            if not any(abs(actual[0] - a[0]) <= tolerance and abs(actual[1] - a[1]) <= tolerance and actual[2] == a[2] for a in allowed):
                errors.append(f"Piece {placed.get('label')} has invalid dimensions or rotation state.")

        for i, first in enumerate(pieces):
            a = {"x": num(first["x"]), "y": num(first["y"]), "w": num(first["w"]), "h": num(first["h"])}
            for second in pieces[i + 1 :]:
                b = {"x": num(second["x"]), "y": num(second["y"]), "w": num(second["w"]), "h": num(second["h"])}
                if rect_intersects(a, b):
                    errors.append(f"Pieces {first.get('label')} and {second.get('label')} overlap on sheet {sheet.get('sheet_no')}.")

    for piece_id, piece in expected.items():
        count = seen.get(piece_id, 0)
        if count != 1:
            errors.append(f"Piece {piece.get('label')} appears {count} times; expected exactly once.")

    if plan.get("unplaced"):
        errors.append(f"Plan contains {len(plan['unplaced'])} unplaced piece(s).")
    return errors
