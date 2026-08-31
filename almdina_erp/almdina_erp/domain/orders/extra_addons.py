from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .costing import round_value


EXTRA_PIECE_TYPE = "Extra"
EXTRA_ADDON_CODES = (
    "double",
    "full_door_double",
    "liner",
    "recessed_handle_cutout",
)
FULL_DOOR_DOUBLE_CUT_MULTIPLIER = 2


class ExtraAddonError(ValueError):
    """Raised when an Extra-door selection or price violates a domain rule."""

    def __init__(self, code: str, addon_code: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.addon_code = addon_code


@dataclass(frozen=True, slots=True)
class ExtraAddonRates:
    double_usd: float = 0
    full_door_double_usd: float = 0
    liner_usd: float = 0
    recessed_handle_cutout_usd: float = 0


@dataclass(frozen=True, slots=True)
class ExtraAddonPieceInput:
    piece_type: str
    qty: int
    notes: str = ""
    double: bool = False
    full_door_double: bool = False
    liner: bool = False
    recessed_handle_cutout: bool = False
    double_snapshot_unit_price_usd: float | None = None
    full_door_double_snapshot_unit_price_usd: float | None = None
    liner_snapshot_unit_price_usd: float | None = None
    recessed_handle_cutout_snapshot_unit_price_usd: float | None = None


@dataclass(frozen=True, slots=True)
class ExtraAddonPieceResult:
    applicable: bool
    selected_codes: tuple[str, ...]
    double_unit_price_usd: float
    double_total_usd: float
    full_door_double_unit_price_usd: float
    full_door_double_total_usd: float
    liner_unit_price_usd: float
    liner_total_usd: float
    recessed_handle_cutout_unit_price_usd: float
    recessed_handle_cutout_total_usd: float
    total_usd: float


@dataclass(frozen=True, slots=True)
class ExtraAddonPricingSummary:
    pieces: tuple[ExtraAddonPieceResult, ...]
    total_usd: float


def physical_cut_quantity(qty: int, *, full_door_double: bool) -> int:
    """Return optimizer/cut-list quantity without mutating customer qty."""

    resolved = max(0, int(qty or 0))
    if full_door_double and resolved > 0:
        return resolved * FULL_DOOR_DOUBLE_CUT_MULTIPLIER
    return resolved


def calculate_extra_addon_pricing(
    pieces: Iterable[ExtraAddonPieceInput],
    *,
    rates: ExtraAddonRates,
) -> ExtraAddonPricingSummary:
    """Validate selections and snapshot unit/total sales prices per row."""

    resolved_rates = {
        "double": _finite_non_negative(rates.double_usd),
        "full_door_double": _finite_non_negative(rates.full_door_double_usd),
        "liner": _finite_non_negative(rates.liner_usd),
        "recessed_handle_cutout": _finite_non_negative(
            rates.recessed_handle_cutout_usd
        ),
    }
    results: list[ExtraAddonPieceResult] = []
    order_total = 0.0

    for piece in pieces:
        selected = tuple(
            code
            for code, enabled in (
                ("double", piece.double),
                ("full_door_double", piece.full_door_double),
                ("liner", piece.liner),
                ("recessed_handle_cutout", piece.recessed_handle_cutout),
            )
            if bool(enabled)
        )
        piece_type = str(piece.piece_type or "Regular")
        if piece_type != EXTRA_PIECE_TYPE:
            if selected:
                raise ExtraAddonError("non_extra_addon_selection", selected[0])
            results.append(_empty_result())
            continue

        if not selected:
            raise ExtraAddonError("extra_addon_required")
        if not str(piece.notes or "").strip():
            raise ExtraAddonError("extra_notes_required")

        qty = int(piece.qty or 0)
        if qty <= 0:
            raise ExtraAddonError("extra_quantity_invalid")
        snapshots = {
            "double": piece.double_snapshot_unit_price_usd,
            "full_door_double": piece.full_door_double_snapshot_unit_price_usd,
            "liner": piece.liner_snapshot_unit_price_usd,
            "recessed_handle_cutout": (
                piece.recessed_handle_cutout_snapshot_unit_price_usd
            ),
        }
        effective_rates = {
            code: (
                _finite_non_negative(snapshots[code])
                if snapshots[code] is not None
                else resolved_rates[code]
            )
            for code in EXTRA_ADDON_CODES
        }
        for code in selected:
            if effective_rates[code] <= 0:
                raise ExtraAddonError("extra_addon_rate_not_configured", code)

        unit_values = {
            code: effective_rates[code] if code in selected else 0.0
            for code in EXTRA_ADDON_CODES
        }
        total_values = {
            code: _money(unit_values[code] * qty)
            for code in EXTRA_ADDON_CODES
        }
        row_total = _money(sum(total_values.values()))
        order_total += row_total
        results.append(
            ExtraAddonPieceResult(
                applicable=True,
                selected_codes=selected,
                double_unit_price_usd=unit_values["double"],
                double_total_usd=total_values["double"],
                full_door_double_unit_price_usd=unit_values["full_door_double"],
                full_door_double_total_usd=total_values["full_door_double"],
                liner_unit_price_usd=unit_values["liner"],
                liner_total_usd=total_values["liner"],
                recessed_handle_cutout_unit_price_usd=unit_values[
                    "recessed_handle_cutout"
                ],
                recessed_handle_cutout_total_usd=total_values[
                    "recessed_handle_cutout"
                ],
                total_usd=row_total,
            )
        )

    return ExtraAddonPricingSummary(
        pieces=tuple(results),
        total_usd=_money(order_total),
    )


def _empty_result() -> ExtraAddonPieceResult:
    return ExtraAddonPieceResult(
        applicable=False,
        selected_codes=(),
        double_unit_price_usd=0,
        double_total_usd=0,
        full_door_double_unit_price_usd=0,
        full_door_double_total_usd=0,
        liner_unit_price_usd=0,
        liner_total_usd=0,
        recessed_handle_cutout_unit_price_usd=0,
        recessed_handle_cutout_total_usd=0,
        total_usd=0,
    )


def _finite_non_negative(value: float) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as error:
        raise ExtraAddonError("extra_addon_rate_invalid") from error
    if not math.isfinite(number) or number < 0:
        raise ExtraAddonError("extra_addon_rate_invalid")
    return number


def _money(value: float) -> float:
    return round_value(value, 3)


__all__ = [
    "EXTRA_ADDON_CODES",
    "EXTRA_PIECE_TYPE",
    "FULL_DOOR_DOUBLE_CUT_MULTIPLIER",
    "ExtraAddonError",
    "ExtraAddonPieceInput",
    "ExtraAddonPieceResult",
    "ExtraAddonPricingSummary",
    "ExtraAddonRates",
    "calculate_extra_addon_pricing",
    "physical_cut_quantity",
]
