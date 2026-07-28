from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PieceMaterialInput:
    edge_type: str
    edge_meters: float


@dataclass(frozen=True, slots=True)
class EdgeMaterialDemand:
    edge_type: str
    meters: float


@dataclass(frozen=True, slots=True)
class MaterialDemand:
    board_item: str
    full_board_count: int
    edge_demands: tuple[EdgeMaterialDemand, ...]


def build_material_demand(
    *,
    board_item: str,
    full_board_count: int,
    default_edge_type: str,
    pieces: Iterable[PieceMaterialInput],
) -> MaterialDemand:
    """Aggregate physical board and edge-band demand without framework access."""

    edge_totals: dict[str, float] = {}
    for piece in pieces:
        edge_type = str(piece.edge_type or default_edge_type or "").strip()
        meters = float(piece.edge_meters or 0)
        if not edge_type or meters <= 0:
            continue
        edge_totals[edge_type] = edge_totals.get(edge_type, 0.0) + meters

    return MaterialDemand(
        board_item=str(board_item or "").strip(),
        full_board_count=max(0, int(full_board_count or 0)),
        edge_demands=tuple(
            EdgeMaterialDemand(edge_type=edge_type, meters=meters)
            for edge_type, meters in edge_totals.items()
        ),
    )


__all__ = [
    "EdgeMaterialDemand",
    "MaterialDemand",
    "PieceMaterialInput",
    "build_material_demand",
]
