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

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    has_self_intersection,
    point_in_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    CutDimensionError,
    l_shaped_raw_cut,
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
        )
        if tool.ok:
            return tool
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


def liner_centerline_mm(
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
) -> list[Point]:
    """One open line through the middle of the liner strip.

    The distance from the reference edge is the ordered offset plus half the
    liner width. The line follows that edge, including an L bend or a clipped
    diagonal, and is not a cutter toolpath.
    """

    error = validation_code(piece, side, offset_cm, width_cm)
    if error:
        raise LinerGeometryError(error)
    polygon = piece_polygon_mm(piece)
    reference = reference_polyline_mm(piece, side)
    sign = _inward_sign(reference, polygon)
    distance = _mm(offset_cm) + (_mm(width_cm) / 2.0)
    return _offset_polyline(reference, distance, sign)


def liner_toolpath_mm(
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float,
) -> list[Point]:
    """One open zigzag of cutter centers for the existing liner strip."""

    error = validation_code(piece, side, offset_cm, width_cm)
    if error:
        raise LinerGeometryError(error)
    width_mm = _mm(width_cm)
    centers = cutter_center_offsets_mm(width_mm, float(cutter_diameter_mm))
    polygon = piece_polygon_mm(piece)
    reference = reference_polyline_mm(piece, side)
    sign = _inward_sign(reference, polygon)
    radius = float(cutter_diameter_mm) / 2.0
    lines = [
        _extend_centerline(
            _offset_polyline(reference, _mm(offset_cm) + center, sign),
            radius,
            polygon,
        )
        for center in centers
    ]
    path: list[Point] = []
    for index, line in enumerate(lines):
        sequence = line if index % 2 == 0 else list(reversed(line))
        if path and math.dist(path[-1], sequence[0]) <= 1e-6:
            sequence = sequence[1:]
        path.extend(sequence)
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
) -> list[Point]:
    points = list(polyline)
    if len(points) < 2:
        raise LinerGeometryError("liner_extension_unsafe")
    for index, other_index in ((0, 1), (-1, -2)):
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
        points[index] = (
            hit[0] + direction[0] * extension,
            hit[1] + direction[1] * extension,
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
    sign = _inward_sign(reference, polygon)
    samples: list[Point] = []
    for start, end in zip(reference, reference[1:]):
        length = math.dist(start, end)
        if length <= GEOMETRY_TOLERANCE_MM:
            continue
        steps = max(2, int(length // 40.0))
        for step in range(1, steps):
            ratio = step / steps
            anchor = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            normal = _left_normal(start, end)
            samples.append((
                anchor[0] + sign * normal[0] * distance,
                anchor[1] + sign * normal[1] * distance,
            ))
    return samples


def _measure_toolpath(
    path: Sequence[Point],
    piece: LinerPiece,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float,
) -> LinerMeasurement:
    try:
        expected = liner_toolpath_mm(piece, side, offset_cm, width_cm, cutter_diameter_mm)
        centers = cutter_center_offsets_mm(_mm(width_cm), cutter_diameter_mm)
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
    reference = reference_polyline_mm(piece, side)
    offset_mm = _mm(offset_cm)
    width_mm = _mm(width_cm)
    inside = []
    for station in (0.2, 0.5, 0.8):
        inside.extend(_sample_width(reference, polygon, offset_mm + (width_mm * station)))
    outside_gap = max(1.0, GEOMETRY_TOLERANCE_MM * 4)
    outside = _sample_width(reference, polygon, offset_mm - outside_gap)
    outside.extend(_sample_width(reference, polygon, offset_mm + width_mm + outside_gap))
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
    "contour_notch_cm",
    "liner_activation_error",
    "inverse_transform_point",
    "liner_parameters_active",
    "cutter_center_offsets_mm",
    "liner_toolpath_mm",
    "liner_strip_polygon_mm",
    "localize_path",
    "piece_polygon_mm",
    "reference_polyline_mm",
    "transform_point",
    "validation_code",
]
