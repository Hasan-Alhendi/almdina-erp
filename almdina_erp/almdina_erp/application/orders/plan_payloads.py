from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_text


@dataclass(frozen=True, slots=True)
class PlanBoardInput:
    item: str
    width_mm: float
    length_mm: float


@dataclass(frozen=True, slots=True)
class PlanCutInput:
    kerf_mm: float
    trim_margin_mm: float
    packing_mode: str
    machine_type: str
    time_limit_sec: float


@dataclass(frozen=True, slots=True)
class PlanOptimizerSettings:
    exact_piece_limit: int
    min_remnant_width_mm: float
    min_remnant_length_mm: float
    min_remnant_area_m2: float


@dataclass(frozen=True, slots=True)
class PlanPieceInput:
    index: int
    width_cm: float
    length_cm: float
    qty: int
    allow_rotation: int
    piece_type: str
    clipped_corner_position: str
    clipped_corner_width_cm: float
    clipped_corner_length_cm: float


@dataclass(frozen=True, slots=True)
class PlanMetadataPiece:
    index: int
    piece_type: str
    edge_long_right: int
    edge_long_left: int
    edge_width_top: int
    edge_width_bottom: int
    edge_type: str
    edge_rate_usd: float
    edge_cost_usd: float
    area_m2: float
    notes: str
    drawing_token: str
    special_shape_status: str
    edge_long_type: str = ""
    edge_width_type: str = ""
    edge_long_rate_usd: float = 0
    edge_width_rate_usd: float = 0
    edge_long_cost_usd: float = 0
    edge_width_cost_usd: float = 0


def build_plan_input_payload(
    *,
    version: int,
    board: PlanBoardInput,
    cut: PlanCutInput,
    optimizer: PlanOptimizerSettings,
    pieces: Iterable[PlanPieceInput],
) -> dict[str, Any]:
    return {
        "version": int(version),
        "board": {
            "item": board.item,
            "width_mm": board.width_mm,
            "length_mm": board.length_mm,
        },
        "cut": {
            "kerf_mm": cut.kerf_mm,
            "trim_margin_mm": cut.trim_margin_mm,
            "packing_mode": cut.packing_mode,
            "machine_type": cut.machine_type,
            "time_limit_sec": cut.time_limit_sec,
        },
        "optimizer_settings": {
            "exact_piece_limit": optimizer.exact_piece_limit,
            "min_remnant_width_mm": optimizer.min_remnant_width_mm,
            "min_remnant_length_mm": optimizer.min_remnant_length_mm,
            "min_remnant_area_m2": optimizer.min_remnant_area_m2,
        },
        "pieces": [
            {
                "index": piece.index,
                "width_cm": piece.width_cm,
                "length_cm": piece.length_cm,
                "qty": piece.qty,
                "allow_rotation": piece.allow_rotation,
                "piece_type": piece.piece_type,
                "clipped_corner_position": piece.clipped_corner_position,
                "clipped_corner_width_cm": piece.clipped_corner_width_cm,
                "clipped_corner_length_cm": piece.clipped_corner_length_cm,
            }
            for piece in pieces
        ],
    }


def build_plan_metadata_payload(
    *,
    default_edge_type: str,
    edge_color: str,
    pieces: Iterable[PlanMetadataPiece],
) -> dict[str, Any]:
    return {
        "default_edge_type": default_edge_type,
        "edge_color": edge_color,
        "pieces": [
            {
                "index": piece.index,
                "piece_type": piece.piece_type,
                "edge_long_right": piece.edge_long_right,
                "edge_long_left": piece.edge_long_left,
                "edge_width_top": piece.edge_width_top,
                "edge_width_bottom": piece.edge_width_bottom,
                "edge_long_type": piece.edge_long_type or piece.edge_type,
                "edge_width_type": piece.edge_width_type or piece.edge_type,
                "edge_long_rate_usd": (
                    piece.edge_long_rate_usd
                    if piece.edge_long_type
                    else piece.edge_rate_usd
                ),
                "edge_width_rate_usd": (
                    piece.edge_width_rate_usd
                    if piece.edge_width_type
                    else piece.edge_rate_usd
                ),
                "edge_long_cost_usd": piece.edge_long_cost_usd,
                "edge_width_cost_usd": piece.edge_width_cost_usd,
                "edge_cost_usd": piece.edge_cost_usd,
                "area_m2": piece.area_m2,
                "notes": piece.notes,
                "drawing_hash": fingerprint_text(piece.drawing_token),
                "special_shape_status": piece.special_shape_status,
            }
            for piece in pieces
        ],
    }


__all__ = [
    "PlanBoardInput",
    "PlanCutInput",
    "PlanMetadataPiece",
    "PlanOptimizerSettings",
    "PlanPieceInput",
    "build_plan_input_payload",
    "build_plan_metadata_payload",
]
