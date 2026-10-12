"""Parametric liner strip on a door, shared by preview, plans, and DXF checks.

Coordinates are the usable-sheet frame: origin at the piece's top-left, x to
the right, y downward, millimetres. That is the same frame as corner contours.
A liner is one offset band along a single strap-system edge. A path whose
vertices have no measurable thickness is rejected; lineweight is not invented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
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
    if kind == "Regular":
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


def _offset_polyline(polyline: Sequence[Point], distance: float, sign: float) -> list[Point]:
    segments = [
        _offset_segment(start, end, distance, sign)
        for start, end in zip(polyline, polyline[1:])
    ]
    points = [segments[0][0]]
    for index, segment in enumerate(segments):
        if index and math.dist(points[-1], segment[0]) > 1e-6:
            points.append(segment[0])
        points.append(segment[1])
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
    for point in _offset_polyline(reference, _mm(offset) + _mm(width), sign):
        if not point_in_polygon(point, polygon, tolerance=GEOMETRY_TOLERANCE_MM):
            return "strip_outside"
    for point in _offset_polyline(reference, _mm(offset), sign):
        if not point_in_polygon(point, polygon, tolerance=GEOMETRY_TOLERANCE_MM):
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


def _coverage(path: Sequence[Point], reference: Sequence[Point]) -> tuple[float, float, float]:
    segments = list(zip(reference, reference[1:]))
    lengths = [math.dist(start, end) for start, end in segments]
    total = sum(lengths)
    if total <= 0:
        return 0.0, 0.0, 0.0
    projections: list[float] = []
    for point in path:
        best_distance = None
        best_along = 0.0
        cursor = 0.0
        for (start, end), length in zip(segments, lengths):
            distance, ratio = _segment_distance(point, start, end)
            along = cursor + ratio * length
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_along = along
            cursor += length
        projections.append(best_along)
    return min(projections), max(projections), total


def _fmt_cm(value_mm: float) -> str:
    return f"{value_mm / CM_TO_MM:.3f}"


def _straight_run_points(
    path: Sequence[Point],
    reference: Sequence[Point],
    radius: float,
) -> list[Point]:
    """Drop vertices next to an interior corner so a bevel does not change the band thickness."""

    corners = list(reference[1:-1])
    if not corners:
        return list(path)
    kept = [
        point
        for point in path
        if all(math.dist(point, corner) > radius for corner in corners)
    ]
    return kept or list(path)


def _measure_against_side(
    path: Sequence[Point],
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
) -> LinerMeasurement:
    reference = reference_polyline_mm(piece, side)
    body = _straight_run_points(
        path,
        reference,
        _mm(offset_cm) + _mm(width_cm) + GEOMETRY_TOLERANCE_MM,
    )
    distances = _distances(body, reference)
    if not distances:
        return LinerMeasurement(False, LINER_SHAPE_MISMATCH, "shape", "", "", "empty_path")
    measured_offset = min(distances)
    measured_width = max(distances) - measured_offset
    if measured_width <= GEOMETRY_TOLERANCE_MM:
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
    start, end, total = _coverage(path, reference)
    covers = start <= GEOMETRY_TOLERANCE_MM and end >= total - GEOMETRY_TOLERANCE_MM
    offset_ok = abs(measured_offset - expected_offset) <= GEOMETRY_TOLERANCE_MM
    width_ok = abs(measured_width - expected_width) <= GEOMETRY_TOLERANCE_MM
    if offset_ok and width_ok and covers:
        return LinerMeasurement(True, matched_side=side)
    if not offset_ok:
        return LinerMeasurement(
            False,
            LINER_OFFSET_MISMATCH,
            "offset",
            _fmt_cm(expected_offset),
            _fmt_cm(measured_offset),
            "offset_mismatch",
            side,
        )
    if not width_ok:
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
) -> LinerMeasurement:
    """Compare a canonical-frame path with the ordered liner band."""

    selected = _measure_against_side(path, piece, side, offset_cm, width_cm)
    if selected.ok:
        return selected
    if selected.code == LINER_WIDTH_NOT_MEASURABLE:
        return selected
    for candidate in available_liner_sides(piece.piece_type):
        if candidate == side:
            continue
        other = _measure_against_side(path, piece, candidate, offset_cm, width_cm)
        if other.ok:
            return LinerMeasurement(
                False,
                LINER_SIDE_MISMATCH,
                "side",
                side,
                candidate,
                "side_mismatch",
                candidate,
            )
    return selected


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
    "OUTER_SIDES",
    "SIDE_BREAK",
    "SIDE_BREAK_ONLY",
    "SIDE_BOTTOM",
    "SIDE_LEFT",
    "SIDE_RIGHT",
    "SIDE_TOP",
    "available_liner_sides",
    "canonical_path",
    "compare_liner_path",
    "inverse_transform_point",
    "liner_parameters_active",
    "liner_strip_polygon_mm",
    "localize_path",
    "piece_polygon_mm",
    "reference_polyline_mm",
    "transform_point",
    "validation_code",
]
