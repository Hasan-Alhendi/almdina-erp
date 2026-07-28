from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


class CostingError(ValueError):
    """Raised when costing inputs violate a business rule."""


@dataclass(frozen=True, slots=True)
class PieceCostInput:
    width_cm: float
    length_cm: float
    qty: int
    edge_long_right: int
    edge_long_left: int
    edge_width_top: int
    edge_width_bottom: int
    edge_type: str = ""


@dataclass(frozen=True, slots=True)
class PieceCostResult:
    area_m2: float
    edge_meters: float
    edge_rate_usd: float
    edge_cost_usd: float


@dataclass(frozen=True, slots=True)
class PieceCostSummary:
    pieces: tuple[PieceCostResult, ...]
    total_area_m2: float
    total_edge_meters: float
    total_edge_cost_usd: float


@dataclass(frozen=True, slots=True)
class OrderCostSummary:
    required_boards: int
    mdf_cost_usd: float
    cutting_cost_usd: float
    edge_cost_usd: float
    total_cost_usd: float


@dataclass(frozen=True, slots=True)
class WasteSummary:
    waste_area_m2: float
    waste_percent: float


@dataclass(frozen=True, slots=True)
class SpecialPricingSettings:
    design_fee_usd: float = 0
    cnc_fee_usd: float = 0
    manual_edge_fee_usd: float = 0
    margin_percent: float = 0


@dataclass(frozen=True, slots=True)
class SpecialPricingPieceInput:
    piece_type: str
    qty: int
    area_m2: float
    edge_cost_usd: float
    price_status: str = ""
    approved_by: str = ""
    custom_unit_price_usd: float = 0


@dataclass(frozen=True, slots=True)
class SpecialPricingPieceResult:
    applicable: bool
    estimated_unit_price_usd: float
    final_unit_price_usd: float
    price_status: str
    preserve_approval: bool


@dataclass(frozen=True, slots=True)
class SpecialPricingSummary:
    pieces: tuple[SpecialPricingPieceResult, ...]
    baseline_cost_usd: float
    estimated_total_usd: float
    final_total_usd: float
    customer_quote_total_usd: float
    customer_quote_status: str


def round_value(value: float, decimals: int = 3) -> float:
    """Preserve the legacy half-away-from-zero rounding contract."""

    factor = 10**decimals
    number = _finite(value)
    if number >= 0:
        return math.floor((number * factor) + 0.5) / factor
    return math.ceil((number * factor) - 0.5) / factor


def calculate_piece_costs(
    pieces: Iterable[PieceCostInput],
    *,
    default_edge_type: str,
    edge_rates: Mapping[str, float],
) -> PieceCostSummary:
    results: list[PieceCostResult] = []
    total_area = 0.0
    total_edge_meters = 0.0
    total_edge_cost = 0.0

    for piece in pieces:
        width_cm = _finite(piece.width_cm)
        length_cm = _finite(piece.length_cm)
        qty = int(piece.qty)
        long_edges = int(piece.edge_long_right) + int(piece.edge_long_left)
        width_edges = int(piece.edge_width_top) + int(piece.edge_width_bottom)

        area_m2 = (width_cm * length_cm * qty) / 10000
        edge_meters = (((length_cm * long_edges) + (width_cm * width_edges)) * qty) / 100
        effective_edge_type = piece.edge_type or default_edge_type
        edge_rate = _finite(edge_rates.get(effective_edge_type, 0.0)) if effective_edge_type else 0.0
        edge_cost = edge_meters * edge_rate

        results.append(
            PieceCostResult(
                area_m2=round_value(area_m2, 3),
                edge_meters=round_value(edge_meters, 3),
                edge_rate_usd=edge_rate,
                edge_cost_usd=round_value(edge_cost, 3),
            )
        )
        total_area += area_m2
        total_edge_meters += edge_meters
        total_edge_cost += edge_cost

    return PieceCostSummary(
        pieces=tuple(results),
        total_area_m2=round_value(total_area, 3),
        total_edge_meters=round_value(total_edge_meters, 3),
        total_edge_cost_usd=round_value(total_edge_cost, 3),
    )


def calculate_order_costs(
    *,
    required_boards: int,
    board_rate_usd: float,
    cutting_cost_per_board_usd: float,
    edge_cost_usd: float,
) -> OrderCostSummary:
    boards = max(0, int(required_boards))
    board_rate = _finite(board_rate_usd)
    cutting_rate = _finite(cutting_cost_per_board_usd)
    edge_cost = _finite(edge_cost_usd)
    mdf_cost = boards * board_rate
    cutting_cost = boards * cutting_rate
    return OrderCostSummary(
        required_boards=boards,
        mdf_cost_usd=round_value(mdf_cost, 3),
        cutting_cost_usd=round_value(cutting_cost, 3),
        edge_cost_usd=round_value(edge_cost, 3),
        total_cost_usd=round_value(mdf_cost + cutting_cost + edge_cost, 3),
    )


def calculate_waste(*, waste_area_m2: float, total_board_area_m2: float) -> WasteSummary:
    waste_area = max(0.0, _finite(waste_area_m2))
    total_board_area = _finite(total_board_area_m2)
    waste_percent = (waste_area / total_board_area * 100) if total_board_area else 0.0
    return WasteSummary(
        waste_area_m2=round_value(waste_area, 3),
        waste_percent=round_value(waste_percent, 2),
    )


def calculate_special_pricing(
    pieces: Iterable[SpecialPricingPieceInput],
    *,
    settings: SpecialPricingSettings,
    total_area_m2: float,
    board_and_cutting_cost_usd: float,
    total_cost_usd: float,
) -> SpecialPricingSummary:
    piece_list = tuple(pieces)
    fees = (
        _finite(settings.design_fee_usd),
        _finite(settings.cnc_fee_usd),
        _finite(settings.manual_edge_fee_usd),
        _finite(settings.margin_percent),
    )
    if min(fees) < 0:
        raise CostingError("special_shape_defaults_negative")

    special_indexes = [
        index for index, piece in enumerate(piece_list) if (piece.piece_type or "Regular") == "Special"
    ]
    if not special_indexes:
        return SpecialPricingSummary(
            pieces=tuple(
                SpecialPricingPieceResult(
                    applicable=False,
                    estimated_unit_price_usd=0,
                    final_unit_price_usd=0,
                    price_status="Not Applicable",
                    preserve_approval=False,
                )
                for _piece in piece_list
            ),
            baseline_cost_usd=0,
            estimated_total_usd=0,
            final_total_usd=0,
            customer_quote_total_usd=round_value(total_cost_usd, 3),
            customer_quote_status="Automatic",
        )

    total_area = _finite(total_area_m2)
    board_and_cutting_cost = _finite(board_and_cutting_cost_usd)
    results: list[SpecialPricingPieceResult] = []
    baseline_total = 0.0
    estimated_total = 0.0
    final_total = 0.0
    approved_count = 0
    regular_edge_total = 0.0

    for piece in piece_list:
        if (piece.piece_type or "Regular") != "Special":
            regular_edge_total += _finite(piece.edge_cost_usd)
            results.append(
                SpecialPricingPieceResult(
                    applicable=False,
                    estimated_unit_price_usd=0,
                    final_unit_price_usd=0,
                    price_status="Not Applicable",
                    preserve_approval=False,
                )
            )
            continue

        qty = max(1, int(piece.qty))
        area_share = (_finite(piece.area_m2) / total_area) if total_area else 0
        allocated_total = (board_and_cutting_cost * area_share) + _finite(piece.edge_cost_usd)
        baseline_unit = allocated_total / qty
        estimated_unit = (
            baseline_unit + fees[0] + fees[1] + fees[2]
        ) * (1 + (fees[3] / 100))
        estimated_unit = round_value(estimated_unit, 3)
        approved = bool(piece.price_status == "Approved" and piece.approved_by)
        final_unit = _finite(piece.custom_unit_price_usd) if approved else estimated_unit

        if approved:
            approved_count += 1
        results.append(
            SpecialPricingPieceResult(
                applicable=True,
                estimated_unit_price_usd=estimated_unit,
                final_unit_price_usd=round_value(final_unit, 3),
                price_status="Approved" if approved else "Estimated",
                preserve_approval=approved,
            )
        )
        baseline_total += allocated_total
        estimated_total += estimated_unit * qty
        final_total += final_unit * qty

    special_count = len(special_indexes)
    if approved_count == special_count:
        quote_status = "Approved"
    elif approved_count:
        quote_status = "Partially Approved"
    else:
        quote_status = "Estimated"

    invoice_base_total = board_and_cutting_cost + regular_edge_total
    return SpecialPricingSummary(
        pieces=tuple(results),
        baseline_cost_usd=round_value(baseline_total, 3),
        estimated_total_usd=round_value(estimated_total, 3),
        final_total_usd=round_value(final_total, 3),
        customer_quote_total_usd=round_value(invoice_base_total + final_total, 3),
        customer_quote_status=quote_status,
    )


def _finite(value: float) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as error:
        raise CostingError("non_finite_cost_input") from error
    if not math.isfinite(number):
        raise CostingError("non_finite_cost_input")
    return number


__all__ = [
    "CostingError",
    "OrderCostSummary",
    "PieceCostInput",
    "PieceCostResult",
    "PieceCostSummary",
    "SpecialPricingPieceInput",
    "SpecialPricingPieceResult",
    "SpecialPricingSettings",
    "SpecialPricingSummary",
    "WasteSummary",
    "calculate_order_costs",
    "calculate_piece_costs",
    "calculate_special_pricing",
    "calculate_waste",
    "round_value",
]
