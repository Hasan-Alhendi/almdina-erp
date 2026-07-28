from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


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
                    "piece_type": row.get("piece_type") or "Regular",
                    "clipped_corner_position": row.get("clipped_corner_position") or "",
                    "clipped_corner_width_cm": num(row.get("clipped_corner_width_cm")),
                    "clipped_corner_length_cm": num(row.get("clipped_corner_length_cm")),
                    "special_shape_geometry_json": (
                        row.get("special_shape_geometry_json") or ""
                    ),
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
    if piece.get("allow_rotation") and num(piece.get("width_cm")) != num(
        piece.get("length_cm")
    ):
        result.append(
            {
                "w": num(piece.get("length_cm")),
                "h": num(piece.get("width_cm")),
                "rotated": True,
            }
        )
    return result


def make_placed_piece(
    piece: dict[str, Any],
    x: float,
    y: float,
    w: float,
    h: float,
    rotated: bool,
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
        "piece_type": piece.get("piece_type") or "Regular",
        "clipped_corner_position": piece.get("clipped_corner_position") or "",
        "clipped_corner_width_cm": num(piece.get("clipped_corner_width_cm")),
        "clipped_corner_length_cm": num(piece.get("clipped_corner_length_cm")),
        "special_shape_geometry_json": piece.get("special_shape_geometry_json") or "",
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
        items.sort(
            key=lambda p: num(p.get("width_cm")) * num(p.get("length_cm")),
            reverse=True,
        )
    elif method == "long_side_desc":
        items.sort(
            key=lambda p: max(num(p.get("width_cm")), num(p.get("length_cm"))),
            reverse=True,
        )
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


def create_sheet(
    sheet_no: int,
    board_w_cm: float,
    board_h_cm: float,
) -> dict[str, Any]:
    return {
        "sheet_no": sheet_no,
        "w": board_w_cm,
        "h": board_h_cm,
        "pieces": [],
        "free_rects": [
            {"x": 0.0, "y": 0.0, "w": board_w_cm, "h": board_h_cm}
        ],
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


def split_free_rect(
    free: dict[str, float],
    used: dict[str, float],
) -> list[dict[str, float]]:
    if not rect_intersects(free, used):
        return [free]

    result: list[dict[str, float]] = []
    min_size = 0.01

    if used["x"] > free["x"]:
        result.append(
            {
                "x": free["x"],
                "y": free["y"],
                "w": used["x"] - free["x"],
                "h": free["h"],
            }
        )
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
        result.append(
            {
                "x": free["x"],
                "y": free["y"],
                "w": free["w"],
                "h": used["y"] - free["y"],
            }
        )
    if used["y"] + used["h"] < free["y"] + free["h"]:
        result.append(
            {
                "x": free["x"],
                "y": used["y"] + used["h"],
                "w": free["w"],
                "h": (free["y"] + free["h"]) - (used["y"] + used["h"]),
            }
        )
    return [rect for rect in result if rect["w"] > min_size and rect["h"] > min_size]


def prune_free_rects(
    free_rects: list[dict[str, float]],
) -> list[dict[str, float]]:
    pruned: list[dict[str, float]] = []
    for index, rect in enumerate(free_rects):
        if any(
            index != other_index and is_contained(rect, other)
            for other_index, other in enumerate(free_rects)
        ):
            continue
        pruned.append(rect)
    return pruned


__all__ = [
    "clone_pieces",
    "create_sheet",
    "expand_piece_groups",
    "is_contained",
    "make_placed_piece",
    "normalize_mode",
    "num",
    "orientations_for",
    "prune_free_rects",
    "rect_intersects",
    "round_value",
    "sort_pieces",
    "split_free_rect",
]
