"""Saw-center paths offset from finished door contours.

The finished ring stays the manufactured boundary. The saw is a disk of
diameter ``kerf`` and radius ``R``. Its center runs ``R`` into the waste:
outside an outer edge, into a hole, and once down the middle of a shared gap
of width ``2R``. Collinear centers that overlap or touch are one segment.
A gap larger than the collinear tolerance stays a gap, so a partial
coincidence cannot delete the rest of a cut and two paths are not joined
across door material.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon

Point = tuple[float, float]
Segment = tuple[Point, Point]
Shape = tuple[Sequence[Point], Sequence[Sequence[Point]]]

COLLINEAR_TOLERANCE_MM = 0.05


@dataclass(frozen=True, slots=True)
class CutterCenterPath:
    """One exported toolpath; closed paths preserve per-ring DXF identity."""

    points: tuple[Point, ...]
    closed: bool


def cutter_center_paths(
    shapes: Sequence[Shape],
    radius_mm: float,
    *,
    tolerance: float = COLLINEAR_TOLERANCE_MM,
    board: Sequence[float] | None = None,
) -> list[CutterCenterPath]:
    """Return independent closed offsets, with a safe board-edge fallback.

    A ring wholly inside the physical board is exported as one closed path,
    matching AutoCAD Multi Offset. A ring that uses a physical board edge
    keeps the established contract that this raw edge is not cut; its remaining
    centers are emitted as open, deduplicated segments instead.
    """

    radius = max(0.0, float(radius_mm or 0.0))
    prepared = _prepare_shapes(shapes)
    if not prepared:
        return []

    closed_paths: list[CutterCenterPath] = []
    open_segments: list[Segment] = []
    for outer, holes in prepared:
        for ring in [outer, *[hole for hole in holes if len(hole) >= 3]]:
            offset = (
                ring
                if radius <= tolerance
                else _offset_closed(ring, radius, _waste_sign(ring, prepared, radius))
            )
            if len(offset) < 3:
                continue
            board_edges = {
                index
                for index, start in enumerate(ring)
                if board is not None
                and _edge_on_board(
                    start,
                    ring[(index + 1) % len(ring)],
                    board,
                    tolerance,
                )
            }
            if not board_edges:
                closed_paths.append(CutterCenterPath(tuple(offset), True))
                continue
            for index, start in enumerate(offset):
                if index in board_edges:
                    continue
                end = offset[(index + 1) % len(offset)]
                if math.dist(start, end) > tolerance:
                    open_segments.append((start, end))

    open_paths = [
        CutterCenterPath((start, end), False)
        for start, end in _merge_collinear(open_segments, tolerance)
    ]
    return [*closed_paths, *open_paths]


def cutter_center_segments(
    shapes: Sequence[Shape],
    radius_mm: float,
    *,
    tolerance: float = COLLINEAR_TOLERANCE_MM,
    board: Sequence[float] | None = None,
) -> list[Segment]:
    """Return the canonical segment-network view of the exported paths.

    This compatibility view is used by import validation and older callers.
    Coincident sides from independent Multi Offset contours collapse to one
    physical center line before comparison.
    """

    segments: list[Segment] = []
    for path in cutter_center_paths(
        shapes,
        radius_mm,
        tolerance=tolerance,
        board=board,
    ):
        segments.extend(zip(path.points, path.points[1:]))
        if path.closed and len(path.points) >= 3:
            segments.append((path.points[-1], path.points[0]))
    return _merge_collinear(segments, tolerance)


def _prepare_shapes(
    shapes: Sequence[Shape],
) -> list[tuple[list[Point], list[list[Point]]]]:
    prepared = [
        (_open_ring(outer), [_open_ring(hole) for hole in holes])
        for outer, holes in shapes
    ]
    return [(outer, holes) for outer, holes in prepared if len(outer) >= 3]


def _edge_on_board(
    start: Point,
    end: Point,
    board: Sequence[float],
    tolerance: float,
) -> bool:
    """True when both endpoints lie on the same side of the physical board."""

    min_x, min_y, max_x, max_y = (float(value) for value in board)
    sides = ((0, min_x), (0, max_x), (1, min_y), (1, max_y))
    return any(
        abs(start[axis] - value) <= tolerance and abs(end[axis] - value) <= tolerance
        for axis, value in sides
    )


def _open_ring(points: Sequence[Point]) -> list[Point]:
    ring = [(float(point[0]), float(point[1])) for point in points]
    if len(ring) >= 2 and math.dist(ring[0], ring[-1]) <= 1e-9:
        ring = ring[:-1]
    cleaned: list[Point] = []
    for point in ring:
        if not cleaned or math.dist(cleaned[-1], point) > 1e-6:
            cleaned.append(point)
    if len(cleaned) >= 2 and math.dist(cleaned[0], cleaned[-1]) <= 1e-6:
        cleaned.pop()
    return cleaned


def _left_normal(start: Point, end: Point) -> Point:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    return (-dy / length, dx / length)


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


def _offset_closed(ring: Sequence[Point], distance: float, sign: float) -> list[Point]:
    count = len(ring)
    shifted = [
        _offset_segment(ring[index], ring[(index + 1) % count], distance, sign)
        for index in range(count)
    ]
    points: list[Point] = []
    for index in range(count):
        joint = _intersect_offset_lines(shifted[(index - 1) % count], shifted[index])
        points.append(joint if joint is not None else shifted[index][0])
    return points


def _is_material(point: Point, shapes: Sequence[tuple[list[Point], list[list[Point]]]]) -> bool:
    for outer, holes in shapes:
        if not point_in_polygon(point, outer):
            continue
        if any(point_in_polygon(point, hole) for hole in holes):
            continue
        return True
    return False


def _longest_edge(ring: Sequence[Point]) -> tuple[Point, Point]:
    best = (ring[0], ring[1])
    best_length = -1.0
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        length = math.dist(start, end)
        if length > best_length:
            best = (start, end)
            best_length = length
    return best


def _waste_sign(
    ring: Sequence[Point],
    shapes: Sequence[tuple[list[Point], list[list[Point]]]],
    radius: float,
) -> float:
    """Positive sign moves along the left normal, toward the waste."""

    start, end = _longest_edge(ring)
    normal = _left_normal(start, end)
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    probe = min(1.0, radius * 0.5)
    left = (midpoint[0] + normal[0] * probe, midpoint[1] + normal[1] * probe)
    right = (midpoint[0] - normal[0] * probe, midpoint[1] - normal[1] * probe)
    left_material = _is_material(left, shapes)
    right_material = _is_material(right, shapes)
    if left_material and not right_material:
        return -1.0
    if right_material and not left_material:
        return 1.0
    if point_in_polygon(left, ring):
        return -1.0 if left_material else 1.0
    return 1.0 if right_material else -1.0


def _merge_collinear(segments: Sequence[Segment], tolerance: float) -> list[Segment]:
    unused = set(range(len(segments)))
    merged: list[Segment] = []
    while unused:
        seed_index = unused.pop()
        origin, end = segments[seed_index]
        dx = end[0] - origin[0]
        dy = end[1] - origin[1]
        length = math.hypot(dx, dy)
        if length <= tolerance:
            continue
        direction = (dx / length, dy / length)
        normal = (-direction[1], direction[0])
        cluster = [(origin, end)]
        for other_index in list(unused):
            start, finish = segments[other_index]
            if _line_distance(start, origin, normal) > tolerance or _line_distance(finish, origin, normal) > tolerance:
                continue
            other_dx = finish[0] - start[0]
            other_dy = finish[1] - start[1]
            other_length = math.hypot(other_dx, other_dy)
            if other_length <= tolerance:
                unused.remove(other_index)
                continue
            sine = abs(direction[0] * other_dy - direction[1] * other_dx) / other_length
            if sine > tolerance:
                continue
            cluster.append((start, finish))
            unused.remove(other_index)
        intervals = []
        for start, finish in cluster:
            start_t = (start[0] - origin[0]) * direction[0] + (start[1] - origin[1]) * direction[1]
            end_t = (finish[0] - origin[0]) * direction[0] + (finish[1] - origin[1]) * direction[1]
            intervals.append((min(start_t, end_t), max(start_t, end_t)))
        intervals.sort()
        spans: list[list[float]] = []
        for start_t, end_t in intervals:
            if not spans or start_t > spans[-1][1] + tolerance:
                spans.append([start_t, end_t])
            else:
                spans[-1][1] = max(spans[-1][1], end_t)
        for start_t, end_t in spans:
            if end_t - start_t <= tolerance:
                continue
            merged.append((
                (origin[0] + direction[0] * start_t, origin[1] + direction[1] * start_t),
                (origin[0] + direction[0] * end_t, origin[1] + direction[1] * end_t),
            ))
    return merged


def _line_distance(point: Point, origin: Point, normal: Point) -> float:
    return abs((point[0] - origin[0]) * normal[0] + (point[1] - origin[1]) * normal[1])


SAW_CENTER_ABSENT = "absent"
SAW_CENTER_MATCH = "match"
SAW_CENTER_INVALID = "invalid"


def _finite_segments(
    segments: Sequence[Segment],
    *,
    tolerance: float,
) -> list[Segment]:
    cleaned: list[Segment] = []
    for start, end in segments:
        try:
            a = (float(start[0]), float(start[1]))
            b = (float(end[0]), float(end[1]))
        except (TypeError, ValueError, IndexError):
            continue
        if not all(math.isfinite(value) for value in (*a, *b)):
            continue
        if math.dist(a, b) <= tolerance:
            continue
        cleaned.append((a, b))
    return cleaned


def _segment_cover_length(
    candidate: Segment,
    cover: Segment,
    *,
    tolerance: float,
) -> float:
    """Return how much of ``candidate`` lies on ``cover``; 0 when not collinear."""

    origin, end = cover
    dx = end[0] - origin[0]
    dy = end[1] - origin[1]
    length = math.hypot(dx, dy)
    if length <= tolerance:
        return 0.0
    direction = (dx / length, dy / length)
    normal = (-direction[1], direction[0])
    start, finish = candidate
    if (
        _line_distance(start, origin, normal) > tolerance
        or _line_distance(finish, origin, normal) > tolerance
    ):
        return 0.0
    other_dx = finish[0] - start[0]
    other_dy = finish[1] - start[1]
    other_length = math.hypot(other_dx, other_dy)
    if other_length <= tolerance:
        return 0.0
    sine = abs(direction[0] * other_dy - direction[1] * other_dx) / other_length
    if sine > tolerance:
        return 0.0
    start_t = (start[0] - origin[0]) * direction[0] + (start[1] - origin[1]) * direction[1]
    end_t = (finish[0] - origin[0]) * direction[0] + (finish[1] - origin[1]) * direction[1]
    low, high = (min(start_t, end_t), max(start_t, end_t))
    overlap = min(high, length) - max(low, 0.0)
    return max(0.0, overlap)


def saw_center_segments_match(
    observed: Sequence[Segment],
    expected: Sequence[Segment],
    *,
    tolerance: float = COLLINEAR_TOLERANCE_MM,
) -> bool:
    """True when observed saw centers cover the expected set without extras."""

    left = _merge_collinear(_finite_segments(observed, tolerance=tolerance), tolerance)
    right = _merge_collinear(_finite_segments(expected, tolerance=tolerance), tolerance)
    if len(left) != len(right):
        return False
    if not left:
        return True
    remaining = list(right)
    for candidate in left:
        candidate_length = math.dist(candidate[0], candidate[1])
        match_index = None
        for index, cover in enumerate(remaining):
            covered = _segment_cover_length(candidate, cover, tolerance=tolerance)
            reverse = _segment_cover_length(cover, candidate, tolerance=tolerance)
            cover_length = math.dist(cover[0], cover[1])
            if (
                abs(covered - candidate_length) <= tolerance
                and abs(reverse - cover_length) <= tolerance
            ):
                match_index = index
                break
        if match_index is None:
            return False
        remaining.pop(match_index)
    return not remaining


def classify_saw_center_segments(
    observed: Sequence[Segment],
    expected: Sequence[Segment],
    *,
    tolerance: float = COLLINEAR_TOLERANCE_MM,
) -> str:
    """Classify uploaded CUT_PATH centers against the finished-geometry engine.

    ``absent`` means the designer left manufacturing paths empty so approval may
    generate them. ``match`` keeps the designer paths. ``invalid`` rejects the
    file; partial paths are never repaired.
    """

    cleaned = _finite_segments(observed, tolerance=tolerance)
    if not cleaned:
        return SAW_CENTER_ABSENT
    if saw_center_segments_match(cleaned, expected, tolerance=tolerance):
        return SAW_CENTER_MATCH
    return SAW_CENTER_INVALID


__all__ = [
    "COLLINEAR_TOLERANCE_MM",
    "CutterCenterPath",
    "SAW_CENTER_ABSENT",
    "SAW_CENTER_INVALID",
    "SAW_CENTER_MATCH",
    "classify_saw_center_segments",
    "cutter_center_paths",
    "cutter_center_segments",
    "saw_center_segments_match",
]
