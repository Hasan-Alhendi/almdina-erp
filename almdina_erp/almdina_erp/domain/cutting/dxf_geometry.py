from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Iterable, Sequence

Point = tuple[float, float]
Segment = tuple[Point, Point]

EPSILON = 1e-9


def points_close(a: Point, b: Point, tolerance: float) -> bool:
    return math.dist(a, b) <= tolerance


def segment_length(segment: Segment) -> float:
    return math.dist(segment[0], segment[1])


def bbox(points: Sequence[Point]) -> tuple[float, float, float, float]:
    if not points:
        raise ValueError("points cannot be empty")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _node_key(point: Point, tolerance: float) -> tuple[int, int]:
    scale = max(tolerance, EPSILON)
    return (int(round(point[0] / scale)), int(round(point[1] / scale)))


def assemble_contours(
    segments: Iterable[Segment],
    tolerance: float,
) -> list[dict[str, object]]:
    """Assemble unordered segments into connected contours.

    The result deliberately reports open/branched components instead of silently
    repairing them, so the application layer can show a precise validation error.
    """
    usable = [segment for segment in segments if segment_length(segment) > EPSILON]
    if not usable:
        return []

    edge_nodes: list[tuple[tuple[int, int], tuple[int, int]]] = []
    adjacency: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (start, end) in enumerate(usable):
        start_key = _node_key(start, tolerance)
        end_key = _node_key(end, tolerance)
        edge_nodes.append((start_key, end_key))
        adjacency[start_key].append(index)
        adjacency[end_key].append(index)

    unvisited = set(range(len(usable)))
    contours: list[dict[str, object]] = []
    while unvisited:
        seed = next(iter(unvisited))
        component: set[int] = set()
        queue = deque([seed])
        while queue:
            edge_index = queue.popleft()
            if edge_index not in unvisited:
                continue
            unvisited.remove(edge_index)
            component.add(edge_index)
            for node in edge_nodes[edge_index]:
                for linked in adjacency[node]:
                    if linked in unvisited:
                        queue.append(linked)

        degrees: dict[tuple[int, int], int] = defaultdict(int)
        for edge_index in component:
            start_key, end_key = edge_nodes[edge_index]
            degrees[start_key] += 1
            degrees[end_key] += 1
        branched = any(degree > 2 for degree in degrees.values())
        closed = bool(degrees) and not branched and all(degree == 2 for degree in degrees.values())

        start_node = next((node for node, degree in degrees.items() if degree == 1), next(iter(degrees)))
        ordered_points: list[Point] = []
        remaining = set(component)
        current_node = start_node
        while remaining:
            candidates = [idx for idx in adjacency[current_node] if idx in remaining]
            if not candidates:
                break
            edge_index = candidates[0]
            remaining.remove(edge_index)
            start_key, end_key = edge_nodes[edge_index]
            start, end = usable[edge_index]
            if start_key == current_node:
                first, second, next_node = start, end, end_key
            else:
                first, second, next_node = end, start, start_key
            if not ordered_points:
                ordered_points.append(first)
            elif not points_close(ordered_points[-1], first, tolerance):
                ordered_points.append(first)
            ordered_points.append(second)
            current_node = next_node

        if closed and ordered_points and points_close(ordered_points[0], ordered_points[-1], tolerance):
            ordered_points[-1] = ordered_points[0]
        contours.append(
            {
                "points": ordered_points,
                "segments": [usable[index] for index in component],
                "closed": closed,
                "branched": branched,
            }
        )
    return contours


def simplify_polygon(points: Sequence[Point], tolerance: float) -> list[Point]:
    if not points:
        return []
    clean: list[Point] = []
    for point in points:
        if not clean or not points_close(clean[-1], point, tolerance):
            clean.append(point)
    if len(clean) > 1 and points_close(clean[0], clean[-1], tolerance):
        clean.pop()
    if len(clean) < 3:
        return clean

    changed = True
    while changed and len(clean) >= 3:
        changed = False
        result: list[Point] = []
        count = len(clean)
        for i, current in enumerate(clean):
            prev = clean[(i - 1) % count]
            nxt = clean[(i + 1) % count]
            cross = (current[0] - prev[0]) * (nxt[1] - current[1]) - (current[1] - prev[1]) * (nxt[0] - current[0])
            scale = max(math.dist(prev, current), math.dist(current, nxt), 1.0)
            if abs(cross) <= tolerance * scale:
                changed = True
                continue
            result.append(current)
        if len(result) == len(clean):
            break
        clean = result
    return clean


def polygon_area(points: Sequence[Point]) -> float:
    polygon = list(points)
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon.pop()
    if len(polygon) < 3:
        return 0.0
    return abs(sum(
        polygon[i][0] * polygon[(i + 1) % len(polygon)][1]
        - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
        for i in range(len(polygon))
    )) / 2.0


def _orientation(a: Point, b: Point, c: Point, tolerance: float) -> int:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) <= tolerance:
        return 0
    return 1 if value > 0 else -1


def _point_on_segment(point: Point, start: Point, end: Point, tolerance: float) -> bool:
    if _orientation(start, end, point, tolerance) != 0:
        return False
    return (
        min(start[0], end[0]) - tolerance <= point[0] <= max(start[0], end[0]) + tolerance
        and min(start[1], end[1]) - tolerance <= point[1] <= max(start[1], end[1]) + tolerance
    )


def segments_intersect(a: Segment, b: Segment, tolerance: float = EPSILON) -> bool:
    a1, a2 = a
    b1, b2 = b
    o1 = _orientation(a1, a2, b1, tolerance)
    o2 = _orientation(a1, a2, b2, tolerance)
    o3 = _orientation(b1, b2, a1, tolerance)
    o4 = _orientation(b1, b2, a2, tolerance)
    if o1 != o2 and o3 != o4:
        return True
    return any((
        o1 == 0 and _point_on_segment(b1, a1, a2, tolerance),
        o2 == 0 and _point_on_segment(b2, a1, a2, tolerance),
        o3 == 0 and _point_on_segment(a1, b1, b2, tolerance),
        o4 == 0 and _point_on_segment(a2, b1, b2, tolerance),
    ))


def polygon_segments(points: Sequence[Point]) -> list[Segment]:
    polygon = list(points)
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon.pop()
    if len(polygon) < 2:
        return []
    return [(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))]


def has_self_intersection(points: Sequence[Point], tolerance: float = EPSILON) -> bool:
    segments = polygon_segments(points)
    count = len(segments)
    for i, first in enumerate(segments):
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            if segments_intersect(first, segments[j], tolerance):
                return True
    return False


def point_in_polygon(point: Point, polygon: Sequence[Point], tolerance: float = EPSILON) -> bool:
    segments = polygon_segments(polygon)
    if any(_point_on_segment(point, start, end, tolerance) for start, end in segments):
        return True
    x, y = point
    inside = False
    for start, end in segments:
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) == (y2 > y):
            continue
        crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        if crossing_x > x:
            inside = not inside
    return inside


def polygons_overlap(a: Sequence[Point], b: Sequence[Point], tolerance: float = EPSILON) -> bool:
    # Proper interior crossings are overlap. Pure boundary touching is handled by kerf validation.
    for first in polygon_segments(a):
        for second in polygon_segments(b):
            if not segments_intersect(first, second, tolerance):
                continue
            shared_endpoint = any(points_close(p, q, tolerance) for p in first for q in second)
            if not shared_endpoint:
                return True
    a_poly = simplify_polygon(a, tolerance)
    b_poly = simplify_polygon(b, tolerance)
    # Containment can be missed when the first vertex happens to lie on the other
    # contour boundary. Check every vertex and require strict interior placement.
    b_segments = polygon_segments(b_poly)
    for point in a_poly:
        if point_in_polygon(point, b_poly, tolerance) and not any(
            _point_on_segment(point, start, end, tolerance) for start, end in b_segments
        ):
            return True
    a_segments = polygon_segments(a_poly)
    for point in b_poly:
        if point_in_polygon(point, a_poly, tolerance) and not any(
            _point_on_segment(point, start, end, tolerance) for start, end in a_segments
        ):
            return True
    return False


def _point_segment_distance(point: Point, segment: Segment) -> float:
    start, end = segment
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    denom = dx * dx + dy * dy
    if denom <= EPSILON:
        return math.dist(point, start)
    t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denom))
    projection = (start[0] + t * dx, start[1] + t * dy)
    return math.dist(point, projection)


def segment_distance(a: Segment, b: Segment, tolerance: float = EPSILON) -> float:
    if segments_intersect(a, b, tolerance):
        return 0.0
    return min(
        _point_segment_distance(a[0], b),
        _point_segment_distance(a[1], b),
        _point_segment_distance(b[0], a),
        _point_segment_distance(b[1], a),
    )


def polygon_distance(a: Sequence[Point], b: Sequence[Point], tolerance: float = EPSILON) -> float:
    first_segments = polygon_segments(a)
    second_segments = polygon_segments(b)
    if not first_segments or not second_segments:
        return math.inf
    return min(segment_distance(first, second, tolerance) for first in first_segments for second in second_segments)


def polygon_inside_rect(
    points: Sequence[Point],
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    tolerance: float,
) -> bool:
    return all(
        min_x - tolerance <= x <= max_x + tolerance
        and min_y - tolerance <= y <= max_y + tolerance
        for x, y in points
    )


def is_axis_aligned_rectangle(points: Sequence[Point], tolerance: float) -> bool:
    polygon = simplify_polygon(points, tolerance)
    if len(polygon) != 4 or polygon_area(polygon) <= tolerance * tolerance:
        return False
    min_x, min_y, max_x, max_y = bbox(polygon)
    expected = {(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)}
    for point in polygon:
        if not any(points_close(point, corner, tolerance) for corner in expected):
            return False
    for start, end in polygon_segments(polygon):
        if abs(start[0] - end[0]) > tolerance and abs(start[1] - end[1]) > tolerance:
            return False
    return True


def validate_polygon(points: Sequence[Point], tolerance: float) -> list[str]:
    polygon = simplify_polygon(points, tolerance)
    errors: list[str] = []
    if len(polygon) < 3:
        errors.append("too_few_vertices")
        return errors
    if polygon_area(polygon) <= tolerance * tolerance:
        errors.append("zero_area")
    if has_self_intersection(polygon, tolerance=max(tolerance * 0.01, EPSILON)):
        errors.append("self_intersection")
    return errors
