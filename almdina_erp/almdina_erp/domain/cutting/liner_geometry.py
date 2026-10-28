"""Parametric liner strip on a door, shared by preview, plans, and DXF checks.

Coordinates are the usable-sheet frame: origin at the piece's top-left, x to
the right, y downward, millimetres. That is the same frame as corner contours.
A liner is one offset band along a single strap-system edge. A path whose
vertices have no measurable thickness is rejected; lineweight is not invented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    bbox,
    has_self_intersection,
    point_in_polygon,
    point_to_polygon_distance,
    polygon_segments,
    polygons_overlap,
    segment_distance,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    CutDimensionError,
    l_shaped_raw_cut,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import GLASS_TYPE
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    CLIPPED_CORNER_TYPE,
    L_SHAPED_CORNER_TYPE,
)

Point = tuple[float, float]

SIDE_TOP = "edge_width_top"
SIDE_BOTTOM = "edge_width_bottom"
SIDE_LEFT = "edge_long_left"
SIDE_RIGHT = "edge_long_right"
SIDE_BREAK = "edge_break"
SIDE_BREAK_ONLY = "edge_break_only"
OUTER_SIDES = (SIDE_TOP, SIDE_BOTTOM, SIDE_LEFT, SIDE_RIGHT)
CM_TO_MM = 10.0

LINER_OFFSET_MISMATCH = "liner_offset_mismatch"
LINER_WIDTH_MISMATCH = "liner_width_mismatch"
LINER_SIDE_MISMATCH = "liner_side_mismatch"
LINER_SHAPE_MISMATCH = "liner_shape_mismatch"
LINER_WIDTH_NOT_MEASURABLE = "liner_width_not_measurable"


class LinerGeometryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LinerPiece:
    piece_type: str
    width_cm: float
    length_cm: float
    clipped_corner_position: str = "Top Right"
    clipped_corner_width_cm: float = 0.0
    clipped_corner_length_cm: float = 0.0


@dataclass(frozen=True, slots=True)
class LinerMeasurement:
    ok: bool
    code: str = ""
    property_code: str = ""
    expected: str = ""
    measured: str = ""
    reason_code: str = ""
    matched_side: str = ""


def available_liner_sides(piece_type: str | None) -> tuple[str, ...]:
    kind = piece_type or "Regular"
    if kind == CLIPPED_CORNER_TYPE:
        return OUTER_SIDES + (SIDE_BREAK, SIDE_BREAK_ONLY)
    if kind == L_SHAPED_CORNER_TYPE:
        return OUTER_SIDES + (SIDE_BREAK,)
    if kind in {"Regular", GLASS_TYPE}:
        return OUTER_SIDES
    return ()


def liner_parameters_active(
    *,
    enabled: bool,
    side: str,
    offset_cm: float,
    width_cm: float,
) -> bool:
    return bool(enabled) and bool(str(side or "").strip()) and float(width_cm or 0) > 0


def _mm(value_cm: float) -> float:
    return float(value_cm) * CM_TO_MM


def _corner_polygon(piece: LinerPiece, width: float, height: float, cut_x: float, cut_y: float) -> list[Point] | None:
    position = piece.clipped_corner_position or "Top Right"
    if piece.piece_type == L_SHAPED_CORNER_TYPE:
        polygons = {
            "Top Right": [(0.0, 0.0), (width - cut_x, 0.0), (width - cut_x, cut_y), (width, cut_y), (width, height), (0.0, height)],
            "Top Left": [(cut_x, 0.0), (width, 0.0), (width, height), (0.0, height), (0.0, cut_y), (cut_x, cut_y)],
            "Bottom Right": [(0.0, 0.0), (width, 0.0), (width, height - cut_y), (width - cut_x, height - cut_y), (width - cut_x, height), (0.0, height)],
            "Bottom Left": [(0.0, 0.0), (width, 0.0), (width, height), (cut_x, height), (cut_x, height - cut_y), (0.0, height - cut_y)],
        }
    elif piece.piece_type == CLIPPED_CORNER_TYPE:
        polygons = {
            "Top Right": [(0.0, 0.0), (width - cut_x, 0.0), (width, cut_y), (width, height), (0.0, height)],
            "Top Left": [(cut_x, 0.0), (width, 0.0), (width, height), (0.0, height), (0.0, cut_y)],
            "Bottom Right": [(0.0, 0.0), (width, 0.0), (width, height - cut_y), (width - cut_x, height), (0.0, height)],
            "Bottom Left": [(0.0, 0.0), (width, 0.0), (width, height), (cut_x, height), (0.0, height - cut_y)],
        }
    else:
        return None
    return polygons.get(position)


_PRINT_CORNER_POSITIONS = frozenset({
    "Top Right",
    "Top Left",
    "Bottom Right",
    "Bottom Left",
})


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in {float("inf"), float("-inf")}:
        return 0.0
    return number


def printable_corner_outline_cm(piece: Mapping[str, Any]) -> list[Point] | None:
    """Order-entry outline in centimetres, without a default corner or rotation.

    Stored cut fields are distances from the saved corner. Incomplete data
    returns None so a print cannot invent a notch.
    """
    piece_type = str(piece.get("piece_type") or "")
    if piece_type not in {CLIPPED_CORNER_TYPE, L_SHAPED_CORNER_TYPE}:
        return None
    width = _finite(piece.get("width_cm"))
    length = _finite(piece.get("length_cm"))
    cut_width = _finite(piece.get("clipped_corner_width_cm"))
    cut_length = _finite(piece.get("clipped_corner_length_cm"))
    position = str(piece.get("clipped_corner_position") or "").strip()
    if width <= 0 or length <= 0:
        return None
    if cut_width <= 0 or cut_length <= 0:
        return None
    if cut_width >= width or cut_length >= length:
        return None
    if position not in _PRINT_CORNER_POSITIONS:
        return None
    outline = _corner_polygon(
        LinerPiece(
            piece_type=piece_type,
            width_cm=width,
            length_cm=length,
            clipped_corner_position=position,
            clipped_corner_width_cm=cut_width,
            clipped_corner_length_cm=cut_length,
        ),
        width,
        length,
        cut_width,
        cut_length,
    )
    return outline


def _print_corner_inputs(piece: Mapping[str, Any]) -> tuple[str, str, float, float, float, float] | None:
    piece_type = str(piece.get("piece_type") or "")
    if piece_type not in {CLIPPED_CORNER_TYPE, L_SHAPED_CORNER_TYPE}:
        return None
    width = _finite(piece.get("width_cm"))
    length = _finite(piece.get("length_cm"))
    cut_width = _finite(piece.get("clipped_corner_width_cm"))
    cut_length = _finite(piece.get("clipped_corner_length_cm"))
    position = str(piece.get("clipped_corner_position") or "").strip()
    if width <= 0 or length <= 0:
        return None
    if cut_width <= 0 or cut_length <= 0:
        return None
    if cut_width >= width or cut_length >= length:
        return None
    if position not in _PRINT_CORNER_POSITIONS:
        return None
    return piece_type, position, width, length, cut_width, cut_length


def _print_edge_path_source(
    piece_type: str,
    position: str,
    width: float,
    height: float,
    cut_x: float,
    cut_y: float,
) -> dict[str, list[Point] | None]:
    clipped = {
        "Top Right": {
            "top": [(0.0, 0.0), (width - cut_x, 0.0)],
            "right": [(width, cut_y), (width, height)],
            "bottom": [(width, height), (0.0, height)],
            "left": [(0.0, height), (0.0, 0.0)],
            "break": [(0.0, 0.0), (width - cut_x, 0.0), (width, cut_y), (width, height)],
            "breakOnly": [(width - cut_x, 0.0), (width, cut_y)],
        },
        "Top Left": {
            "top": [(cut_x, 0.0), (width, 0.0)],
            "right": [(width, 0.0), (width, height)],
            "bottom": [(width, height), (0.0, height)],
            "left": [(0.0, height), (0.0, cut_y)],
            "break": [(width, 0.0), (cut_x, 0.0), (0.0, cut_y), (0.0, height)],
            "breakOnly": [(cut_x, 0.0), (0.0, cut_y)],
        },
        "Bottom Right": {
            "top": [(0.0, 0.0), (width, 0.0)],
            "right": [(width, 0.0), (width, height - cut_y)],
            "bottom": [(width - cut_x, height), (0.0, height)],
            "left": [(0.0, height), (0.0, 0.0)],
            "break": [(width, 0.0), (width, height - cut_y), (width - cut_x, height), (0.0, height)],
            "breakOnly": [(width, height - cut_y), (width - cut_x, height)],
        },
        "Bottom Left": {
            "top": [(0.0, 0.0), (width, 0.0)],
            "right": [(width, 0.0), (width, height)],
            "bottom": [(width, height), (cut_x, height)],
            "left": [(0.0, height - cut_y), (0.0, 0.0)],
            "break": [(0.0, 0.0), (0.0, height - cut_y), (cut_x, height), (width, height)],
            "breakOnly": [(0.0, height - cut_y), (cut_x, height)],
        },
    }
    shaped_break = {
        "Top Right": [(width - cut_x, 0.0), (width - cut_x, cut_y), (width, cut_y)],
        "Top Left": [(cut_x, 0.0), (cut_x, cut_y), (0.0, cut_y)],
        "Bottom Right": [(width, height - cut_y), (width - cut_x, height - cut_y), (width - cut_x, height)],
        "Bottom Left": [(0.0, height - cut_y), (cut_x, height - cut_y), (cut_x, height)],
    }
    source = dict(clipped[position])
    if piece_type == L_SHAPED_CORNER_TYPE:
        source["break"] = shaped_break[position]
        source["breakOnly"] = None
    return source


def _inset_path_toward_center(
    path: Sequence[Point],
    width: float,
    height: float,
    inset: float,
) -> list[Point]:
    if inset <= 0 or len(path) < 2:
        return [(float(point[0]), float(point[1])) for point in path]
    center = (width / 2.0, height / 2.0)
    result: list[Point] = []
    for point in path:
        dx = center[0] - point[0]
        dy = center[1] - point[1]
        length = math.hypot(dx, dy) or 1.0
        result.append((point[0] + dx / length * inset, point[1] + dy / length * inset))
    return result


def printable_corner_edge_paths_cm(
    piece: Mapping[str, Any],
    *,
    inset: float | None = None,
) -> dict[str, list[Point] | None]:
    """Selected strap polylines in centimetres for print, matching editor routing."""
    empty = {
        "top": None,
        "bottom": None,
        "left": None,
        "right": None,
        "break": None,
        "breakOnly": None,
    }
    parsed = _print_corner_inputs(piece)
    if parsed is None:
        return empty
    piece_type, position, width, length, cut_width, cut_length = parsed
    source = _print_edge_path_source(
        piece_type, position, width, length, cut_width, cut_length
    )
    amount = (
        max(0.0, float(inset))
        if inset is not None
        else min(width, length) * 0.035
    )

    def inset_path(path: list[Point] | None) -> list[Point] | None:
        if not path:
            return None
        return _inset_path_toward_center(path, width, length, amount)

    selected = {
        "top": inset_path(source.get("top")) if piece.get("edge_width_top") else None,
        "bottom": inset_path(source.get("bottom")) if piece.get("edge_width_bottom") else None,
        "left": inset_path(source.get("left")) if piece.get("edge_long_left") else None,
        "right": inset_path(source.get("right")) if piece.get("edge_long_right") else None,
        "break": inset_path(source.get("break")) if piece.get("edge_break") else None,
        "breakOnly": (
            inset_path(source.get("breakOnly"))
            if piece.get("edge_break_only") and piece_type == CLIPPED_CORNER_TYPE
            else None
        ),
    }
    return selected


def _remaining_side_segments(
    position: str,
    width: float,
    height: float,
    cut_x: float,
    cut_y: float,
) -> dict[str, list[Point]]:
    return {
        "Top Right": {
            "width": [(0.0, 0.0), (width - cut_x, 0.0)],
            "length": [(width, cut_y), (width, height)],
        },
        "Top Left": {
            "width": [(cut_x, 0.0), (width, 0.0)],
            "length": [(0.0, height), (0.0, cut_y)],
        },
        "Bottom Right": {
            "width": [(width - cut_x, height), (0.0, height)],
            "length": [(width, 0.0), (width, height - cut_y)],
        },
        "Bottom Left": {
            "width": [(width, height), (cut_x, height)],
            "length": [(0.0, height - cut_y), (0.0, 0.0)],
        },
    }[position]


def printable_remaining_dimension_anchors_cm(
    piece: Mapping[str, Any],
    *,
    offset: float | None = None,
) -> list[dict[str, Any]]:
    """Label anchors for remaining width/length sides in centimetres."""
    parsed = _print_corner_inputs(piece)
    if parsed is None:
        return []
    _piece_type, position, width, length, cut_width, cut_length = parsed
    segments = _remaining_side_segments(position, width, length, cut_width, cut_length)
    label_offset = (
        max(0.0, float(offset))
        if offset is not None
        else min(width, length) * 0.08
    )
    center = (width / 2.0, length / 2.0)
    remaining_width = round(width - cut_width, 3)
    remaining_length = round(length - cut_length, 3)
    anchors: list[dict[str, Any]] = []
    for axis, value, segment in (
        ("width", remaining_width, segments["width"]),
        ("length", remaining_length, segments["length"]),
    ):
        if value <= 0 or len(segment) < 2:
            continue
        start, end = segment[0], segment[1]
        mid_x = (start[0] + end[0]) / 2.0
        mid_y = (start[1] + end[1]) / 2.0
        nx = start[1] - end[1]
        ny = end[0] - start[0]
        normal_length = math.hypot(nx, ny) or 1.0
        nx /= normal_length
        ny /= normal_length
        if (mid_x - center[0]) * nx + (mid_y - center[1]) * ny < 0:
            nx = -nx
            ny = -ny
        side_length = math.hypot(end[0] - start[0], end[1] - start[1])
        short = side_length < min(width, length) * 0.22
        # Length sits beside a vertical edge with middle anchoring; keep it clear
        # of the outline more than the width label above/below a horizontal edge.
        used_offset = label_offset * 1.35 if short else label_offset
        if axis == "length":
            used_offset *= 2.9
        anchors.append(
            {
                "axis": axis,
                "value": value,
                "midX": mid_x,
                "midY": mid_y,
                "x": mid_x + nx * used_offset,
                "y": mid_y + ny * used_offset,
                "nx": nx,
                "ny": ny,
                "short": short,
            }
        )
    return anchors


def piece_polygon_mm(piece: LinerPiece) -> list[Point]:
    width = _mm(piece.width_cm)
    height = _mm(piece.length_cm)
    if piece.piece_type not in {CLIPPED_CORNER_TYPE, L_SHAPED_CORNER_TYPE}:
        return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    cut_x = min(max(_mm(piece.clipped_corner_width_cm), 0.0), width * 0.95)
    cut_y = min(max(_mm(piece.clipped_corner_length_cm), 0.0), height * 0.95)
    polygon = _corner_polygon(piece, width, height, cut_x, cut_y)
    if polygon is None:
        raise LinerGeometryError("invalid_corner")
    return polygon


def _edge_paths(piece: LinerPiece) -> dict[str, list[Point]]:
    width = _mm(piece.width_cm)
    height = _mm(piece.length_cm)
    if piece.piece_type not in {CLIPPED_CORNER_TYPE, L_SHAPED_CORNER_TYPE}:
        return {
            SIDE_TOP: [(0.0, 0.0), (width, 0.0)],
            SIDE_BOTTOM: [(0.0, height), (width, height)],
            SIDE_LEFT: [(0.0, 0.0), (0.0, height)],
            SIDE_RIGHT: [(width, 0.0), (width, height)],
        }
    cut_x = min(max(_mm(piece.clipped_corner_width_cm), 0.0), width * 0.95)
    cut_y = min(max(_mm(piece.clipped_corner_length_cm), 0.0), height * 0.95)
    position = piece.clipped_corner_position or "Top Right"
    clipped = {
        "Top Right": {
            SIDE_TOP: [(0.0, 0.0), (width - cut_x, 0.0)],
            SIDE_RIGHT: [(width, cut_y), (width, height)],
            SIDE_BOTTOM: [(width, height), (0.0, height)],
            SIDE_LEFT: [(0.0, height), (0.0, 0.0)],
            SIDE_BREAK: [(0.0, 0.0), (width - cut_x, 0.0), (width, cut_y), (width, height)],
            SIDE_BREAK_ONLY: [(width - cut_x, 0.0), (width, cut_y)],
        },
        "Top Left": {
            SIDE_TOP: [(cut_x, 0.0), (width, 0.0)],
            SIDE_RIGHT: [(width, 0.0), (width, height)],
            SIDE_BOTTOM: [(width, height), (0.0, height)],
            SIDE_LEFT: [(0.0, height), (0.0, cut_y)],
            SIDE_BREAK: [(width, 0.0), (cut_x, 0.0), (0.0, cut_y), (0.0, height)],
            SIDE_BREAK_ONLY: [(cut_x, 0.0), (0.0, cut_y)],
        },
        "Bottom Right": {
            SIDE_TOP: [(0.0, 0.0), (width, 0.0)],
            SIDE_RIGHT: [(width, 0.0), (width, height - cut_y)],
            SIDE_BOTTOM: [(width - cut_x, height), (0.0, height)],
            SIDE_LEFT: [(0.0, height), (0.0, 0.0)],
            SIDE_BREAK: [(width, 0.0), (width, height - cut_y), (width - cut_x, height), (0.0, height)],
            SIDE_BREAK_ONLY: [(width, height - cut_y), (width - cut_x, height)],
        },
        "Bottom Left": {
            SIDE_TOP: [(0.0, 0.0), (width, 0.0)],
            SIDE_RIGHT: [(width, 0.0), (width, height)],
            SIDE_BOTTOM: [(width, height), (cut_x, height)],
            SIDE_LEFT: [(0.0, height - cut_y), (0.0, 0.0)],
            SIDE_BREAK: [(0.0, 0.0), (0.0, height - cut_y), (cut_x, height), (width, height)],
            SIDE_BREAK_ONLY: [(0.0, height - cut_y), (cut_x, height)],
        },
    }
    shaped = {
        "Top Right": {
            SIDE_BREAK: [(width - cut_x, 0.0), (width - cut_x, cut_y), (width, cut_y)],
        },
        "Top Left": {
            SIDE_BREAK: [(cut_x, 0.0), (cut_x, cut_y), (0.0, cut_y)],
        },
        "Bottom Right": {
            SIDE_BREAK: [(width, height - cut_y), (width - cut_x, height - cut_y), (width - cut_x, height)],
        },
        "Bottom Left": {
            SIDE_BREAK: [(0.0, height - cut_y), (cut_x, height - cut_y), (cut_x, height)],
        },
    }
    paths = dict(clipped[position])
    if piece.piece_type == L_SHAPED_CORNER_TYPE:
        paths[SIDE_BREAK] = shaped[position][SIDE_BREAK]
        paths.pop(SIDE_BREAK_ONLY, None)
    return paths


def reference_polyline_mm(piece: LinerPiece, side: str) -> list[Point]:
    paths = _edge_paths(piece)
    path = paths.get(side)
    if not path or len(path) < 2:
        raise LinerGeometryError("side_unavailable")
    return path


def _left_normal(start: Point, end: Point) -> Point:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    return (-dy / length, dx / length)


def _inward_sign(polyline: Sequence[Point], polygon: Sequence[Point]) -> float:
    best_length = -1.0
    segment = (polyline[0], polyline[1])
    for start, end in zip(polyline, polyline[1:]):
        length = math.dist(start, end)
        if length > best_length:
            best_length = length
            segment = (start, end)
    start, end = segment
    normal = _left_normal(start, end)
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    probe = (midpoint[0] + normal[0], midpoint[1] + normal[1])
    if point_in_polygon(probe, polygon):
        return 1.0
    return -1.0


def _offset_segment(start: Point, end: Point, distance: float, sign: float) -> tuple[Point, Point]:
    normal = _left_normal(start, end)
    shift = (sign * normal[0] * distance, sign * normal[1] * distance)
    return (
        (start[0] + shift[0], start[1] + shift[1]),
        (end[0] + shift[0], end[1] + shift[1]),
    )


def _intersect_offset_lines(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> Point | None:
    """Miter where two neighbouring offset lines meet. Parallel lines have none."""

    start, end = first
    other_start, other_end = second
    direction = (end[0] - start[0], end[1] - start[1])
    other = (other_end[0] - other_start[0], other_end[1] - other_start[1])
    denominator = direction[0] * other[1] - direction[1] * other[0]
    if abs(denominator) <= 1e-9:
        return None
    step = (
        (other_start[0] - start[0]) * other[1]
        - (other_start[1] - start[1]) * other[0]
    ) / denominator
    return (start[0] + direction[0] * step, start[1] + direction[1] * step)


def _offset_polyline(polyline: Sequence[Point], distance: float, sign: float) -> list[Point]:
    segments = [
        _offset_segment(start, end, distance, sign)
        for start, end in zip(polyline, polyline[1:])
    ]
    if not segments:
        return []
    points = [segments[0][0]]
    for previous, current in zip(segments, segments[1:]):
        joint = _intersect_offset_lines(previous, current)
        points.append(joint if joint is not None else previous[1])
    points.append(segments[-1][1])
    return points


def liner_strip_polygon_mm(piece: LinerPiece, side: str, offset_cm: float, width_cm: float) -> list[Point]:
    error = validation_code(piece, side, offset_cm, width_cm)
    if error:
        raise LinerGeometryError(error)
    polygon = piece_polygon_mm(piece)
    reference = reference_polyline_mm(piece, side)
    sign = _inward_sign(reference, polygon)
    offset = _mm(offset_cm)
    width = _mm(width_cm)
    near = _offset_polyline(reference, offset, sign)
    far = _offset_polyline(reference, offset + width, sign)
    return near + list(reversed(far))


def liner_region_polygon_mm(
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    start_cm: float | None = None,
    length_cm: float | None = None,
) -> list[Point]:
    """Mill rectangle/band for the ordered start and length, not the whole edge."""

    error = validation_code(piece, side, offset_cm, width_cm)
    if error:
        raise LinerGeometryError(error)
    polygon = piece_polygon_mm(piece)
    reference, clipped, _start, _end, _boundary_start, _boundary_end = _prepared_reference(
        piece, side, start_cm, length_cm
    )
    sign = _inward_sign(reference, polygon)
    near = _offset_polyline(clipped, _mm(offset_cm), sign)
    far = _offset_polyline(clipped, _mm(offset_cm) + _mm(width_cm), sign)
    return near + list(reversed(far))


def validation_code(piece: LinerPiece, side: str, offset_cm: float, width_cm: float) -> str:
    if piece.width_cm <= 0 or piece.length_cm <= 0:
        return "missing_dimensions"
    if piece.piece_type in {CLIPPED_CORNER_TYPE, L_SHAPED_CORNER_TYPE}:
        if piece.clipped_corner_width_cm <= 0 or piece.clipped_corner_length_cm <= 0:
            return "missing_corner"
        if piece.clipped_corner_position not in {"Top Right", "Top Left", "Bottom Right", "Bottom Left"}:
            return "invalid_corner"
    if side not in available_liner_sides(piece.piece_type):
        return "side_unavailable"
    try:
        offset = float(offset_cm)
        width = float(width_cm)
    except (TypeError, ValueError):
        return "width_invalid"
    if not math.isfinite(offset) or offset < 0:
        return "offset_invalid"
    if not math.isfinite(width) or width <= 0:
        return "width_invalid"
    polygon = piece_polygon_mm(piece)
    reference = reference_polyline_mm(piece, side)
    sign = _inward_sign(reference, polygon)
    near = _offset_polyline(reference, _mm(offset), sign)
    far = _offset_polyline(reference, _mm(offset) + _mm(width), sign)
    strip = near + list(reversed(far))
    for point in strip:
        if not point_in_polygon(point, polygon, tolerance=GEOMETRY_TOLERANCE_MM):
            return "strip_outside"
    if has_self_intersection(strip, GEOMETRY_TOLERANCE_MM):
        return "strip_outside"
    return ""


def _segment_distance(point: Point, start: Point, end: Point) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.dist(point, start), 0.0
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    ratio = min(1.0, max(0.0, ratio))
    nearest = (start[0] + dx * ratio, start[1] + dy * ratio)
    return math.dist(point, nearest), ratio


def _distances(path: Sequence[Point], reference: Sequence[Point]) -> list[float]:
    distances: list[float] = []
    segments = list(zip(reference, reference[1:]))
    for point in path:
        best = min(_segment_distance(point, start, end)[0] for start, end in segments)
        distances.append(best)
    return distances


def _fmt_cm(value_mm: float) -> str:
    return f"{value_mm / CM_TO_MM:.3f}"


def _closed_ring(path: Sequence[Point]) -> list[Point]:
    ring = list(path)
    if len(ring) >= 2 and math.dist(ring[0], ring[-1]) <= GEOMETRY_TOLERANCE_MM:
        ring = ring[:-1]
    return ring


def _simplify_collinear(path: Sequence[Point]) -> list[Point]:
    """Drop extra vertices that sit on the straight edge between their neighbours."""

    ring = _closed_ring(path)
    if len(ring) < 3:
        return ring
    changed = True
    while changed and len(ring) >= 3:
        changed = False
        simplified: list[Point] = []
        count = len(ring)
        for index, point in enumerate(ring):
            previous = ring[(index - 1) % count]
            nxt = ring[(index + 1) % count]
            distance, ratio = _segment_distance(point, previous, nxt)
            if distance <= GEOMETRY_TOLERANCE_MM and -1e-9 <= ratio <= 1.0 + 1e-9:
                changed = True
                continue
            simplified.append(point)
        ring = simplified
    return ring


def _same_ring(path: Sequence[Point], expected: Sequence[Point]) -> bool:
    left = _simplify_collinear(path)
    right = _simplify_collinear(expected)
    if len(left) != len(right) or len(left) < 3:
        return False
    count = len(left)
    for reversed_ring in (False, True):
        sequence = list(reversed(right)) if reversed_ring else list(right)
        for shift in range(count):
            if all(
                math.dist(left[index], sequence[(index + shift) % count])
                <= GEOMETRY_TOLERANCE_MM
                for index in range(count)
            ):
                return True
    return False


def _boundary_bands(
    path: Sequence[Point],
    reference: Sequence[Point],
) -> tuple[float, float] | None:
    """Near distance and thickness when every vertex lies on one of two boundaries."""

    distances = _distances(path, reference)
    if not distances:
        return None
    near = min(distances)
    far = max(distances)
    if far - near <= GEOMETRY_TOLERANCE_MM:
        return None
    if any(
        min(abs(distance - near), abs(distance - far)) > GEOMETRY_TOLERANCE_MM
        for distance in distances
    ):
        return None
    return near, far - near


def _measure_against_side(
    path: Sequence[Point],
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
) -> LinerMeasurement:
    if len(path) < 2:
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "shape", side, "", "empty_path", side)
    reference = reference_polyline_mm(piece, side)
    distances = _distances(path, reference)
    if distances and max(distances) - min(distances) <= GEOMETRY_TOLERANCE_MM:
        return LinerMeasurement(
            False,
            LINER_WIDTH_NOT_MEASURABLE,
            "width",
            _fmt_cm(_mm(width_cm)),
            "",
            "width_not_measurable",
        )
    expected_offset = _mm(offset_cm)
    expected_width = _mm(width_cm)
    try:
        expected = liner_strip_polygon_mm(piece, side, offset_cm, width_cm)
    except LinerGeometryError:
        expected = None
    if (
        expected is not None
        and _same_ring(path, expected)
        and not has_self_intersection(path, GEOMETRY_TOLERANCE_MM)
    ):
        return LinerMeasurement(True, matched_side=side)
    bands = _boundary_bands(path, reference)
    if bands is None:
        return LinerMeasurement(
            False,
            LINER_SHAPE_MISMATCH,
            "shape",
            side,
            "",
            "path_does_not_follow_edge",
            side,
        )
    measured_offset, measured_width = bands
    if abs(measured_offset - expected_offset) > GEOMETRY_TOLERANCE_MM:
        return LinerMeasurement(
            False,
            LINER_OFFSET_MISMATCH,
            "offset",
            _fmt_cm(expected_offset),
            _fmt_cm(measured_offset),
            "offset_mismatch",
            side,
        )
    if abs(measured_width - expected_width) > GEOMETRY_TOLERANCE_MM:
        return LinerMeasurement(
            False,
            LINER_WIDTH_MISMATCH,
            "width",
            _fmt_cm(expected_width),
            _fmt_cm(measured_width),
            "width_mismatch",
            side,
        )
    return LinerMeasurement(
        False,
        LINER_SHAPE_MISMATCH,
        "shape",
        side,
        "",
        "path_does_not_follow_edge",
        side,
    )


def compare_liner_path(
    path: Sequence[Point],
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float | None = None,
    start_cm: float | None = None,
    length_cm: float | None = None,
    *,
    start_sawn: bool | None = None,
    end_sawn: bool | None = None,
) -> LinerMeasurement:
    """Compare a canonical-frame path with the ordered liner band or toolpath.

    A closed strip is still the geometry representation. An open zigzag is the
    cutter-center toolpath and is judged only when the plan blade kerf is a
    positive diameter. A missing diameter never becomes an assumed default.
    """

    selected = _measure_against_side(path, piece, side, offset_cm, width_cm)
    if selected.ok:
        return selected
    tool = None
    if _positive_diameter(cutter_diameter_mm):
        tool = _measure_toolpath(
            path,
            piece,
            side,
            offset_cm,
            width_cm,
            float(cutter_diameter_mm or 0),
            start_cm,
            length_cm,
            start_sawn=start_sawn,
            end_sawn=end_sawn,
        )
        if tool.ok:
            return tool
        if tool.reason_code in {"end_not_closed", "extension_short"}:
            legacy = _measure_toolpath(
                path,
                piece,
                side,
                offset_cm,
                width_cm,
                float(cutter_diameter_mm or 0),
                start_cm,
                length_cm,
                start_sawn=start_sawn,
                end_sawn=end_sawn,
                flat_contour=True,
            )
            if legacy.ok:
                return legacy
    if selected.code != LINER_WIDTH_NOT_MEASURABLE or tool is not None:
        for candidate in available_liner_sides(piece.piece_type):
            if candidate == side:
                continue
            other = _measure_against_side(path, piece, candidate, offset_cm, width_cm)
            if other.ok or (
                tool is not None
                and _measure_toolpath(
                    path,
                    piece,
                    candidate,
                    offset_cm,
                    width_cm,
                    float(cutter_diameter_mm or 0),
                    start_cm,
                    length_cm,
                ).ok
            ):
                return LinerMeasurement(
                    False,
                    LINER_SIDE_MISMATCH,
                    "side",
                    side,
                    candidate,
                    "side_mismatch",
                    candidate,
                )
    if tool is not None and selected.code in {LINER_SHAPE_MISMATCH, LINER_WIDTH_NOT_MEASURABLE}:
        return tool
    return selected


def cutter_center_offsets_mm(width_mm: float, diameter_mm: float) -> list[float]:
    """Centers across the liner width, measured from the edge nearest the reference.

    The first center sits one radius in from that edge and the last sits one
    radius in from the far edge. Intermediate centers share the remainder so
    neighbouring cuts touch or overlap and the tool never crosses the width.
    """

    if (
        not math.isfinite(width_mm)
        or not math.isfinite(diameter_mm)
        or diameter_mm <= GEOMETRY_TOLERANCE_MM
        or width_mm <= GEOMETRY_TOLERANCE_MM
    ):
        raise LinerGeometryError("cutter_diameter_invalid")
    if width_mm + GEOMETRY_TOLERANCE_MM < diameter_mm:
        raise LinerGeometryError("liner_narrower_than_cutter")
    radius = diameter_mm / 2.0
    if abs(width_mm - diameter_mm) <= GEOMETRY_TOLERANCE_MM:
        return [width_mm / 2.0]
    # Full tool steps from both edges. The leftover, which is at most one
    # diameter, sits in one interior gap instead of being spread evenly.
    leading = [radius]
    trailing = [width_mm - radius]
    while trailing[0] - leading[-1] > diameter_mm + 1e-9:
        leading.append(leading[-1] + diameter_mm)
        if trailing[0] - leading[-1] > diameter_mm + 1e-9:
            trailing.insert(0, trailing[0] - diameter_mm)
    return leading + trailing


def _polyline_length(path: Sequence[Point]) -> float:
    return sum(math.dist(start, end) for start, end in zip(path, path[1:]))


def _point_along(path: Sequence[Point], distance: float) -> tuple[Point, int]:
    if len(path) < 2:
        raise LinerGeometryError("side_unavailable")
    if distance <= 1e-9:
        return path[0], 0
    walked = 0.0
    for index, (start, end) in enumerate(zip(path, path[1:])):
        length = math.dist(start, end)
        if walked + length >= distance - 1e-9:
            ratio = 0.0 if length <= 1e-12 else min(1.0, max(0.0, (distance - walked) / length))
            return (
                (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio),
                index,
            )
        walked += length
    return path[-1], len(path) - 2


def _subpolyline(path: Sequence[Point], start_mm: float, end_mm: float) -> list[Point]:
    total = _polyline_length(path)
    if start_mm <= GEOMETRY_TOLERANCE_MM and end_mm >= total - GEOMETRY_TOLERANCE_MM:
        return list(path)
    start_point, start_index = _point_along(path, start_mm)
    end_point, end_index = _point_along(path, end_mm)
    points = [start_point]
    for index in range(start_index + 1, end_index + 1):
        vertex = path[index]
        if math.dist(points[-1], vertex) > 1e-6:
            points.append(vertex)
    if math.dist(points[-1], end_point) > 1e-6:
        points.append(end_point)
    if len(points) < 2:
        points.append(end_point)
    return points


def _span_hits_bend(path: Sequence[Point], start_mm: float, end_mm: float) -> bool:
    """True when a partial limit sits on an interior bend with no single direction."""

    total = _polyline_length(path)
    walked = 0.0
    for index, (start, end) in enumerate(zip(path, path[1:])):
        walked += math.dist(start, end)
        if index >= len(path) - 2:
            continue
        if walked <= GEOMETRY_TOLERANCE_MM or abs(walked - total) <= GEOMETRY_TOLERANCE_MM:
            continue
        if (
            abs(walked - start_mm) <= GEOMETRY_TOLERANCE_MM
            or abs(walked - end_mm) <= GEOMETRY_TOLERANCE_MM
        ):
            return True
    return False


def resolved_liner_span_mm(
    piece: LinerPiece,
    side: str,
    start_cm: float | None = None,
    length_cm: float | None = None,
) -> tuple[float, float, str]:
    """Return start and length in millimetres along the reference edge.

    A missing length, or a stored zero from an order saved before this field
    existed, means the remainder of the edge. An explicit positive length is
    kept and must fit on the edge.
    """

    reference = reference_polyline_mm(piece, side)
    edge = _polyline_length(reference)
    if start_cm in (None, ""):
        start = 0.0
    else:
        try:
            start = float(start_cm) * CM_TO_MM
        except (TypeError, ValueError):
            return 0.0, edge, "liner_start_invalid"
    if not math.isfinite(start) or start < -GEOMETRY_TOLERANCE_MM:
        return 0.0, 0.0, "liner_start_invalid"
    start = max(0.0, start)
    legacy_full = length_cm in (None, "")
    if not legacy_full:
        try:
            length = float(length_cm) * CM_TO_MM
        except (TypeError, ValueError):
            return start, 0.0, "liner_length_invalid"
        if not math.isfinite(length):
            return start, 0.0, "liner_length_invalid"
        if length <= GEOMETRY_TOLERANCE_MM:
            length = edge - start
    else:
        length = edge - start
    if length <= GEOMETRY_TOLERANCE_MM:
        return start, length, "liner_length_invalid"
    if start + length > edge + GEOMETRY_TOLERANCE_MM:
        return start, length, "liner_span_exceeds_edge"
    return start, min(length, max(0.0, edge - start)), ""


def _prepared_reference(
    piece: LinerPiece,
    side: str,
    start_cm: float | None,
    length_cm: float | None,
) -> tuple[list[Point], list[Point], float, float, bool, bool]:
    reference = reference_polyline_mm(piece, side)
    start_mm, length_mm, span_error = resolved_liner_span_mm(piece, side, start_cm, length_cm)
    if span_error:
        raise LinerGeometryError(span_error)
    end_mm = start_mm + length_mm
    if _span_hits_bend(reference, start_mm, end_mm):
        raise LinerGeometryError("liner_span_on_corner")
    edge = _polyline_length(reference)
    return (
        reference,
        _subpolyline(reference, start_mm, end_mm),
        start_mm,
        end_mm,
        start_mm <= GEOMETRY_TOLERANCE_MM,
        abs(end_mm - edge) <= GEOMETRY_TOLERANCE_MM,
    )


def liner_centerline_mm(
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    start_cm: float | None = None,
    length_cm: float | None = None,
) -> list[Point]:
    """One open line through the middle of the liner strip.

    The distance from the reference edge is the ordered offset plus half the
    liner width. The line follows that edge, including an L bend or a clipped
    diagonal, and only the ordered start and length. It is not a cutter toolpath.
    """

    error = validation_code(piece, side, offset_cm, width_cm)
    if error:
        raise LinerGeometryError(error)
    _reference, clipped, _start, _end, _boundary_start, _boundary_end = _prepared_reference(
        piece, side, start_cm, length_cm
    )
    polygon = piece_polygon_mm(piece)
    sign = _inward_sign(_reference, polygon)
    distance = _mm(offset_cm) + (_mm(width_cm) / 2.0)
    return _offset_polyline(clipped, distance, sign)


def _resolve_sawn(explicit: bool | None, boundary: bool) -> bool:
    """A contour end is saw-closed only when the caller says that edge is cut.

    ``None`` keeps the historical rule: the sheet is unknown, so a contour end
    is treated as sawn. An internal end is never saw-closed.
    """

    if explicit is None:
        return boundary
    return bool(explicit) and boundary


def _cutter_passes(
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float,
    start_cm: float | None,
    length_cm: float | None,
    *,
    start_sawn: bool | None = None,
    end_sawn: bool | None = None,
    flat_contour: bool = False,
) -> tuple[list[list[Point]], bool, bool]:
    """Parallel cutter passes for one liner span.

    A contour end extends by the bit radius past the door, including when that
    face is the raw board edge and the bit leaves the sheet. Missing trim is
    not a reason to shorten it. An internal end stops one radius short. A real
    saw closes a contour end; otherwise the liner path itself closes it.
    ``flat_contour`` keeps the older board-edge shorten-and-close path so a
    previously exported file still matches.
    """

    error = validation_code(piece, side, offset_cm, width_cm)
    if error:
        raise LinerGeometryError(error)
    centers = cutter_center_offsets_mm(_mm(width_cm), float(cutter_diameter_mm))
    polygon = piece_polygon_mm(piece)
    reference, clipped, _start, _end, boundary_start, boundary_end = _prepared_reference(
        piece, side, start_cm, length_cm
    )
    sign = _inward_sign(reference, polygon)
    radius = float(cutter_diameter_mm) / 2.0
    saw_start = _resolve_sawn(start_sawn, boundary_start)
    saw_end = _resolve_sawn(end_sawn, boundary_end)
    extend_start = boundary_start and not (flat_contour and not saw_start)
    extend_end = boundary_end and not (flat_contour and not saw_end)
    needs_flat = not saw_start or not saw_end
    if needs_flat and len(centers) < 2:
        raise LinerGeometryError("liner_flat_end_unmachinable")
    trim_start = 0.0 if extend_start else radius
    trim_end = 0.0 if extend_end else radius
    if _polyline_length(clipped) + GEOMETRY_TOLERANCE_MM < trim_start + trim_end:
        raise LinerGeometryError("liner_flat_end_unmachinable")
    lines: list[list[Point]] = []
    for center in centers:
        line = _offset_polyline(clipped, _mm(offset_cm) + center, sign)
        if trim_start:
            line = _subpolyline(line, trim_start, _polyline_length(line))
        if trim_end:
            line = _subpolyline(line, 0.0, _polyline_length(line) - trim_end)
        if len(line) < 2:
            raise LinerGeometryError("liner_flat_end_unmachinable")
        if extend_start or extend_end:
            line = _extend_centerline(
                line,
                radius,
                polygon,
                extend_start=extend_start,
                extend_end=extend_end,
            )
        lines.append(line)
    return lines, saw_start, saw_end


def _collinear_point(start: Point, middle: Point, end: Point) -> bool:
    area = abs(
        (middle[0] - start[0]) * (end[1] - start[1])
        - (middle[1] - start[1]) * (end[0] - start[0])
    )
    return area <= GEOMETRY_TOLERANCE_MM * max(math.dist(start, end), 1.0)


def _chain_present(path: Sequence[Point], points: Sequence[Point]) -> bool:
    if len(points) < 2:
        return True
    for start_index, vertex in enumerate(path):
        if math.dist(vertex, points[0]) > GEOMETRY_TOLERANCE_MM:
            continue
        cursor = 1
        for later in path[start_index + 1 :]:
            if math.dist(later, points[cursor]) <= GEOMETRY_TOLERANCE_MM:
                cursor += 1
                if cursor == len(points):
                    return True
                continue
            if not _collinear_point(points[cursor - 1], later, points[cursor]):
                break
    return False


def _span_present(path: Sequence[Point], endpoints: Sequence[Point]) -> bool:
    return _chain_present(path, endpoints) or _chain_present(path, list(reversed(endpoints)))


def _prepend_closure(path: list[Point], endpoints: Sequence[Point]) -> list[Point]:
    if _span_present(path, endpoints):
        return path
    ordered = list(endpoints)
    if math.dist(ordered[-1], path[0]) > GEOMETRY_TOLERANCE_MM:
        ordered.reverse()
    if math.dist(ordered[-1], path[0]) > GEOMETRY_TOLERANCE_MM:
        raise LinerGeometryError("liner_extension_unsafe")
    return ordered[:-1] + path


def _append_closure(path: list[Point], endpoints: Sequence[Point], return_pass: Sequence[Point]) -> list[Point]:
    if _span_present(path, endpoints):
        return path
    points = list(path)
    if min(math.dist(points[-1], endpoints[0]), math.dist(points[-1], endpoints[-1])) > GEOMETRY_TOLERANCE_MM:
        retrace = list(return_pass)
        if math.dist(points[-1], retrace[0]) > GEOMETRY_TOLERANCE_MM:
            retrace.reverse()
        if math.dist(points[-1], retrace[0]) > GEOMETRY_TOLERANCE_MM:
            raise LinerGeometryError("liner_extension_unsafe")
        points.extend(retrace[1:])
    ordered = list(endpoints)
    if math.dist(points[-1], ordered[0]) > GEOMETRY_TOLERANCE_MM:
        ordered.reverse()
    if math.dist(points[-1], ordered[0]) > GEOMETRY_TOLERANCE_MM:
        raise LinerGeometryError("liner_extension_unsafe")
    points.extend(ordered[1:])
    return points


def liner_toolpath_mm(
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float,
    start_cm: float | None = None,
    length_cm: float | None = None,
    *,
    start_sawn: bool | None = None,
    end_sawn: bool | None = None,
    flat_contour: bool = False,
) -> list[Point]:
    """Parallel cutter passes, with a straight close only where no saw finishes the end.

    Every contour end extends by the bit radius past the door, even when the
    face is the raw board edge and the cutter leaves the sheet. ``CUT_PATH``
    closes that end only when the face is a real separating or trim cut.
    Otherwise the liner path travels straight across the extended centers.
    An internal end stops one radius short and is closed the same way. The
    sheet outline is never a closer. ``flat_contour`` reproduces the older
    board-edge path that stopped one radius inside.
    """

    lines, saw_start, saw_end = _cutter_passes(
        piece,
        side,
        offset_cm,
        width_cm,
        cutter_diameter_mm,
        start_cm,
        length_cm,
        start_sawn=start_sawn,
        end_sawn=end_sawn,
        flat_contour=flat_contour,
    )
    path: list[Point] = []
    for index, line in enumerate(lines):
        sequence = line if index % 2 == 0 else list(reversed(line))
        if path and math.dist(path[-1], sequence[0]) <= 1e-6:
            sequence = sequence[1:]
        path.extend(sequence)
    if not saw_start:
        path = _prepend_closure(path, [line[0] for line in lines])
    if not saw_end:
        path = _append_closure(path, [line[-1] for line in lines], lines[-1])
    return path


def _positive_diameter(value: float | None) -> bool:
    try:
        diameter = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(diameter) and diameter > GEOMETRY_TOLERANCE_MM


def _boundary_distance(point: Point, polygon: Sequence[Point]) -> float:
    edges = list(zip(polygon, polygon[1:]))
    if polygon and math.dist(polygon[0], polygon[-1]) > 1e-9:
        edges.append((polygon[-1], polygon[0]))
    if not edges:
        return math.inf
    return min(_segment_distance(point, start, end)[0] for start, end in edges)


def _ray_exit(origin: Point, direction: Point, polygon: Sequence[Point]) -> Point | None:
    edges = list(zip(polygon, polygon[1:]))
    if polygon and math.dist(polygon[0], polygon[-1]) > 1e-9:
        edges.append((polygon[-1], polygon[0]))
    best: float | None = None
    for start, end in edges:
        edge = (end[0] - start[0], end[1] - start[1])
        denominator = direction[0] * edge[1] - direction[1] * edge[0]
        if abs(denominator) <= 1e-12:
            continue
        offset = (start[0] - origin[0], start[1] - origin[1])
        travel = (offset[0] * edge[1] - offset[1] * edge[0]) / denominator
        along = (offset[0] * direction[1] - offset[1] * direction[0]) / denominator
        if travel <= 1e-6 or along < -1e-6 or along > 1.0 + 1e-6:
            continue
        if best is None or travel < best:
            best = travel
    if best is None:
        return None
    return (origin[0] + direction[0] * best, origin[1] + direction[1] * best)


def _extend_centerline(
    polyline: Sequence[Point],
    extension: float,
    polygon: Sequence[Point],
    *,
    extend_start: bool = True,
    extend_end: bool = True,
    start_extension: float | None = None,
    end_extension: float | None = None,
) -> list[Point]:
    points = list(polyline)
    if len(points) < 2:
        raise LinerGeometryError("liner_extension_unsafe")
    ends = []
    if extend_start:
        ends.append((0, 1))
    if extend_end:
        ends.append((-1, -2))
    for index, other_index in ends:
        origin = points[index]
        toward = points[other_index]
        direction = (origin[0] - toward[0], origin[1] - toward[1])
        length = math.hypot(direction[0], direction[1]) or 1.0
        direction = (direction[0] / length, direction[1] / length)
        if _boundary_distance(origin, polygon) <= GEOMETRY_TOLERANCE_MM:
            hit = origin
        else:
            hit = _ray_exit(origin, direction, polygon)
            if hit is None:
                raise LinerGeometryError("liner_extension_unsafe")
        amount = extension
        if index == 0 and start_extension is not None:
            amount = start_extension
        if index != 0 and end_extension is not None:
            amount = end_extension
        points[index] = (
            hit[0] + direction[0] * amount,
            hit[1] + direction[1] * amount,
        )
    return points


def _path_distance(point: Point, path: Sequence[Point]) -> float:
    if len(path) < 2:
        return math.inf
    return min(
        _segment_distance(point, start, end)[0]
        for start, end in zip(path, path[1:])
    )


def _sample_width(reference: Sequence[Point], polygon: Sequence[Point], distance: float) -> list[Point]:
    """Samples on the mitered offset, which is the band the cutter actually follows.

    A per-segment normal near a bend lands outside that band, in the wedge the
    miter cuts off. Those points are not unmilled liner material.
    """

    sign = _inward_sign(reference, polygon)
    curve = _offset_polyline(reference, distance, sign)
    samples: list[Point] = []
    for start, end in zip(curve, curve[1:]):
        length = math.dist(start, end)
        if length <= GEOMETRY_TOLERANCE_MM:
            continue
        steps = max(2, int(length // 40.0))
        for step in range(1, steps):
            ratio = step / steps
            samples.append((
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            ))
    return samples


def _longitudinal_samples(
    reference: Sequence[Point],
    polygon: Sequence[Point],
    distance_mm: float,
    offset_mm: float,
    width_mm: float,
) -> list[Point]:
    point, index = _point_along(reference, distance_mm)
    start = reference[index]
    end = reference[index + 1]
    sign = _inward_sign(reference, polygon)
    normal = _left_normal(start, end)
    return [
        (
            point[0] + sign * normal[0] * (offset_mm + width_mm * station),
            point[1] + sign * normal[1] * (offset_mm + width_mm * station),
        )
        for station in (0.2, 0.5, 0.8)
    ]


def _measure_toolpath(
    path: Sequence[Point],
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float,
    start_cm: float | None = None,
    length_cm: float | None = None,
    *,
    start_sawn: bool | None = None,
    end_sawn: bool | None = None,
    flat_contour: bool = False,
) -> LinerMeasurement:
    try:
        expected = liner_toolpath_mm(
            piece,
            side,
            offset_cm,
            width_cm,
            cutter_diameter_mm,
            start_cm,
            length_cm,
            start_sawn=start_sawn,
            end_sawn=end_sawn,
            flat_contour=flat_contour,
        )
        centers = cutter_center_offsets_mm(_mm(width_cm), cutter_diameter_mm)
        reference, clipped, start_mm, end_mm, boundary_start, boundary_end = _prepared_reference(
            piece, side, start_cm, length_cm
        )
    except LinerGeometryError as error:
        code = LINER_WIDTH_MISMATCH if error.code == "liner_narrower_than_cutter" else LINER_SHAPE_MISMATCH
        return LinerMeasurement(
            False,
            code,
            "width" if code == LINER_WIDTH_MISMATCH else "shape",
            _fmt_cm(_mm(width_cm)),
            _fmt_cm(cutter_diameter_mm),
            error.code,
            side,
        )
    radius = cutter_diameter_mm / 2.0
    polygon = piece_polygon_mm(piece)
    offset_mm = _mm(offset_cm)
    width_mm = _mm(width_cm)
    inside = []
    for station in (0.2, 0.5, 0.8):
        inside.extend(_sample_width(clipped, polygon, offset_mm + (width_mm * station)))
    outside_gap = max(1.0, GEOMETRY_TOLERANCE_MM * 4)
    outside = _sample_width(clipped, polygon, offset_mm - outside_gap)
    outside.extend(_sample_width(clipped, polygon, offset_mm + width_mm + outside_gap))
    edge = _polyline_length(reference)
    beyond_start = []
    beyond_end = []
    if not boundary_start and start_mm - outside_gap >= 0:
        beyond_start = _longitudinal_samples(
            reference, polygon, start_mm - outside_gap, offset_mm, width_mm
        )
    if not boundary_end and end_mm + outside_gap <= edge:
        beyond_end = _longitudinal_samples(
            reference, polygon, end_mm + outside_gap, offset_mm, width_mm
        )
    if any(_path_distance(point, path) <= radius - GEOMETRY_TOLERANCE_MM for point in beyond_start):
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "start", side, "", "start_mismatch", side)
    if any(_path_distance(point, path) <= radius - GEOMETRY_TOLERANCE_MM for point in beyond_end):
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "length", side, "", "length_mismatch", side)
    if any(_path_distance(point, path) > radius + GEOMETRY_TOLERANCE_MM for point in inside):
        return LinerMeasurement(
            False,
            LINER_SHAPE_MISMATCH,
            "shape",
            side,
            "",
            "coverage_gap",
            side,
        )
    if any(_path_distance(point, path) <= radius - GEOMETRY_TOLERANCE_MM for point in outside):
        near = _sample_width(reference, polygon, offset_mm - outside_gap)
        near_cut = any(_path_distance(point, path) <= radius - GEOMETRY_TOLERANCE_MM for point in near)
        return LinerMeasurement(
            False,
            LINER_OFFSET_MISMATCH if near_cut else LINER_WIDTH_MISMATCH,
            "offset" if near_cut else "width",
            _fmt_cm(offset_mm if near_cut else width_mm),
            "",
            "tool_overcut",
            side,
        )
    passes, saw_start, saw_end = _cutter_passes(
        piece,
        side,
        offset_cm,
        width_cm,
        cutter_diameter_mm,
        start_cm,
        length_cm,
        start_sawn=start_sawn,
        end_sawn=end_sawn,
        flat_contour=flat_contour,
    )
    if not saw_start and not _span_present(path, [line[0] for line in passes]):
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "start", side, "", "end_not_closed", side)
    if not saw_end and not _span_present(path, [line[-1] for line in passes]):
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "length", side, "", "end_not_closed", side)
    end_short = any(
        _path_distance(point, path) > GEOMETRY_TOLERANCE_MM
        for point in (expected[0], expected[-1])
    )
    outside_path = [
        point for point in path
        if not point_in_polygon(point, polygon, tolerance=GEOMETRY_TOLERANCE_MM)
    ]
    if any(
        _boundary_distance(point, polygon) > radius + GEOMETRY_TOLERANCE_MM
        for point in outside_path
    ):
        end_short = True
    if end_short:
        return LinerMeasurement(
            False,
            LINER_SHAPE_MISMATCH,
            "shape",
            _fmt_cm(radius),
            "",
            "extension_short",
            side,
        )
    if not centers:
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "shape", side, "", "coverage_gap", side)
    return LinerMeasurement(True, matched_side=side)


def contour_notch_cm(
    *,
    piece_type: str | None,
    finished_width_cm: float,
    finished_length_cm: float,
    notch_width_cm: float,
    notch_length_cm: float,
    position: str,
    side_thickness_mm: dict | None = None,
    edge_break: bool = False,
    edge_break_thickness_mm: float | None = None,
) -> tuple[float, float]:
    """Notch used by the liner and by the L cut contour.

    Finished corner distances stay on the order. An L door uses the raw bite
    from the existing strap rule once the inner thickness is known. An unknown
    inner thickness keeps the stored finished notch instead of inventing one.
    """

    finished = (float(notch_width_cm or 0), float(notch_length_cm or 0))
    if piece_type != L_SHAPED_CORNER_TYPE:
        return finished
    try:
        raw = l_shaped_raw_cut(
            finished_width_cm=finished_width_cm,
            finished_length_cm=finished_length_cm,
            notch_width_cm=notch_width_cm,
            notch_length_cm=notch_length_cm,
            position=position,
            side_thickness_mm=side_thickness_mm or {},
            edge_break=edge_break,
            edge_break_thickness_mm=edge_break_thickness_mm,
        )
    except CutDimensionError:
        return finished
    if (
        not raw.proven
        or raw.raw_notch_width_cm is None
        or raw.raw_notch_length_cm is None
    ):
        return finished
    return float(raw.raw_notch_width_cm), float(raw.raw_notch_length_cm)


def liner_activation_error(
    *,
    enabled: bool,
    piece_type: str | None,
    side: str,
    offset_cm: float,
    width_cm: float,
    legacy_checkbox_only: bool,
) -> str:
    """Reject a new enabled liner that has no usable parameters.

    A saved checkbox-only row stays valid. Special doors have no liner geometry.
    """

    if not enabled or not available_liner_sides(piece_type):
        return ""
    blank = (
        not str(side or "").strip()
        and float(offset_cm or 0) <= 0
        and float(width_cm or 0) <= 0
    )
    if blank and not legacy_checkbox_only:
        return "liner_parameters_required"
    return ""


def transform_point(
    point: Point,
    *,
    mirrored: bool,
    quarter_turns: int,
    width: float,
    height: float,
) -> Point:
    """Horizontal reflection, then clockwise quarter-turns. Matches corner contours."""

    x, y = point
    box_width, box_height = width, height
    if mirrored:
        x = box_width - x
    for _ in range(int(quarter_turns)):
        x, y = box_height - y, x
        box_width, box_height = box_height, box_width
    return (x, y)


_BOARD_EDGE_TOLERANCE_MM = 0.05


def _transform_direction(
    direction: Point,
    *,
    mirrored: bool,
    quarter_turns: int,
    width: float,
    height: float,
) -> Point:
    origin = transform_point(
        (0.0, 0.0),
        mirrored=mirrored,
        quarter_turns=quarter_turns,
        width=width,
        height=height,
    )
    moved = transform_point(
        direction,
        mirrored=mirrored,
        quarter_turns=quarter_turns,
        width=width,
        height=height,
    )
    return (moved[0] - origin[0], moved[1] - origin[1])


def _ring_edges(polygon: Sequence[Point]) -> list[tuple[Point, Point]]:
    points = [(float(point[0]), float(point[1])) for point in polygon]
    if len(points) >= 2 and math.dist(points[0], points[-1]) <= 1e-9:
        points = points[:-1]
    if len(points) < 2:
        return []
    return list(zip(points, points[1:] + points[:1]))


def _edge_lies_on_board(
    start: Point,
    end: Point,
    board: Sequence[float],
    tolerance: float = _BOARD_EDGE_TOLERANCE_MM,
) -> bool:
    min_x, min_y, max_x, max_y = (float(value) for value in board)
    sides = ((0, min_x), (0, max_x), (1, min_y), (1, max_y))
    return any(
        abs(start[axis] - value) <= tolerance and abs(end[axis] - value) <= tolerance
        for axis, value in sides
    )


def _face_edge(
    polygon: Sequence[Point],
    point: Point,
    direction: Point,
) -> tuple[Point, Point] | None:
    """The contour edge the liner runs into, not the edge it travels along."""

    length = math.hypot(direction[0], direction[1]) or 1.0
    unit = (direction[0] / length, direction[1] / length)
    best: tuple[Point, Point] | None = None
    best_score = -1.0
    for start, end in _ring_edges(polygon):
        if _segment_distance(point, start, end)[0] > GEOMETRY_TOLERANCE_MM:
            continue
        normal = _left_normal(start, end)
        score = abs(normal[0] * unit[0] + normal[1] * unit[1])
        if score > best_score:
            best = (start, end)
            best_score = score
    return best


def sawn_liner_ends(
    piece: LinerPiece,
    side: str,
    *,
    origin_mm: Point,
    mirrored: bool,
    quarter_turns: int,
    board: Sequence[float] | None,
    start_cm: float | None = None,
    length_cm: float | None = None,
) -> tuple[bool, bool]:
    """Whether each contour end is finished by a real saw cut.

    ``board is None`` means the sheet is unknown, so a contour end is treated
    as sawn. A known board, ``(min_x, min_y, max_x, max_y)`` in the same
    coordinates as the placed piece, saws a contour end only when the edge
    that end runs into is not the physical board edge. Each end is independent.
    """

    _reference, clipped, _start, _end, boundary_start, boundary_end = _prepared_reference(
        piece, side, start_cm, length_cm
    )
    if len(clipped) < 2:
        return boundary_start, boundary_end
    width = _mm(piece.width_cm)
    height = _mm(piece.length_cm)
    polygon = [
        transform_point(
            point,
            mirrored=mirrored,
            quarter_turns=quarter_turns,
            width=width,
            height=height,
        )
        for point in piece_polygon_mm(piece)
    ]
    placed = [
        (point[0] + float(origin_mm[0]), point[1] + float(origin_mm[1]))
        for point in polygon
    ]

    def sawn(at_start: bool, boundary: bool) -> bool:
        if not boundary:
            return False
        if board is None:
            return True
        origin = clipped[0] if at_start else clipped[-1]
        toward = clipped[1] if at_start else clipped[-2]
        direction = _transform_direction(
            (origin[0] - toward[0], origin[1] - toward[1]),
            mirrored=mirrored,
            quarter_turns=quarter_turns,
            width=width,
            height=height,
        )
        placed_origin = transform_point(
            origin,
            mirrored=mirrored,
            quarter_turns=quarter_turns,
            width=width,
            height=height,
        )
        placed_point = (
            placed_origin[0] + float(origin_mm[0]),
            placed_origin[1] + float(origin_mm[1]),
        )
        edge = _face_edge(placed, placed_point, direction)
        if edge is None:
            return True
        return not _edge_lies_on_board(edge[0], edge[1], board)

    return sawn(True, boundary_start), sawn(False, boundary_end)


def inverse_transform_point(
    point: Point,
    *,
    mirrored: bool,
    quarter_turns: int,
    width: float,
    height: float,
) -> Point:
    x, y = point
    box_width, box_height = width, height
    for _ in range(int(quarter_turns)):
        box_width, box_height = box_height, box_width
    for _ in range(int(quarter_turns)):
        x, y = y, box_width - x
        box_width, box_height = box_height, box_width
    if mirrored:
        x = width - x
    return (x, y)


def localize_path(path: Sequence[Point], outline: Sequence[Point]) -> list[Point]:
    min_x = min(point[0] for point in outline)
    min_y = min(point[1] for point in outline)
    return [(point[0] - min_x, point[1] - min_y) for point in path]


def piece_quarter_turns(piece: Mapping[str, Any] | None) -> int:
    """Resolve clockwise quarter turns for a placed plan/DXF piece."""

    if not piece:
        return 0
    if isinstance(piece.get("rotation_quarter_turns"), int):
        return int(piece["rotation_quarter_turns"]) % 4
    if isinstance(piece.get("corner_rotation_quarter_turns"), int):
        return int(piece["corner_rotation_quarter_turns"]) % 4
    return 1 if piece.get("rotated") else 0


def placement_ring_mm(piece: Mapping[str, Any]) -> list[Point]:
    x = float(piece.get("x") or 0) * CM_TO_MM
    y = float(piece.get("y") or 0) * CM_TO_MM
    width = float(piece.get("w") or 0) * CM_TO_MM
    height = float(piece.get("h") or 0) * CM_TO_MM
    if not (width > 0 and height > 0):
        return []
    return [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    ]


def placed_polygon_mm(piece: Mapping[str, Any]) -> list[Point]:
    liner = LinerPiece(
        str(piece.get("piece_type") or "Regular"),
        float(
            piece.get("cut_width_cm")
            or piece.get("width_cm")
            or piece.get("original_w")
            or piece.get("w")
            or 0
        ),
        float(
            piece.get("cut_length_cm")
            or piece.get("length_cm")
            or piece.get("original_h")
            or piece.get("h")
            or 0
        ),
        str(piece.get("clipped_corner_position") or "Top Right"),
        float(piece.get("clipped_corner_width_cm") or 0),
        float(piece.get("clipped_corner_length_cm") or 0),
    )
    local = piece_polygon_mm(liner)
    turns = piece_quarter_turns(piece)
    mirrored = bool(piece.get("corner_mirrored") or piece.get("mirrored"))
    origin_x = float(piece.get("x") or 0) * CM_TO_MM
    origin_y = float(piece.get("y") or 0) * CM_TO_MM
    width = _mm(liner.width_cm)
    height = _mm(liner.length_cm)
    placed: list[Point] = []
    for point in local:
        moved = transform_point(
            point,
            mirrored=mirrored,
            quarter_turns=turns,
            width=width,
            height=height,
        )
        placed.append((moved[0] + origin_x, moved[1] + origin_y))
    return placed


def obstacle_polygon_mm(piece: Mapping[str, Any]) -> list[Point]:
    """Compatibility outer ring for liner extension clearance."""

    return list(obstacle_geometry_mm(piece)["outer"])


def obstacle_geometry_mm(piece: Mapping[str, Any]) -> dict[str, Any]:
    """Placed material outline including openings, in usable-sheet coordinates."""

    geometry = piece.get("geometry") if isinstance(piece.get("geometry"), Mapping) else None
    outer = geometry.get("outer") if geometry else None
    if isinstance(outer, Sequence) and len(outer) >= 3:
        holes = geometry.get("holes") if isinstance(geometry.get("holes"), Sequence) else ()
        return {
            "outer": [(float(point[0]), float(point[1])) for point in outer],
            "holes": [
                [(float(point[0]), float(point[1])) for point in hole]
                for hole in holes
                if isinstance(hole, Sequence) and len(hole) >= 3
            ],
            "source": "persisted_geometry",
        }
    kind = str(piece.get("piece_type") or "Regular")
    if kind not in {CLIPPED_CORNER_TYPE, L_SHAPED_CORNER_TYPE}:
        ring = placement_ring_mm(piece)
        if len(ring) >= 3:
            holes: list[list[Point]] = []
            glass_hole = piece.get("glass_hole_local_mm")
            if kind == GLASS_TYPE and isinstance(glass_hole, Sequence) and len(glass_hole) >= 3:
                origin_x = float(piece.get("x") or 0) * CM_TO_MM
                origin_y = float(piece.get("y") or 0) * CM_TO_MM
                holes.append(
                    [
                        (origin_x + float(point[0]), origin_y + float(point[1]))
                        for point in glass_hole
                    ]
                )
            return {
                "outer": ring,
                "holes": holes,
                "source": "placement_with_glass_hole" if holes else "placement_box",
            }
    return {
        "outer": placed_polygon_mm(piece),
        "holes": [],
        "source": "placed_parametric_polygon",
    }


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    def side(p: Point, q: Point, r: Point) -> float:
        return ((q[0] - p[0]) * (r[1] - p[1])) - ((q[1] - p[1]) * (r[0] - p[0]))

    return side(a, b, c) * side(a, b, d) < -1e-8 and side(c, d, a) * side(c, d, b) < -1e-8


def _point_in_material(point: Point, outer: Sequence[Point], holes: Sequence[Sequence[Point]]) -> bool:
    if not point_in_polygon(point, outer):
        return False
    return not any(point_in_polygon(point, hole) for hole in holes)


def _obstacle_material(obstacle: Mapping[str, Any] | Sequence[Point]) -> tuple[list[Point], list[list[Point]]]:
    if isinstance(obstacle, Mapping) and "outer" in obstacle:
        outer = [(float(p[0]), float(p[1])) for p in obstacle.get("outer") or ()]
    elif isinstance(obstacle, Mapping) and "polygon" in obstacle:
        outer = [(float(p[0]), float(p[1])) for p in obstacle["polygon"]]
    elif isinstance(obstacle, Mapping):
        outer = [
            (float(obstacle.get("minX") or 0), float(obstacle.get("minY") or 0)),
            (float(obstacle.get("maxX") or 0), float(obstacle.get("minY") or 0)),
            (float(obstacle.get("maxX") or 0), float(obstacle.get("maxY") or 0)),
            (float(obstacle.get("minX") or 0), float(obstacle.get("maxY") or 0)),
        ]
    else:
        outer = [(float(p[0]), float(p[1])) for p in obstacle]
    holes = []
    if isinstance(obstacle, Mapping):
        holes = [
            [(float(p[0]), float(p[1])) for p in hole]
            for hole in obstacle.get("holes") or ()
            if isinstance(hole, Sequence) and len(hole) >= 3
        ]
    return outer, holes


def extension_conflict_details(
    path: Sequence[Point],
    diameter_mm: float,
    board: Sequence[float] | Mapping[str, float] | None,
    obstacles: Sequence[Mapping[str, Any] | Sequence[Point]],
) -> dict[str, Any] | None:
    """Describe the first material collision made by a liner cutter body.

    ``board`` is accepted for API parity with the JS port; clearance is decided
    against obstacle rings only (off-board extensions remain allowed).
    """

    del board  # reserved for callers that still pass usable-sheet bounds
    radius = float(diameter_mm) / 2.0

    for index in range(len(path) - 1):
        start = (float(path[index][0]), float(path[index][1]))
        end = (float(path[index + 1][0]), float(path[index + 1][1]))
        for obstacle_index, obstacle in enumerate(obstacles or ()):
            outer, holes = _obstacle_material(obstacle)
            if len(outer) < 3:
                continue
            boundaries = [outer, *holes]
            minimum_distance = min(
                segment_distance((start, end), edge)
                for ring in boundaries
                for edge in polygon_segments(ring)
            )
            reject_condition = ""
            if _point_in_material(start, outer, holes) or _point_in_material(end, outer, holes):
                reject_condition = "endpoint_in_material"
            elif any(
                _segments_cross(start, end, edge[0], edge[1])
                for ring in boundaries
                for edge in polygon_segments(ring)
            ):
                reject_condition = "segment_crosses_material_boundary"
            elif minimum_distance < radius - GEOMETRY_TOLERANCE_MM:
                reject_condition = "clearance_below_cutter_radius"
            if reject_condition:
                return {
                    "code": "liner_extension_hits_piece",
                    "segment_index": index,
                    "obstacle_index": obstacle_index,
                    "start": start,
                    "end": end,
                    "minimum_distance_mm": minimum_distance,
                    "cutter_radius_mm": radius,
                    "rejection_threshold_mm": radius - GEOMETRY_TOLERANCE_MM,
                    "reject_condition": reject_condition,
                    "obstacle": obstacle.get("diagnostic") if isinstance(obstacle, Mapping) else None,
                }
    return None


def extension_conflict(
    path: Sequence[Point],
    diameter_mm: float,
    board: Sequence[float] | Mapping[str, float] | None,
    obstacles: Sequence[Mapping[str, Any] | Sequence[Point]],
) -> str:
    """Return ``liner_extension_hits_piece`` when the cutter body invades material."""

    details = extension_conflict_details(path, diameter_mm, board, obstacles)
    return str(details["code"]) if details else ""


def canonical_path(
    path: Sequence[Point],
    *,
    mirrored: bool,
    quarter_turns: int,
    width_mm: float,
    height_mm: float,
) -> list[Point]:
    return [
        inverse_transform_point(
            point,
            mirrored=mirrored,
            quarter_turns=quarter_turns,
            width=width_mm,
            height=height_mm,
        )
        for point in path
    ]



@dataclass(frozen=True, slots=True)
class RecessedHandleCenter:
    ok: bool
    code: str = ""
    side: str = ""
    start_cm: float = 0.0
    offset_cm: float = 0.0


_HORIZONTAL_HANDLE_SIDES = frozenset({SIDE_TOP, SIDE_BOTTOM})
_VERTICAL_HANDLE_SIDES = frozenset({SIDE_LEFT, SIDE_RIGHT})
_HANDLE_CENTER_TOLERANCE_MM = 0.05


def _quantize_cm(value: float) -> float:
    return round(float(value) * 10000.0) / 10000.0


def _positive_cm(value: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def center_recessed_handle(
    piece: LinerPiece,
    side: str | None,
    width_cm: float,
    length_cm: float,
) -> RecessedHandleCenter:
    """Place a regular-door recessed handle on the door's geometric center.

    The reference side only sets the rectangle's direction and how start/offset
    are measured. Offset is the distance from that edge to the near side of the
    rectangle. Start is the distance along the edge. The placement is returned
    only when the existing centerline passes through the door center, so preview
    and DXF consume the same fields.
    """

    if (piece.piece_type or "") != "Regular":
        return RecessedHandleCenter(False, "unsupported_piece_type")
    resolved = str(side or "").strip() or SIDE_TOP
    horizontal = resolved in _HORIZONTAL_HANDLE_SIDES
    vertical = resolved in _VERTICAL_HANDLE_SIDES
    if not horizontal and not vertical:
        return RecessedHandleCenter(False, "side_unavailable")
    door_width = _positive_cm(piece.width_cm)
    door_height = _positive_cm(piece.length_cm)
    handle_width = _positive_cm(width_cm)
    handle_length = _positive_cm(length_cm)
    if door_width is None:
        return RecessedHandleCenter(False, "door_width_invalid")
    if door_height is None:
        return RecessedHandleCenter(False, "door_height_invalid")
    if handle_length is None:
        return RecessedHandleCenter(False, "handle_length_invalid")
    if handle_width is None:
        return RecessedHandleCenter(False, "handle_width_invalid")
    span = door_width if horizontal else door_height
    depth = door_height if horizontal else door_width
    if handle_length > span + 1e-9:
        code = "length_exceeds_door_width" if horizontal else "length_exceeds_door_height"
        return RecessedHandleCenter(False, code)
    if handle_width > depth + 1e-9:
        code = "width_exceeds_door_height" if horizontal else "width_exceeds_door_width"
        return RecessedHandleCenter(False, code)
    start_cm = _quantize_cm((span - handle_length) / 2.0)
    offset_cm = _quantize_cm((depth - handle_width) / 2.0)
    if start_cm < 0 or offset_cm < 0:
        return RecessedHandleCenter(False, "center_rejected")
    try:
        line = liner_centerline_mm(
            piece, resolved, offset_cm, handle_width, start_cm, handle_length
        )
    except LinerGeometryError as error:
        return RecessedHandleCenter(False, error.code or "center_rejected")
    if len(line) < 2:
        return RecessedHandleCenter(False, "center_rejected")
    midpoint = (
        (line[0][0] + line[-1][0]) / 2.0,
        (line[0][1] + line[-1][1]) / 2.0,
    )
    center = (_mm(door_width) / 2.0, _mm(door_height) / 2.0)
    if (
        abs(midpoint[0] - center[0]) > _HANDLE_CENTER_TOLERANCE_MM
        or abs(midpoint[1] - center[1]) > _HANDLE_CENTER_TOLERANCE_MM
    ):
        return RecessedHandleCenter(False, "center_rejected")
    return RecessedHandleCenter(True, "", resolved, start_cm, offset_cm)


def mill_regions_connected(
    first: Sequence[Point],
    second: Sequence[Point],
    *,
    tolerance: float = GEOMETRY_TOLERANCE_MM,
) -> bool:
    """True when two mill bands share interior or a boundary that should be unioned."""

    if len(first) < 3 or len(second) < 3:
        return False
    if polygons_overlap(first, second, tolerance):
        return True
    for point in first:
        if point_in_polygon(point, second, tolerance):
            return True
    for point in second:
        if point_in_polygon(point, first, tolerance):
            return True
    for edge in polygon_segments(first):
        for other in polygon_segments(second):
            if segment_distance(edge, other, tolerance) <= tolerance:
                return True
    return False


def _liner_spec_tuple(spec: Any) -> tuple[str, float, float | None, float | None]:
    if isinstance(spec, Mapping):
        return (
            str(spec.get("side") or ""),
            float(spec.get("offset_cm", spec.get("offsetCm", 0)) or 0),
            spec.get("start_cm", spec.get("startCm")),
            spec.get("length_cm", spec.get("lengthCm")),
        )
    return (
        str(getattr(spec, "side", "") or ""),
        float(getattr(spec, "offset_cm", 0) or 0),
        getattr(spec, "start_cm", None),
        getattr(spec, "length_cm", None),
    )


def _connected_liner_components(regions: Sequence[Sequence[Point]]) -> tuple[tuple[int, ...], ...]:
    remaining = set(range(len(regions)))
    components: list[tuple[int, ...]] = []
    while remaining:
        seed = min(remaining)
        group = [seed]
        remaining.remove(seed)
        queue = [seed]
        while queue:
            current = queue.pop()
            for other in list(remaining):
                if mill_regions_connected(regions[current], regions[other]):
                    remaining.remove(other)
                    group.append(other)
                    queue.append(other)
        components.append(tuple(sorted(group)))
    return tuple(components)


def _point_deep_inside(point: Point, polygon: Sequence[Point], margin_mm: float) -> bool:
    if not point_in_polygon(point, polygon, GEOMETRY_TOLERANCE_MM):
        return False
    return point_to_polygon_distance(point, polygon) > max(margin_mm, GEOMETRY_TOLERANCE_MM)


def _region_already_milled(
    region: Sequence[Point],
    covered: Sequence[Sequence[Point]],
    margin_mm: float,
) -> bool:
    samples = _sample_region(region, max(margin_mm, 2.0))
    if not samples or not covered:
        return False
    inflate = max(margin_mm, GEOMETRY_TOLERANCE_MM)
    return all(
        any(point_in_polygon(sample, previous, inflate) for previous in covered)
        for sample in samples
    )


def _clip_pass_against_covered(
    line: Sequence[Point],
    covered: Sequence[Sequence[Point]],
    keep_margin_mm: float,
) -> list[list[Point]]:
    """Drop cutter-center runs that sit fully inside an already-milled region."""

    if len(line) < 2 or not covered:
        return [list(line)] if len(line) >= 2 else []
    length = _polyline_length(line)
    if length <= GEOMETRY_TOLERANCE_MM:
        return []
    step = min(1.0, max(length / 64.0, GEOMETRY_TOLERANCE_MM * 4))
    samples: list[tuple[Point, bool]] = []
    cursor = 0.0
    while cursor <= length + 1e-9:
        point, _index = _point_along(line, min(cursor, length))
        inside = any(_point_deep_inside(point, region, keep_margin_mm) for region in covered)
        samples.append((point, inside))
        if cursor >= length:
            break
        cursor = min(length, cursor + step)
    runs: list[list[Point]] = []
    current: list[Point] = []
    for point, inside in samples:
        if inside:
            if len(current) >= 2:
                runs.append(current)
            current = []
            continue
        if current and math.dist(current[-1], point) <= GEOMETRY_TOLERANCE_MM:
            continue
        current.append(point)
    if len(current) >= 2:
        runs.append(current)
    return runs


def _chain_cutter_lines(lines: Sequence[Sequence[Point]]) -> list[Point]:
    path: list[Point] = []
    for index, line in enumerate(lines):
        if len(line) < 2:
            continue
        sequence = list(line if index % 2 == 0 else reversed(line))
        if path and math.dist(path[-1], sequence[0]) <= 1e-6:
            sequence = sequence[1:]
        path.extend(sequence)
    return path


def _close_component_path(
    path: list[Point],
    lines: Sequence[Sequence[Point]],
    *,
    saw_start: bool,
    saw_end: bool,
    junction_start: bool,
    junction_end: bool,
) -> list[Point]:
    if len(path) < 2 or not lines:
        return path
    if not saw_start and not junction_start:
        path = _prepend_closure(path, [line[0] for line in lines])
    if not saw_end and not junction_end:
        path = _append_closure(path, [line[-1] for line in lines], lines[-1])
    return path


def merged_liner_toolpaths_mm(
    piece: LinerPiece,
    specs: Sequence[Any],
    width_cm: float,
    cutter_diameter_mm: float,
    *,
    start_sawn: Sequence[bool | None] | None = None,
    end_sawn: Sequence[bool | None] | None = None,
    flat_contour: bool = False,
) -> list[list[Point]]:
    """Zigzag cutter-center paths covering the union of overlapping mill bands.

    Isolated liners keep the historical single-strip toolpath. Overlapping
    bands are milled without repeating the shared interior.
    """

    items = tuple(specs or ())
    if not items:
        return []
    radius = float(cutter_diameter_mm) / 2.0
    regions: list[list[Point]] = []
    for spec in items:
        side, offset_cm, start_cm, length_cm = _liner_spec_tuple(spec)
        regions.append(
            liner_region_polygon_mm(piece, side, offset_cm, width_cm, start_cm, length_cm)
        )
    if len(items) == 1:
        side, offset_cm, start_cm, length_cm = _liner_spec_tuple(items[0])
        return [
            liner_toolpath_mm(
                piece,
                side,
                offset_cm,
                width_cm,
                cutter_diameter_mm,
                start_cm,
                length_cm,
                start_sawn=None if not start_sawn else start_sawn[0],
                end_sawn=None if not end_sawn else end_sawn[0],
                flat_contour=flat_contour,
            )
        ]

    paths: list[list[Point]] = []
    for component in _connected_liner_components(regions):
        covered: list[list[Point]] = []
        for index in component:
            spec = items[index]
            side, offset_cm, start_cm, length_cm = _liner_spec_tuple(spec)
            if covered and _region_already_milled(regions[index], covered, radius):
                continue
            if not covered:
                paths.append(
                    liner_toolpath_mm(
                        piece,
                        side,
                        offset_cm,
                        width_cm,
                        cutter_diameter_mm,
                        start_cm,
                        length_cm,
                        start_sawn=None if not start_sawn else start_sawn[index],
                        end_sawn=None if not end_sawn else end_sawn[index],
                        flat_contour=flat_contour,
                    )
                )
                covered.append(regions[index])
                continue
            lines, saw_start, saw_end = _cutter_passes(
                piece,
                side,
                offset_cm,
                width_cm,
                cutter_diameter_mm,
                start_cm,
                length_cm,
                start_sawn=None if not start_sawn else start_sawn[index],
                end_sawn=None if not end_sawn else end_sawn[index],
                flat_contour=flat_contour,
            )
            clipped: list[list[Point]] = []
            for line in lines:
                clipped.extend(_clip_pass_against_covered(line, covered, radius))
            if not clipped:
                covered.append(regions[index])
                continue
            path = _chain_cutter_lines(clipped)
            start_pt = clipped[0][0]
            end_pt = clipped[-1][-1]
            junction_start = any(
                _point_deep_inside(start_pt, region, radius * 0.25) or (
                    point_in_polygon(start_pt, region, radius)
                )
                for region in covered
            )
            junction_end = any(
                _point_deep_inside(end_pt, region, radius * 0.25) or (
                    point_in_polygon(end_pt, region, radius)
                )
                for region in covered
            )
            path = _close_component_path(
                path,
                clipped,
                saw_start=saw_start or junction_start,
                saw_end=saw_end or junction_end,
                junction_start=junction_start,
                junction_end=junction_end,
            )
            if len(path) >= 2:
                paths.append(path)
            covered.append(regions[index])
    return [path for path in paths if len(path) >= 2]


def _path_length(path: Sequence[Point]) -> float:
    return _polyline_length(path)


def _point_to_path_distance(point: Point, path: Sequence[Point]) -> float:
    if len(path) < 2:
        return math.inf
    return min(
        _segment_distance(point, start, end)[0]
        for start, end in zip(path, path[1:])
    )


def _paths_match(left: Sequence[Point], right: Sequence[Point], tolerance: float) -> bool:
    if len(left) < 2 or len(right) < 2:
        return False
    if abs(_path_length(left) - _path_length(right)) > max(tolerance * 8, 2.0):
        sampled_left = list(left[:: max(1, len(left) // 12)] ) + [left[-1]]
        sampled_right = list(right[:: max(1, len(right) // 12)] ) + [right[-1]]
    else:
        sampled_left = left
        sampled_right = right
    if any(_point_to_path_distance(point, right) > tolerance for point in sampled_left):
        return False
    if any(_point_to_path_distance(point, left) > tolerance for point in sampled_right):
        return False
    return True


def _sample_region(polygon: Sequence[Point], step_mm: float) -> list[Point]:
    if len(polygon) < 3:
        return []
    min_x, min_y, max_x, max_y = bbox(polygon)
    step = max(step_mm, GEOMETRY_TOLERANCE_MM * 8)
    samples: list[Point] = []
    y = min_y + step / 2.0
    while y <= max_y + 1e-9:
        x = min_x + step / 2.0
        while x <= max_x + 1e-9:
            point = (x, y)
            if point_in_polygon(point, polygon, GEOMETRY_TOLERANCE_MM):
                samples.append(point)
            x += step
        y += step
    if not samples:
        samples.append(
            (
                (min_x + max_x) / 2.0,
                (min_y + max_y) / 2.0,
            )
        )
    return samples


def compare_liner_set_paths(
    paths: Sequence[Sequence[Point]],
    piece: LinerPiece,
    specs: Sequence[Any],
    width_cm: float,
    cutter_diameter_mm: float | None = None,
    *,
    start_sawn: Sequence[bool | None] | None = None,
    end_sawn: Sequence[bool | None] | None = None,
) -> LinerMeasurement:
    """Judge imported Liner entities against the ordered mill union, not entity count."""

    items = tuple(specs or ())
    imported = [tuple(path) for path in paths if path and len(path) >= 2]
    if not items:
        if imported:
            return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "shape", "", "", "extra_path")
        return LinerMeasurement(True)
    if len(items) == 1 and len(imported) == 1:
        side, offset_cm, start_cm, length_cm = _liner_spec_tuple(items[0])
        return compare_liner_path(
            imported[0],
            piece,
            side,
            offset_cm,
            width_cm,
            cutter_diameter_mm,
            start_cm,
            length_cm,
            start_sawn=None if not start_sawn else start_sawn[0],
            end_sawn=None if not end_sawn else end_sawn[0],
        )
    if not imported:
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "shape", "", "", "empty_path")
    if not _positive_diameter(cutter_diameter_mm):
        return LinerMeasurement(
            False,
            LINER_WIDTH_NOT_MEASURABLE,
            "width",
            _fmt_cm(_mm(width_cm)),
            "",
            "width_not_measurable",
        )
    diameter = float(cutter_diameter_mm or 0)
    radius = diameter / 2.0
    try:
        expected = merged_liner_toolpaths_mm(
            piece,
            items,
            width_cm,
            diameter,
            start_sawn=start_sawn,
            end_sawn=end_sawn,
        )
        regions = [
            liner_region_polygon_mm(piece, *_liner_spec_tuple(spec)[:2], width_cm, *_liner_spec_tuple(spec)[2:])
            for spec in items
        ]
    except LinerGeometryError as error:
        code = LINER_WIDTH_MISMATCH if error.code == "liner_narrower_than_cutter" else LINER_SHAPE_MISMATCH
        return LinerMeasurement(False, code, "shape", "", "", error.code)

    unused = list(range(len(imported)))
    matched = 0
    for expected_path in expected:
        found = None
        for index in unused:
            if _paths_match(imported[index], expected_path, max(GEOMETRY_TOLERANCE_MM * 4, radius * 0.35)):
                found = index
                break
        if found is None:
            continue
        unused.remove(found)
        matched += 1
    if matched == len(expected) and not unused:
        return LinerMeasurement(True)

    cover_tolerance = radius + GEOMETRY_TOLERANCE_MM
    for region in regions:
        for sample in _sample_region(region, max(radius, 2.0)):
            if min(_point_to_path_distance(sample, path) for path in imported) > cover_tolerance:
                return LinerMeasurement(
                    False,
                    LINER_SHAPE_MISMATCH,
                    "shape",
                    "",
                    "",
                    "missing_region",
                )
    inflate = radius + GEOMETRY_TOLERANCE_MM * 4
    for path in imported:
        for point in path:
            in_region = any(
                point_in_polygon(point, region, inflate) for region in regions
            )
            near_region = min(point_to_polygon_distance(point, region) for region in regions) <= inflate
            if in_region or near_region:
                continue
            return LinerMeasurement(
                False,
                LINER_SHAPE_MISMATCH,
                "shape",
                "",
                "",
                "extra_path",
            )
    if unused and matched == 0:
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "shape", "", "", "shape_mismatch")
    return LinerMeasurement(True)


__all__ = [
    "CM_TO_MM",
    "GEOMETRY_TOLERANCE_MM",
    "LINER_OFFSET_MISMATCH",
    "LINER_SHAPE_MISMATCH",
    "LINER_SIDE_MISMATCH",
    "LINER_WIDTH_MISMATCH",
    "LINER_WIDTH_NOT_MEASURABLE",
    "LinerGeometryError",
    "LinerMeasurement",
    "LinerPiece",
    "RecessedHandleCenter",
    "OUTER_SIDES",
    "SIDE_BREAK",
    "SIDE_BREAK_ONLY",
    "SIDE_BOTTOM",
    "SIDE_LEFT",
    "SIDE_RIGHT",
    "SIDE_TOP",
    "available_liner_sides",
    "canonical_path",
    "center_recessed_handle",
    "compare_liner_path",
    "compare_liner_set_paths",
    "contour_notch_cm",
    "liner_activation_error",
    "inverse_transform_point",
    "liner_parameters_active",
    "cutter_center_offsets_mm",
    "extension_conflict",
    "extension_conflict_details",
    "liner_toolpath_mm",
    "liner_region_polygon_mm",
    "liner_strip_polygon_mm",
    "localize_path",
    "merged_liner_toolpaths_mm",
    "mill_regions_connected",
    "obstacle_polygon_mm",
    "obstacle_geometry_mm",
    "piece_polygon_mm",
    "piece_quarter_turns",
    "placed_polygon_mm",
    "placement_ring_mm",
    "reference_polyline_mm",
    "sawn_liner_ends",
    "transform_point",
    "validation_code",
]
