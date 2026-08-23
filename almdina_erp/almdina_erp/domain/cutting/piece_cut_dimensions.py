from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

CUT_DIMENSION_QUANTUM_CM = Decimal("0.001")
MM_PER_CM = Decimal("10")

SIDE_LONG_RIGHT = "long_right"
SIDE_LONG_LEFT = "long_left"
SIDE_WIDTH_TOP = "width_top"
SIDE_WIDTH_BOTTOM = "width_bottom"

WIDTH_DEDUCTION_SIDES = (SIDE_LONG_RIGHT, SIDE_LONG_LEFT)
LENGTH_DEDUCTION_SIDES = (SIDE_WIDTH_TOP, SIDE_WIDTH_BOTTOM)


class CutDimensionError(ValueError):
    """User-fixable failure while deriving exact finished-to-raw dimensions."""

    def __init__(self, errors: str | list[str]):
        self.errors = (
            [errors]
            if isinstance(errors, str)
            else [str(error) for error in errors if str(error).strip()]
        )
        super().__init__("\n".join(self.errors))


@dataclass(frozen=True)
class CutDimensionResult:
    finished_width_cm: Decimal
    finished_length_cm: Decimal
    cut_width_cm: Decimal
    cut_length_cm: Decimal
    width_deduction_mm: Decimal
    length_deduction_mm: Decimal
    side_thickness_mm: Mapping[str, Decimal]


def decimal_value(value: object, *, label: str = "value") -> Decimal:
    try:
        result = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CutDimensionError(f"{label} ليس رقمًا صالحًا.") from exc
    if not result.is_finite():
        raise CutDimensionError(f"{label} يجب أن يكون رقمًا محدودًا.")
    return result


def normalize_cut_cm(value: object) -> Decimal:
    """Normalize a cut dimension to the persisted 0.001 cm precision.

    This is storage precision, not a manufacturing tolerance. Two dimensions
    match only when their normalized values are identical.
    """
    return decimal_value(value).quantize(CUT_DIMENSION_QUANTUM_CM, rounding=ROUND_HALF_UP)


def calculate_cut_dimensions(
    *,
    finished_width_cm: object,
    finished_length_cm: object,
    side_thickness_mm: Mapping[str, object] | None = None,
) -> CutDimensionResult:
    width = normalize_cut_cm(finished_width_cm)
    length = normalize_cut_cm(finished_length_cm)
    if width <= 0 or length <= 0:
        raise CutDimensionError("مقاس الدرفة النهائي يجب أن يكون أكبر من صفر.")

    raw_sides = side_thickness_mm or {}
    sides: dict[str, Decimal] = {}
    for side in (
        SIDE_LONG_RIGHT,
        SIDE_LONG_LEFT,
        SIDE_WIDTH_TOP,
        SIDE_WIDTH_BOTTOM,
    ):
        thickness = decimal_value(raw_sides.get(side, 0), label=f"سماكة القشاط ({side})")
        if thickness < 0:
            raise CutDimensionError("سماكة القشاط لا يمكن أن تكون سالبة.")
        sides[side] = thickness

    width_deduction_mm = sum((sides[side] for side in WIDTH_DEDUCTION_SIDES), Decimal("0"))
    length_deduction_mm = sum((sides[side] for side in LENGTH_DEDUCTION_SIDES), Decimal("0"))

    cut_width = normalize_cut_cm(width - (width_deduction_mm / MM_PER_CM))
    cut_length = normalize_cut_cm(length - (length_deduction_mm / MM_PER_CM))
    if cut_width <= 0 or cut_length <= 0:
        raise CutDimensionError(
            "سماكات القشاط المختارة تستهلك كامل مقاس الدرفة أو تتجاوزه؛ "
            "راجع المقاس النهائي وأنواع القشاط على الأضلاع."
        )

    return CutDimensionResult(
        finished_width_cm=width,
        finished_length_cm=length,
        cut_width_cm=cut_width,
        cut_length_cm=cut_length,
        width_deduction_mm=width_deduction_mm,
        length_deduction_mm=length_deduction_mm,
        side_thickness_mm=sides,
    )


def dimensions_match_exact(
    actual_width_cm: object,
    actual_length_cm: object,
    expected_width_cm: object,
    expected_length_cm: object,
) -> bool:
    return (
        normalize_cut_cm(actual_width_cm) == normalize_cut_cm(expected_width_cm)
        and normalize_cut_cm(actual_length_cm) == normalize_cut_cm(expected_length_cm)
    )
