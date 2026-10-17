"""Glass opening checks for an already extracted cut contour.

The finished opening is the order contract: each axis is the entered outer
size minus twice ``glass_margin_mm``. DXF outlines are cut outlines, so each
side's inset from that outline is the same margin minus the band already
deducted on that side. A missing or non-positive inset is a real mismatch;
geometry tolerance does not absorb it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    bbox,
    is_axis_aligned_rectangle,
    validate_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CATEGORY_DIMENSIONS,
    CATEGORY_TOPOLOGY,
    FORBIDDEN_ROTATION,
    GLASS_GEOMETRY_AMBIGUOUS,
    GLASS_MARGIN_MISMATCH,
    GLASS_MULTIPLE_OPENINGS,
    GLASS_OPENING_INVALID,
    GLASS_OPENING_MISSING,
    GLASS_OPENING_OUTSIDE,
    GLASS_OPENING_UNEXPECTED,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    polygon_strictly_contains_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import MM_PER_CM
from almdina_erp.almdina_erp.domain.orders.piece_policy import GLASS_TYPE

# 0° and 180° keep the door width on the contour X axis. They are rotations.
# A single-axis mirror is not in this list.
_UNROTATED = (
    (
        ("left", "long_left"),
        ("right", "long_right"),
        ("bottom", "width_bottom"),
        ("top", "width_top"),
    ),
    (
        ("left", "long_right"),
        ("right", "long_left"),
        ("bottom", "width_top"),
        ("top", "width_bottom"),
    ),
)
# 90° clockwise and counter-clockwise. Both have the same swapped footprint
# the current matcher can see. Neither mapping is a reflection.
_ROTATED = (
    (
        ("left", "width_bottom"),
        ("right", "width_top"),
        ("bottom", "long_right"),
        ("top", "long_left"),
    ),
    (
        ("left", "width_top"),
        ("right", "width_bottom"),
        ("bottom", "long_left"),
        ("top", "long_right"),
    ),
)


@dataclass(frozen=True, slots=True)
class GlassOpeningDecision:
    code: str | None = None
    category: str = CATEGORY_TOPOLOGY
    params: dict[str, object] | None = None

    @property
    def ok(self) -> bool:
        return self.code is None


@dataclass(frozen=True, slots=True)
class GlassIdentityContour:
    width_mm: float
    height_mm: float
    hole_count: int
    expected_index: int | None


@dataclass(frozen=True, slots=True)
class GlassIdentityExpectation:
    width_mm: float
    height_mm: float
    allow_rotation: bool
    is_glass: bool


def _decimal(value: object) -> Decimal:
    return Decimal(str(value if value not in (None, "") else 0))


def cut_insets_mm(
    *,
    margin_mm: object,
    long_left_mm: object = 0,
    long_right_mm: object = 0,
    width_bottom_mm: object = 0,
    width_top_mm: object = 0,
) -> dict[str, Decimal]:
    """Inset of the opening from each side of the cut outline."""

    margin = _decimal(margin_mm)
    return {
        "long_left": margin - _decimal(long_left_mm),
        "long_right": margin - _decimal(long_right_mm),
        "width_bottom": margin - _decimal(width_bottom_mm),
        "width_top": margin - _decimal(width_top_mm),
    }


def _ring(x0: Decimal, y0: Decimal, x1: Decimal, y1: Decimal) -> tuple[tuple[float, float], ...]:
    return (
        (float(x0), float(y0)),
        (float(x1), float(y0)),
        (float(x1), float(y1)),
        (float(x0), float(y1)),
    )


def glass_hole_ring_mm(
    *,
    cut_width_mm: object,
    cut_length_mm: object,
    margin_mm: object,
    long_left_mm: object = 0,
    long_right_mm: object = 0,
    width_bottom_mm: object = 0,
    width_top_mm: object = 0,
    rotated: bool = False,
) -> tuple[tuple[float, float], ...] | None:
    """Piece-local opening. Y grows down from the top of the placed rectangle.

    Unrotated placement keeps the door axes. A rotated placement uses the
    same 90° clockwise edge mapping the cutting-plan renderer already uses.
    """

    insets = cut_insets_mm(
        margin_mm=margin_mm,
        long_left_mm=long_left_mm,
        long_right_mm=long_right_mm,
        width_bottom_mm=width_bottom_mm,
        width_top_mm=width_top_mm,
    )
    if any(value <= 0 for value in insets.values()):
        return None
    width = _decimal(cut_width_mm)
    length = _decimal(cut_length_mm)
    if not rotated:
        return _ring(
            insets["long_left"],
            insets["width_top"],
            width - insets["long_right"],
            length - insets["width_bottom"],
        )
    return _ring(
        insets["width_bottom"],
        insets["long_left"],
        length - insets["width_top"],
        width - insets["long_right"],
    )


def placed_glass_hole_mm(piece: Mapping[str, object], *, rotated: bool) -> list[list[float]] | None:
    if str(piece.get("piece_type") or "") != GLASS_TYPE:
        return None
    margin = piece.get("glass_margin_mm")
    if margin in (None, "", 0, 0.0):
        return None
    width_cm = piece.get("width_cm")
    length_cm = piece.get("length_cm")
    if width_cm in (None, "", 0, 0.0) or length_cm in (None, "", 0, 0.0):
        return None
    long_thickness = _decimal(piece.get("edge_long_thickness_mm"))
    width_thickness = _decimal(piece.get("edge_width_thickness_mm"))
    ring = glass_hole_ring_mm(
        cut_width_mm=_decimal(width_cm) * MM_PER_CM,
        cut_length_mm=_decimal(length_cm) * MM_PER_CM,
        margin_mm=margin,
        long_left_mm=long_thickness if piece.get("edge_long_left") else 0,
        long_right_mm=long_thickness if piece.get("edge_long_right") else 0,
        width_bottom_mm=width_thickness if piece.get("edge_width_bottom") else 0,
        width_top_mm=width_thickness if piece.get("edge_width_top") else 0,
        rotated=rotated,
    )
    if ring is None:
        return None
    return [[x, y] for x, y in ring]


def _measured_insets(outer: Sequence[Sequence[float]], hole: Sequence[Sequence[float]]) -> dict[str, float]:
    min_x, min_y, max_x, max_y = bbox(outer)
    hole_min_x, hole_min_y, hole_max_x, hole_max_y = bbox(hole)
    return {
        "left": hole_min_x - min_x,
        "right": max_x - hole_max_x,
        "bottom": hole_min_y - min_y,
        "top": max_y - hole_max_y,
    }


def _best_mapping(
    actual: Mapping[str, float],
    expected: Mapping[str, Decimal],
    mappings: tuple[tuple[tuple[str, str], ...], ...],
) -> tuple[float, str, float, Decimal]:
    best_delta = None
    best: tuple[float, str, float, Decimal] | None = None
    for mapping in mappings:
        worst_delta = -1.0
        worst: tuple[float, str, float, Decimal] | None = None
        for dxf_side, door_side in mapping:
            delta = abs(actual[dxf_side] - float(expected[door_side]))
            if delta > worst_delta:
                worst_delta = delta
                worst = (delta, door_side, actual[dxf_side], expected[door_side])
        if worst is None:
            continue
        if best_delta is None or worst_delta < best_delta:
            best_delta = worst_delta
            best = worst
    if best is None:
        raise ValueError("glass opening mapping is empty")
    return best


def validate_glass_dxf_opening(
    *,
    outer: Sequence[Sequence[float]],
    holes: Sequence[Sequence[Sequence[float]]],
    piece_type: str | None,
    margin_mm: object,
    long_left_mm: object = 0,
    long_right_mm: object = 0,
    width_bottom_mm: object = 0,
    width_top_mm: object = 0,
    rotated: bool = False,
    allow_rotation: bool = False,
    tolerance: float,
) -> GlassOpeningDecision:
    hole_list = list(holes or ())
    if (piece_type or "") != GLASS_TYPE:
        if hole_list:
            return GlassOpeningDecision(
                code=GLASS_OPENING_UNEXPECTED,
                category=CATEGORY_TOPOLOGY,
            )
        return GlassOpeningDecision()
    if not hole_list:
        return GlassOpeningDecision(code=GLASS_OPENING_MISSING, category=CATEGORY_TOPOLOGY)
    if len(hole_list) > 1:
        return GlassOpeningDecision(
            code=GLASS_MULTIPLE_OPENINGS,
            category=CATEGORY_TOPOLOGY,
            params={"opening_count": len(hole_list)},
        )
    if rotated and not allow_rotation:
        return GlassOpeningDecision(code=FORBIDDEN_ROTATION, category=CATEGORY_DIMENSIONS)
    hole = hole_list[0]
    if validate_polygon(hole, tolerance) or not is_axis_aligned_rectangle(hole, tolerance):
        return GlassOpeningDecision(code=GLASS_OPENING_INVALID, category=CATEGORY_TOPOLOGY)
    if not polygon_strictly_contains_polygon(outer, hole, tolerance=tolerance):
        return GlassOpeningDecision(code=GLASS_OPENING_OUTSIDE, category=CATEGORY_TOPOLOGY)

    bands = {
        "long_left": _decimal(long_left_mm),
        "long_right": _decimal(long_right_mm),
        "width_bottom": _decimal(width_bottom_mm),
        "width_top": _decimal(width_top_mm),
    }
    expected = cut_insets_mm(
        margin_mm=margin_mm,
        long_left_mm=bands["long_left"],
        long_right_mm=bands["long_right"],
        width_bottom_mm=bands["width_bottom"],
        width_top_mm=bands["width_top"],
    )
    order_margin = _decimal(margin_mm)
    if any(value <= 0 for value in expected.values()):
        side = next(name for name, value in expected.items() if value <= 0)
        return GlassOpeningDecision(
            code=GLASS_MARGIN_MISMATCH,
            category=CATEGORY_DIMENSIONS,
            params={
                "reason": "band_consumes_margin",
                "side": side,
                "order_margin_mm": float(order_margin),
                "expected_inset_mm": float(expected[side]),
                "band_mm": float(bands[side]),
            },
        )
    delta, side, actual_inset, expected_inset = _best_mapping(
        _measured_insets(outer, hole),
        expected,
        _ROTATED if rotated else _UNROTATED,
    )
    if delta > tolerance:
        return GlassOpeningDecision(
            code=GLASS_MARGIN_MISMATCH,
            category=CATEGORY_DIMENSIONS,
            params={
                "side": side,
                "order_margin_mm": float(order_margin),
                "expected_inset_mm": float(expected_inset),
                "actual_inset_mm": actual_inset,
                "band_mm": float(bands[side]),
            },
        )
    return GlassOpeningDecision()


def _interchangeable(
    first: GlassIdentityExpectation,
    second: GlassIdentityExpectation,
    tolerance: float,
) -> bool:
    direct = (
        abs(first.width_mm - second.width_mm) <= tolerance
        and abs(first.height_mm - second.height_mm) <= tolerance
    )
    if direct:
        return True
    return bool(
        first.allow_rotation
        and second.allow_rotation
        and abs(first.width_mm - second.height_mm) <= tolerance
        and abs(first.height_mm - second.width_mm) <= tolerance
    )


def reassign_glass_identity(
    contours: Sequence[GlassIdentityContour],
    expected: Sequence[GlassIdentityExpectation],
    *,
    dimension_tolerance: float,
) -> tuple[tuple[int | None, ...], str | None]:
    """Give a same-size Glass row the contour that owns the single opening.

    Contours that do not share a size stay on the assignment they already
    have. Mixed Glass and non-Glass rows of one size are rejected when the
    opening does not identify exactly the Glass rows.
    """

    count = len(expected)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(count):
        for right in range(left + 1, count):
            if _interchangeable(expected[left], expected[right], dimension_tolerance):
                union(left, right)

    assigned = [contour.expected_index for contour in contours]
    clusters: dict[int, list[int]] = {}
    for index in range(count):
        clusters.setdefault(find(index), []).append(index)

    for members in clusters.values():
        member_set = set(members)
        glass = [index for index in members if expected[index].is_glass]
        plain_expected = [index for index in members if index not in set(glass)]
        if not glass or not plain_expected:
            continue
        positions = [
            position
            for position, contour in enumerate(contours)
            if contour.expected_index in member_set
        ]
        if len(positions) != len(members):
            continue
        if any(contours[position].hole_count > 1 for position in positions):
            return tuple(assigned), GLASS_GEOMETRY_AMBIGUOUS
        openings = [position for position in positions if contours[position].hole_count == 1]
        plains = [position for position in positions if contours[position].hole_count == 0]
        if not openings:
            continue
        if len(openings) != len(glass) or len(plains) != len(plain_expected):
            return tuple(assigned), GLASS_GEOMETRY_AMBIGUOUS
        if all(assigned[position] in set(glass) for position in openings):
            continue
        for position, expected_index in zip(sorted(openings), sorted(glass), strict=True):
            assigned[position] = expected_index
        for position, expected_index in zip(sorted(plains), sorted(plain_expected), strict=True):
            assigned[position] = expected_index
    return tuple(assigned), None


__all__ = [
    "GLASS_GEOMETRY_AMBIGUOUS",
    "GLASS_MARGIN_MISMATCH",
    "GLASS_MULTIPLE_OPENINGS",
    "GLASS_OPENING_INVALID",
    "GLASS_OPENING_MISSING",
    "GLASS_OPENING_OUTSIDE",
    "GLASS_OPENING_UNEXPECTED",
    "GlassIdentityContour",
    "GlassIdentityExpectation",
    "GlassOpeningDecision",
    "cut_insets_mm",
    "glass_hole_ring_mm",
    "placed_glass_hole_mm",
    "reassign_glass_identity",
    "validate_glass_dxf_opening",
]
