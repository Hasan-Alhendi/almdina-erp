from __future__ import annotations

import math
from dataclasses import dataclass


class CutDimensionError(ValueError):
    """Raised when edge allowance inputs cannot produce a valid cutting size."""


@dataclass(frozen=True, slots=True)
class CutDimensionInput:
    final_width_cm: float
    final_length_cm: float
    edge_long_right: int = 0
    edge_long_left: int = 0
    edge_width_top: int = 0
    edge_width_bottom: int = 0
    edge_long_right_thickness_mm: float | None = None
    edge_long_left_thickness_mm: float | None = None
    edge_width_top_thickness_mm: float | None = None
    edge_width_bottom_thickness_mm: float | None = None
    # Transitional axis defaults keep the pure policy compatible with callers that
    # still provide one profile per axis. Side values always take precedence.
    long_edge_thickness_mm: float = 0
    width_edge_thickness_mm: float = 0


@dataclass(frozen=True, slots=True)
class CutDimensionResult:
    final_width_cm: float
    final_length_cm: float
    cut_width_cm: float
    cut_length_cm: float
    edge_long_right_thickness_mm: float
    edge_long_left_thickness_mm: float
    edge_width_top_thickness_mm: float
    edge_width_bottom_thickness_mm: float
    long_edge_thickness_mm: float
    width_edge_thickness_mm: float
    width_deduction_mm: float
    length_deduction_mm: float


def calculate_cut_dimensions(piece: CutDimensionInput) -> CutDimensionResult:
    """Calculate raw cutting size from the finished size and four side profiles.

    Every selected long side reduces the cutting width by its own thickness.
    Every selected width side reduces the cutting length by its own thickness.
    """

    final_width = _finite(piece.final_width_cm, "final_width")
    final_length = _finite(piece.final_length_cm, "final_length")
    if final_width <= 0:
        raise CutDimensionError("final_width_not_positive")
    if final_length <= 0:
        raise CutDimensionError("final_length_not_positive")

    right = _side_thickness(
        selected=piece.edge_long_right,
        side_value=piece.edge_long_right_thickness_mm,
        axis_value=piece.long_edge_thickness_mm,
        fieldname="edge_long_right_thickness",
    )
    left = _side_thickness(
        selected=piece.edge_long_left,
        side_value=piece.edge_long_left_thickness_mm,
        axis_value=piece.long_edge_thickness_mm,
        fieldname="edge_long_left_thickness",
    )
    top = _side_thickness(
        selected=piece.edge_width_top,
        side_value=piece.edge_width_top_thickness_mm,
        axis_value=piece.width_edge_thickness_mm,
        fieldname="edge_width_top_thickness",
    )
    bottom = _side_thickness(
        selected=piece.edge_width_bottom,
        side_value=piece.edge_width_bottom_thickness_mm,
        axis_value=piece.width_edge_thickness_mm,
        fieldname="edge_width_bottom_thickness",
    )

    width_deduction_mm = right + left
    length_deduction_mm = top + bottom
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
        edge_long_right_thickness_mm=_round(right),
        edge_long_left_thickness_mm=_round(left),
        edge_width_top_thickness_mm=_round(top),
        edge_width_bottom_thickness_mm=_round(bottom),
        long_edge_thickness_mm=_common_selected_value(
            (piece.edge_long_right, right),
            (piece.edge_long_left, left),
        ),
        width_edge_thickness_mm=_common_selected_value(
            (piece.edge_width_top, top),
            (piece.edge_width_bottom, bottom),
        ),
        width_deduction_mm=_round(width_deduction_mm),
        length_deduction_mm=_round(length_deduction_mm),
    )


def _side_thickness(
    *,
    selected: int,
    side_value: float | None,
    axis_value: float,
    fieldname: str,
) -> float:
    if not bool(selected):
        return 0.0
    source = axis_value if side_value is None else side_value
    thickness = _finite(source, fieldname)
    if thickness < 0:
        raise CutDimensionError(f"{fieldname}_negative")
    return thickness


def _common_selected_value(*values: tuple[int, float]) -> float:
    selected = {_round(value) for enabled, value in values if bool(enabled)}
    return selected.pop() if len(selected) == 1 else 0.0


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
