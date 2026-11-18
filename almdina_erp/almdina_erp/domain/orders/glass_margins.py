"""Glass-door margins measured from the entered outer size.

``All Directions`` keeps the historical single ``glass_margin_mm`` on every
side. ``Individual Sides`` stores four independent millimetre margins. A row
that only has the old field is read as All Directions, so its opening stays
where it was. The opening is not assumed to be centered.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.orders.piece_types import GLASS_TYPE

MM_PER_CM = Decimal("10")

MODE_ALL = "All Directions"
MODE_INDIVIDUAL = "Individual Sides"
GLASS_MARGIN_MODE_FIELD = "glass_margin_mode"
GLASS_MARGIN_MM_FIELD = "glass_margin_mm"
GLASS_MARGIN_TOP_FIELD = "glass_margin_top_mm"
GLASS_MARGIN_BOTTOM_FIELD = "glass_margin_bottom_mm"
GLASS_MARGIN_RIGHT_FIELD = "glass_margin_right_mm"
GLASS_MARGIN_LEFT_FIELD = "glass_margin_left_mm"
GLASS_SIDE_FIELDS = (
    GLASS_MARGIN_TOP_FIELD,
    GLASS_MARGIN_BOTTOM_FIELD,
    GLASS_MARGIN_RIGHT_FIELD,
    GLASS_MARGIN_LEFT_FIELD,
)
FINGERPRINT_GLASS_FIELDS = (GLASS_MARGIN_MODE_FIELD, *GLASS_SIDE_FIELDS)

_SIDE_BANDS = (
    ("left", "edge_long_left", "edge_long_thickness_mm", "width"),
    ("right", "edge_long_right", "edge_long_thickness_mm", "width"),
    ("top", "edge_width_top", "edge_width_thickness_mm", "length"),
    ("bottom", "edge_width_bottom", "edge_width_thickness_mm", "length"),
)
_REMOVED_AXIS_TOLERANCE_MM = Decimal("0.05")


class GlassMarginError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class GlassSideMargins:
    """Finished-edge margins. Y grows down from the top-left outer corner."""

    mode: str
    top_mm: Decimal
    bottom_mm: Decimal
    right_mm: Decimal
    left_mm: Decimal

    @property
    def individual(self) -> bool:
        return self.mode == MODE_INDIVIDUAL

    @property
    def uniform_mm(self) -> Decimal | None:
        if self.top_mm == self.bottom_mm == self.right_mm == self.left_mm:
            return self.top_mm
        return None


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _decimal(value: object, code: str = "glass_margin_must_be_positive") -> Decimal:
    try:
        number = Decimal(str(value if value not in (None, "") else "0"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise GlassMarginError(code) from exc
    if not number.is_finite():
        raise GlassMarginError(code)
    return number


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no"}
    return bool(value)


def canonical_uniform_margin_mm(
    value: object,
    piece_type: str | None = None,
) -> float | None:
    """Float used by plan fingerprints. Zero, blank, and non-Glass stay omitted."""

    if piece_type != GLASS_TYPE:
        return None
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite() or number == 0:
        return None
    return float(number)


def resolve_glass_side_margins(
    source: Any,
    *,
    piece_type: str | None = None,
) -> GlassSideMargins | None:
    """Read one Glass row. Missing mode is the legacy uniform margin.

    Individual mode uses the four side fields even when they are not yet
    valid. Every other mode, including a blank mode on an old order, uses
    ``glass_margin_mm`` for all four sides and ignores stored side fields.
    """

    kind = piece_type if piece_type is not None else str(_field(source, "piece_type", "") or "")
    if kind != GLASS_TYPE:
        return None
    mode = str(_field(source, GLASS_MARGIN_MODE_FIELD, "") or "").strip()
    if mode == MODE_INDIVIDUAL:
        return GlassSideMargins(
            mode=MODE_INDIVIDUAL,
            top_mm=_decimal(_field(source, GLASS_MARGIN_TOP_FIELD, 0)),
            bottom_mm=_decimal(_field(source, GLASS_MARGIN_BOTTOM_FIELD, 0)),
            right_mm=_decimal(_field(source, GLASS_MARGIN_RIGHT_FIELD, 0)),
            left_mm=_decimal(_field(source, GLASS_MARGIN_LEFT_FIELD, 0)),
        )
    stored = _field(source, GLASS_MARGIN_MM_FIELD, None)
    if stored in (None, ""):
        return None
    margin = _decimal(stored)
    return GlassSideMargins(
        mode=MODE_ALL,
        top_mm=margin,
        bottom_mm=margin,
        right_mm=margin,
        left_mm=margin,
    )


def opening_from_margins(
    margins: GlassSideMargins,
    *,
    outer_width_cm: object,
    outer_length_cm: object,
) -> dict[str, Decimal]:
    """Opening size and top-left origin, before edge-band deduction."""

    for value in (
        margins.top_mm,
        margins.bottom_mm,
        margins.right_mm,
        margins.left_mm,
    ):
        if value <= 0:
            raise GlassMarginError("glass_margin_must_be_positive")
    width_mm = _decimal(outer_width_cm, "glass_opening_must_be_positive") * MM_PER_CM
    length_mm = _decimal(outer_length_cm, "glass_opening_must_be_positive") * MM_PER_CM
    opening_width_mm = width_mm - margins.left_mm - margins.right_mm
    opening_length_mm = length_mm - margins.top_mm - margins.bottom_mm
    if opening_width_mm <= 0 or opening_length_mm <= 0:
        raise GlassMarginError("glass_opening_must_be_positive")
    return {
        "opening_width_mm": opening_width_mm,
        "opening_length_mm": opening_length_mm,
        "origin_x_mm": margins.left_mm,
        "origin_y_mm": margins.top_mm,
    }


def has_glass_opening(source: Any) -> bool:
    margins = resolve_glass_side_margins(source)
    if margins is None:
        return False
    try:
        opening_from_margins(
            margins,
            outer_width_cm=_field(source, "width_cm", 0) or _field(source, "original_w", 0),
            outer_length_cm=_field(source, "length_cm", 0) or _field(source, "original_h", 0),
        )
    except GlassMarginError:
        return margins.top_mm > 0 or margins.bottom_mm > 0 or margins.right_mm > 0 or margins.left_mm > 0
    return True


def fingerprint_glass_fields(source: Any) -> dict[str, Any]:
    """Keys that may enter a plan hash. Uniform rows keep the historical key only."""

    margins = resolve_glass_side_margins(source)
    if margins is None:
        return {}
    if margins.individual:
        return {
            GLASS_MARGIN_MODE_FIELD: MODE_INDIVIDUAL,
            GLASS_MARGIN_TOP_FIELD: float(margins.top_mm),
            GLASS_MARGIN_BOTTOM_FIELD: float(margins.bottom_mm),
            GLASS_MARGIN_RIGHT_FIELD: float(margins.right_mm),
            GLASS_MARGIN_LEFT_FIELD: float(margins.left_mm),
        }
    uniform = canonical_uniform_margin_mm(margins.top_mm, GLASS_TYPE)
    if uniform is None:
        return {}
    return {GLASS_MARGIN_MM_FIELD: uniform}


def normalized_glass_margin_fields(source: Any) -> dict[str, Any] | None:
    """Persisted fields after a valid Glass row is saved. None for other types."""

    margins = resolve_glass_side_margins(source)
    if margins is None and str(_field(source, "piece_type", "") or "") != GLASS_TYPE:
        return None
    if margins is None or not margins.individual:
        uniform = Decimal(0) if margins is None else margins.top_mm
        return {
            GLASS_MARGIN_MODE_FIELD: MODE_ALL,
            GLASS_MARGIN_MM_FIELD: float(uniform),
            GLASS_MARGIN_TOP_FIELD: 0,
            GLASS_MARGIN_BOTTOM_FIELD: 0,
            GLASS_MARGIN_RIGHT_FIELD: 0,
            GLASS_MARGIN_LEFT_FIELD: 0,
        }
    shared = margins.uniform_mm
    return {
        GLASS_MARGIN_MODE_FIELD: MODE_INDIVIDUAL,
        GLASS_MARGIN_MM_FIELD: 0 if shared is None else float(shared),
        GLASS_MARGIN_TOP_FIELD: float(margins.top_mm),
        GLASS_MARGIN_BOTTOM_FIELD: float(margins.bottom_mm),
        GLASS_MARGIN_RIGHT_FIELD: float(margins.right_mm),
        GLASS_MARGIN_LEFT_FIELD: float(margins.left_mm),
    }


def cut_frame_thickness_mm(
    source: Any,
    *,
    cut_width_cm: object,
    cut_length_cm: object,
) -> dict[str, float] | None:
    """Frame thickness on the cut rectangle for each outer side.

    When the stored cut is already smaller than the entered size, the selected
    edge band has been removed and the remaining frame is margin minus that
    band. An undeducted blank keeps the full margin. This is the same inset
    the Glass opening uses from the cut outline.
    """

    margins = resolve_glass_side_margins(source)
    if margins is None:
        return None
    finished_width = _decimal(_field(source, "width_cm", 0), "glass_opening_must_be_positive") * MM_PER_CM
    finished_length = _decimal(_field(source, "length_cm", 0), "glass_opening_must_be_positive") * MM_PER_CM
    cut_width = _decimal(cut_width_cm, "glass_opening_must_be_positive") * MM_PER_CM
    cut_length = _decimal(cut_length_cm, "glass_opening_must_be_positive") * MM_PER_CM
    removed = {
        "width": finished_width - cut_width,
        "length": finished_length - cut_length,
    }
    frames: dict[str, float] = {}
    amounts = {
        "left": margins.left_mm,
        "right": margins.right_mm,
        "top": margins.top_mm,
        "bottom": margins.bottom_mm,
    }
    for side, flag, thickness_field, axis in _SIDE_BANDS:
        band = _decimal(_field(source, thickness_field, 0)) if _truthy(_field(source, flag, 0)) else Decimal(0)
        if removed[axis] <= _REMOVED_AXIS_TOLERANCE_MM:
            band = Decimal(0)
        frames[side] = float(amounts[side] - band)
    return frames


__all__ = [
    "FINGERPRINT_GLASS_FIELDS",
    "GLASS_MARGIN_BOTTOM_FIELD",
    "GLASS_MARGIN_LEFT_FIELD",
    "GLASS_MARGIN_MM_FIELD",
    "GLASS_MARGIN_MODE_FIELD",
    "GLASS_MARGIN_RIGHT_FIELD",
    "GLASS_MARGIN_TOP_FIELD",
    "GLASS_SIDE_FIELDS",
    "MODE_ALL",
    "MODE_INDIVIDUAL",
    "GlassMarginError",
    "GlassSideMargins",
    "canonical_uniform_margin_mm",
    "cut_frame_thickness_mm",
    "fingerprint_glass_fields",
    "has_glass_opening",
    "normalized_glass_margin_fields",
    "opening_from_margins",
    "resolve_glass_side_margins",
]
