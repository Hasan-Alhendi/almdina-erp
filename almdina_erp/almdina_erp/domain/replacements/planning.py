from __future__ import annotations

from typing import Any


ENGINE_VERSION = "1.0.0-baseline"


class ReplacementPlanError(ValueError):
    """Raised when a replacement piece cannot be placed on its board."""


def calculate_edge_meters(
    *,
    width_cm: float,
    length_cm: float,
    edge_long_right: bool,
    edge_long_left: bool,
    edge_width_top: bool,
    edge_width_bottom: bool,
) -> float:
    long_edges = int(bool(edge_long_right)) + int(bool(edge_long_left))
    width_edges = int(bool(edge_width_top)) + int(bool(edge_width_bottom))
    return (
        float(length_cm) * long_edges
        + float(width_cm) * width_edges
    ) / 100


def build_replacement_snapshot(
    *,
    board_description: str,
    board_width_cm: float,
    board_length_cm: float,
    trim_margin_mm: float,
    kerf_mm: float,
    original_piece_label: str,
    piece_width_cm: float,
    piece_length_cm: float,
    allow_rotation: bool,
    edge_long_right: bool,
    edge_long_left: bool,
    edge_width_top: bool,
    edge_width_bottom: bool,
    edge_type: str,
    notes: str,
) -> dict[str, Any]:
    description = str(board_description or "").strip()
    if not description:
        raise ReplacementPlanError("Board description is required.")

    full_width = float(board_width_cm)
    full_length = float(board_length_cm)
    if full_width <= 0 or full_length <= 0:
        raise ReplacementPlanError("Board dimensions must be greater than zero.")

    trim_cm = float(trim_margin_mm) / 10
    kerf_cm = float(kerf_mm) / 10
    usable_width = full_width - (2 * trim_cm)
    usable_length = full_length - (2 * trim_cm)
    if usable_width <= 0 or usable_length <= 0:
        raise ReplacementPlanError(
            "The board has no usable area after Trim Margin."
        )

    original_width = float(piece_width_cm)
    original_length = float(piece_length_cm)
    if original_width <= 0 or original_length <= 0:
        raise ReplacementPlanError(
            "Replacement dimensions must be greater than zero."
        )

    rotated = False
    placed_width = original_width
    placed_length = original_length
    if placed_width > usable_width or placed_length > usable_length:
        can_rotate = (
            bool(allow_rotation)
            and original_length <= usable_width
            and original_width <= usable_length
        )
        if not can_rotate:
            raise ReplacementPlanError(
                f"Replacement piece {original_piece_label} does not fit "
                "the board with the current Trim Margin."
            )
        rotated = True
        placed_width = original_length
        placed_length = original_width

    piece_area = original_width * original_length / 10_000
    board_area = usable_width * usable_length / 10_000
    waste_area = max(0.0, board_area - piece_area)
    piece = {
        "id": 1,
        "label": f"{original_piece_label}-R",
        "source_piece_no": 1,
        "copy_no": 1,
        "group_qty": 1,
        "x": 0.0,
        "y": 0.0,
        "w": placed_width,
        "h": placed_length,
        "original_w": original_width,
        "original_h": original_length,
        "rotated": rotated,
        "area_m2": piece_area,
        "notes": notes or "",
        "edge_long_right": int(bool(edge_long_right)),
        "edge_long_left": int(bool(edge_long_left)),
        "edge_width_top": int(bool(edge_width_top)),
        "edge_width_bottom": int(bool(edge_width_bottom)),
        "edge_type": edge_type or "",
    }
    sheet = {
        "sheet_no": 1,
        "w": usable_width,
        "h": usable_length,
        "pieces": [piece],
        "source_type": "Full Board",
        "board_description": description,
        "full_width_cm": full_width,
        "full_length_cm": full_length,
        "usable_width_cm": usable_width,
        "usable_length_cm": usable_length,
        "source_area_m2": board_area,
    }
    return {
        "engine_version": ENGINE_VERSION,
        "method_key": "Replacement Mini Plan",
        "method_label": "Replacement Mini Plan - Full Board",
        "score": waste_area * 1_000,
        "full_board_width_cm": full_width,
        "full_board_length_cm": full_length,
        "usable_board_width_cm": usable_width,
        "usable_board_length_cm": usable_length,
        "kerf_cm": kerf_cm,
        "trim_cm": trim_cm,
        "used_area_m2": piece_area,
        "total_board_area_m2": board_area,
        "waste_area_m2": waste_area,
        "required_full_boards": 1,
        "sheets": [sheet],
        "unplaced": [],
        "validation": {"is_valid": True, "errors": []},
    }
