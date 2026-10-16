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
from typing import Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon

Point = tuple[float, float]
Segment = tuple[Point, Point]
Shape = tuple[Sequence[Point], Sequence[Sequence[Point]]]

COLLINEAR_TOLERANCE_MM = 0.05


def cutter_center_segments(
    shapes: Sequence[Shape],
    radius_mm: float,
    *,
    tolerance: float = COLLINEAR_TOLERANCE_MM,
    board: Sequence[float] | None = None,
) -> list[Segment]:
    """Return unique saw-center segments for every outer ring and hole.

    ``board`` is ``(min_x, min_y, max_x, max_y)`` in the same coordinates as
    the rings. A finished edge lying on that physical boundary is not a cut.
    Trim, a shared kerf, and every edge that leaves the board are still
    emitted. Omitting ``board`` keeps every edge.
    """

    radius = max(0.0, float(radius_mm or 0.0))
    prepared = [(_open_ring(outer), [_open_ring(hole) for hole in holes]) for outer, holes in shapes]
    prepared = [(outer, holes) for outer, holes in prepared if len(outer) >= 3]
    if not prepared:
        return []
    segments: list[Segment] = []
    for outer, holes in prepared:
        rings = [outer, *[hole for hole in holes if len(hole) >= 3]]
        for ring in rings:
            if radius <= tolerance:
                offset = ring
            else:
                sign = _waste_sign(ring, prepared, radius)
                offset = _offset_closed(ring, radius, sign)
            if len(offset) < 3:
                continue
            count = len(ring)
            for index, finished_start in enumerate(ring):
                finished_end = ring[(index + 1) % count]
                if board is not None and _edge_on_board(
                    finished_start, finished_end, board, tolerance
                ):
                    continue
                start = offset[index]
                end = offset[(index + 1) % len(offset)]
                if math.dist(start, end) > tolerance:
                    segments.append((start, end))
    return _merge_collinear(segments, tolerance)


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


__all__ = ["COLLINEAR_TOLERANCE_MM", "cutter_center_segments"]
