from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

CUT_DIMENSION_QUANTUM_CM = Decimal("0.001")
MM_PER_CM = Decimal("10")
SPECIAL_UNRECORDED_EDGE_MAX_DEDUCTION_MM = Decimal("2")

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


def special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
    actual_width_cm: object,
    actual_length_cm: object,
    expected_width_cm: object,
    expected_length_cm: object,
) -> bool:
    """Match a Special bbox equal to or up to 2 mm smaller on each axis.

    This models edge deductions that were not recorded on Special order rows.
    It is a one-sided manufacturing rule, not a symmetric dimension tolerance.
    All operands are compared at persisted cut-dimension precision.
    """
    actual_width = normalize_cut_cm(actual_width_cm)
    actual_length = normalize_cut_cm(actual_length_cm)
    expected_width = normalize_cut_cm(expected_width_cm)
    expected_length = normalize_cut_cm(expected_length_cm)
    max_deduction_cm = (
        SPECIAL_UNRECORDED_EDGE_MAX_DEDUCTION_MM / MM_PER_CM
    )

    width_deduction = expected_width - actual_width
    length_deduction = expected_length - actual_length
    return (
        Decimal("0") <= width_deduction <= max_deduction_cm
        and Decimal("0") <= length_deduction <= max_deduction_cm
    )


def special_bbox_allowed_range_cm(
    expected_width_cm: object,
    expected_length_cm: object,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return the already-defined one-sided Special bbox envelope.

    Validation/application code owns this calculation and may place the result
    into a structured issue. Presentation only formats these four values.
    """
    width = normalize_cut_cm(expected_width_cm)
    length = normalize_cut_cm(expected_length_cm)
    deduction_cm = SPECIAL_UNRECORDED_EDGE_MAX_DEDUCTION_MM / MM_PER_CM
    return (
        max(Decimal("0"), width - deduction_cm),
        width,
        max(Decimal("0"), length - deduction_cm),
        length,
    )


_L_NOTCH_LONG_SIDE = {
    "Top Right": SIDE_LONG_RIGHT,
    "Bottom Right": SIDE_LONG_RIGHT,
    "Top Left": SIDE_LONG_LEFT,
    "Bottom Left": SIDE_LONG_LEFT,
}
_L_NOTCH_WIDTH_SIDE = {
    "Top Right": SIDE_WIDTH_TOP,
    "Top Left": SIDE_WIDTH_TOP,
    "Bottom Right": SIDE_WIDTH_BOTTOM,
    "Bottom Left": SIDE_WIDTH_BOTTOM,
}
_OPPOSITE_SIDE = {
    SIDE_LONG_RIGHT: SIDE_LONG_LEFT,
    SIDE_LONG_LEFT: SIDE_LONG_RIGHT,
    SIDE_WIDTH_TOP: SIDE_WIDTH_BOTTOM,
    SIDE_WIDTH_BOTTOM: SIDE_WIDTH_TOP,
}


@dataclass(frozen=True)
class LCornerAxisCut:
    """One finished remnant and the raw length the DXF must cut."""

    finished_remaining_cm: Decimal
    terminator_mm: Decimal
    inner_mm: Decimal | None
    band_mm: Decimal | None
    expected_raw_cm: Decimal | None


@dataclass(frozen=True)
class LCornerRawCut:
    """Raw L notch in the order frame, before rotation or reflection.

    ``clipped_corner_width_cm`` / ``clipped_corner_length_cm`` stay the finished
    distances from the corner. The raw bite removes the outer band on the notch
    side and adds the inner L-band thickness, because that band sits on the
    material face of the notch. Each remnant deducts only the outer band at its
    far end plus that same inner thickness. The two inner edges affect opposite
    axes and are not added together.
    """

    proven: bool
    raw_notch_width_cm: Decimal | None
    raw_notch_length_cm: Decimal | None
    width: LCornerAxisCut
    length: LCornerAxisCut


def l_shaped_raw_cut(
    *,
    finished_width_cm: object,
    finished_length_cm: object,
    notch_width_cm: object,
    notch_length_cm: object,
    position: str,
    side_thickness_mm: Mapping[str, object] | None = None,
    edge_break: bool = False,
    edge_break_thickness_mm: object | None = None,
) -> LCornerRawCut:
    """Derive the raw L notch from finished corner distances and band thickness."""

    width = normalize_cut_cm(finished_width_cm)
    length = normalize_cut_cm(finished_length_cm)
    notch_width = normalize_cut_cm(notch_width_cm)
    notch_length = normalize_cut_cm(notch_length_cm)
    sides = {
        side: decimal_value((side_thickness_mm or {}).get(side, 0), label=side)
        for side in (
            SIDE_LONG_RIGHT,
            SIDE_LONG_LEFT,
            SIDE_WIDTH_TOP,
            SIDE_WIDTH_BOTTOM,
        )
    }
    inner: Decimal | None
    if not edge_break:
        inner = Decimal("0")
    elif edge_break_thickness_mm is None:
        inner = None
    else:
        inner = decimal_value(edge_break_thickness_mm, label="edge_break_thickness_mm")
        if inner < 0:
            raise CutDimensionError("سماكة قشاط زاوية L لا يمكن أن تكون سالبة.")

    notch_long = _L_NOTCH_LONG_SIDE.get(position)
    notch_width_side = _L_NOTCH_WIDTH_SIDE.get(position)
    if notch_long is None or notch_width_side is None:
        empty = LCornerAxisCut(Decimal("0"), Decimal("0"), inner, None, None)
        return LCornerRawCut(False, None, None, empty, empty)

    width_axis = _axis_cut(
        finished_remaining_cm=width - notch_width,
        terminator_mm=sides[_OPPOSITE_SIDE[notch_long]],
        notch_side_mm=sides[notch_long],
        finished_notch_cm=notch_width,
        inner_mm=inner,
    )
    length_axis = _axis_cut(
        finished_remaining_cm=length - notch_length,
        terminator_mm=sides[_OPPOSITE_SIDE[notch_width_side]],
        notch_side_mm=sides[notch_width_side],
        finished_notch_cm=notch_length,
        inner_mm=inner,
    )
    proven = inner is not None
    return LCornerRawCut(
        proven=proven,
        raw_notch_width_cm=width_axis.raw_notch_cm if proven else None,
        raw_notch_length_cm=length_axis.raw_notch_cm if proven else None,
        width=LCornerAxisCut(
            width_axis.finished_remaining_cm,
            width_axis.terminator_mm,
            inner,
            width_axis.band_mm,
            width_axis.expected_raw_cm,
        ),
        length=LCornerAxisCut(
            length_axis.finished_remaining_cm,
            length_axis.terminator_mm,
            inner,
            length_axis.band_mm,
            length_axis.expected_raw_cm,
        ),
    )


@dataclass(frozen=True)
class _AxisMath:
    finished_remaining_cm: Decimal
    terminator_mm: Decimal
    band_mm: Decimal | None
    expected_raw_cm: Decimal | None
    raw_notch_cm: Decimal | None


def _axis_cut(
    *,
    finished_remaining_cm: Decimal,
    terminator_mm: Decimal,
    notch_side_mm: Decimal,
    finished_notch_cm: Decimal,
    inner_mm: Decimal | None,
) -> _AxisMath:
    if inner_mm is None:
        return _AxisMath(finished_remaining_cm, terminator_mm, None, None, None)
    band_mm = terminator_mm + inner_mm
    expected_raw = normalize_cut_cm(
        finished_remaining_cm - (band_mm / MM_PER_CM)
    )
    raw_notch = normalize_cut_cm(
        finished_notch_cm - (notch_side_mm / MM_PER_CM) + (inner_mm / MM_PER_CM)
    )
    return _AxisMath(
        finished_remaining_cm,
        terminator_mm,
        band_mm,
        expected_raw,
        raw_notch,
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
