from __future__ import annotations

import math
from dataclasses import dataclass


class CutDimensionError(ValueError):
    """Raised when edge allowance inputs cannot produce a valid cutting size."""


@dataclass(frozen=True, slots=True)
class CutDimensionInput:
    final_width_cm: float
    final_length_cm: float
    edge_thickness_mm: float
    edge_long_right: int = 0
    edge_long_left: int = 0
    edge_width_top: int = 0
    edge_width_bottom: int = 0


@dataclass(frozen=True, slots=True)
class CutDimensionResult:
    final_width_cm: float
    final_length_cm: float
    cut_width_cm: float
    cut_length_cm: float
    edge_thickness_mm: float
    width_deduction_mm: float
    length_deduction_mm: float


def calculate_cut_dimensions(piece: CutDimensionInput) -> CutDimensionResult:
    """Calculate the raw board size from the requested finished size.

    Long-side banding grows the finished width, so its thickness is deducted from
    the cutting width. Width-side banding grows the finished length, so its
    thickness is deducted from the cutting length.
    """

    final_width = _finite(piece.final_width_cm, "final_width")
    final_length = _finite(piece.final_length_cm, "final_length")
    thickness_mm = _finite(piece.edge_thickness_mm, "edge_thickness")

    if final_width <= 0:
        raise CutDimensionError("final_width_not_positive")
    if final_length <= 0:
        raise CutDimensionError("final_length_not_positive")
    if thickness_mm < 0:
        raise CutDimensionError("edge_thickness_negative")

    long_side_count = _selected_count(
        piece.edge_long_right,
        piece.edge_long_left,
    )
    width_side_count = _selected_count(
        piece.edge_width_top,
        piece.edge_width_bottom,
    )
    width_deduction_mm = thickness_mm * long_side_count
    length_deduction_mm = thickness_mm * width_side_count
    cut_width = final_width - (width_deduction_mm / 10)
    cut_length = final_length - (length_deduction_mm / 10)

    if cut_width <= 0:
        raise CutDimensionError("cut_width_not_positive")
    if cut_length <= 0:
        raise CutDimensionError("cut_length_not_positive")

    return CutDimensionResult(
        final_width_cm=_round(final_width),
        final_length_cm=_round(final_length),
        cut_width_cm=_round(cut_width),
        cut_length_cm=_round(cut_length),
        edge_thickness_mm=_round(thickness_mm),
        width_deduction_mm=_round(width_deduction_mm),
        length_deduction_mm=_round(length_deduction_mm),
    )


def _selected_count(*values: int) -> int:
    return sum(1 for value in values if bool(value))


def _finite(value: float, fieldname: str) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as error:
        raise CutDimensionError(f"{fieldname}_not_finite") from error
    if not math.isfinite(number):
        raise CutDimensionError(f"{fieldname}_not_finite")
    return number


def _round(value: float) -> float:
    return round(value, 3)


__all__ = [
    "CutDimensionError",
    "CutDimensionInput",
    "CutDimensionResult",
    "calculate_cut_dimensions",
]
