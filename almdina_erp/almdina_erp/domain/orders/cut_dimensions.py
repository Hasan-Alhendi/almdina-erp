from __future__ import annotations

import math
from dataclasses import dataclass


class CutDimensionError(ValueError):
    """Raised when edge allowance inputs cannot produce a valid cutting size."""


@dataclass(frozen=True, slots=True)
class CutDimensionInput:
    final_width_cm: float
    final_length_cm: float
    long_edge_thickness_mm: float = 0
    width_edge_thickness_mm: float = 0
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
    long_edge_thickness_mm: float
    width_edge_thickness_mm: float
    width_deduction_mm: float
    length_deduction_mm: float


def calculate_cut_dimensions(piece: CutDimensionInput) -> CutDimensionResult:
    """Calculate the raw board size from the requested finished size.

    Selected long sides use the long-axis edge profile and reduce cutting width.
    Selected width sides use the width-axis edge profile and reduce cutting length.
    """

    final_width = _finite(piece.final_width_cm, "final_width")
    final_length = _finite(piece.final_length_cm, "final_length")
    long_thickness = _finite(
        piece.long_edge_thickness_mm,
        "long_edge_thickness",
    )
    width_thickness = _finite(
        piece.width_edge_thickness_mm,
        "width_edge_thickness",
    )

    if final_width <= 0:
        raise CutDimensionError("final_width_not_positive")
    if final_length <= 0:
        raise CutDimensionError("final_length_not_positive")
    if long_thickness < 0:
        raise CutDimensionError("long_edge_thickness_negative")
    if width_thickness < 0:
        raise CutDimensionError("width_edge_thickness_negative")

    long_side_count = _selected_count(
        piece.edge_long_right,
        piece.edge_long_left,
    )
    width_side_count = _selected_count(
        piece.edge_width_top,
        piece.edge_width_bottom,
    )
    width_deduction_mm = long_thickness * long_side_count
    length_deduction_mm = width_thickness * width_side_count
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
        long_edge_thickness_mm=_round(long_thickness),
        width_edge_thickness_mm=_round(width_thickness),
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
