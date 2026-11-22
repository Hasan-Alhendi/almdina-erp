"""Exact manufacturing curves kept beside flattened analysis polygons.

Analysis polygons remain the input for nesting, area, and clearance. Cutter
offset, uploaded CUT_PATH checks, and DXF/NC export use these primitives when
they exist. A missing loop stays on the historical straight-segment path.
Splines and ellipses are offset by an adaptive chord of
``CURVE_CHORD_TOLERANCE_MM`` because their offset is not the same curve type.
That chord is tighter than the 0.05 mm path comparison tolerance.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon

Point = tuple[float, float]
Loop = dict[str, Any]
Mapper = Callable[[Point], Point]

CURVE_CHORD_TOLERANCE_MM = 0.02
PATH_MATCH_TOLERANCE_MM = 0.05
_MIN_RADIUS_MM = 1e-4

SAW_CURVE_ABSENT = "absent"
SAW_CURVE_MATCH = "match"
SAW_CURVE_INVALID = "invalid"


def _pt(value: Sequence[float]) -> Point:
    return (float(value[0]), float(value[1]))


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def line_segment(start: Sequence[float], end: Sequence[float]) -> dict[str, Any]:
    return {"kind": "line", "start": _pt(start), "end": _pt(end)}


def arc_segment(
    start: Sequence[float],
    end: Sequence[float],
    center: Sequence[float],
    radius: float,
    *,
    ccw: bool,
) -> dict[str, Any]:
    return {
        "kind": "arc",
        "start": _pt(start),
        "end": _pt(end),
        "center": _pt(center),
        "radius": float(radius),
        "ccw": bool(ccw),
    }


def circle_segment(center: Sequence[float], radius: float, *, ccw: bool = True) -> dict[str, Any]:
    center_point = _pt(center)
    start = (center_point[0] + float(radius), center_point[1])
    return {
        "kind": "circle",
        "start": start,
        "end": start,
        "center": center_point,
        "radius": float(radius),
        "ccw": bool(ccw),
    }


def arc_from_bulge(start: Sequence[float], end: Sequence[float], bulge: float) -> dict[str, Any]:
    """Convert an LWPOLYLINE bulge into a circular arc. Zero bulge is a line."""

    start_point = _pt(start)
    end_point = _pt(end)
    if abs(float(bulge)) <= 1e-12:
        return line_segment(start_point, end_point)
    chord_x = end_point[0] - start_point[0]
    chord_y = end_point[1] - start_point[1]
    chord = math.hypot(chord_x, chord_y)
    if chord <= 1e-12:
        return line_segment(start_point, end_point)
    included = 4.0 * math.atan(float(bulge))
    radius = abs(chord / (2.0 * math.sin(included / 2.0)))
    half = chord / 2.0
    height = math.sqrt(max(radius * radius - half * half, 0.0))
    unit_x = -chord_y / chord
    unit_y = chord_x / chord
    if float(bulge) < 0.0:
        unit_x, unit_y = -unit_x, -unit_y
    if abs(included) > math.pi:
        unit_x, unit_y = -unit_x, -unit_y
    center = (
        (start_point[0] + end_point[0]) / 2.0 + unit_x * height,
        (start_point[1] + end_point[1]) / 2.0 + unit_y * height,
    )
    return arc_segment(start_point, end_point, center, radius, ccw=float(bulge) > 0.0)


def arc_bulge(segment: Mapping[str, Any]) -> float:
    """Bulge of one arc, or 0 for a straight segment."""

    if str(segment.get("kind") or "") != "arc":
        return 0.0
    center = _pt(segment["center"])
    start = _pt(segment["start"])
    end = _pt(segment["end"])
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = end_angle - start_angle
    if segment.get("ccw") and sweep <= 1e-12:
        sweep += math.tau
    if not segment.get("ccw") and sweep >= -1e-12:
        sweep -= math.tau
    return math.tan(sweep / 4.0)


def _sweep(segment: Mapping[str, Any]) -> float:
    center = _pt(segment["center"])
    start = _pt(segment["start"])
    end = _pt(segment["end"])
    if str(segment.get("kind")) == "circle":
        return math.tau if segment.get("ccw", True) else -math.tau
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = end_angle - start_angle
    if segment.get("ccw") and sweep <= 1e-12:
        sweep += math.tau
    if not segment.get("ccw") and sweep >= -1e-12:
        sweep -= math.tau
    return sweep


def _sample_arc(segment: Mapping[str, Any], tolerance: float) -> list[Point]:
    center = _pt(segment["center"])
    radius = abs(float(segment["radius"]))
    start = _pt(segment["start"])
    sweep = _sweep(segment)
    if radius <= _MIN_RADIUS_MM or abs(sweep) <= 1e-12:
        return [start, _pt(segment["end"])]
    step = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - min(tolerance, radius * 0.5) / radius)))
    count = max(1, int(math.ceil(abs(sweep) / max(step, 1e-6))))
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    points = []
    for index in range(count + 1):
        angle = start_angle + sweep * (index / count)
        points.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
    points[0] = start
    points[-1] = _pt(segment["end"])
    return points


def _ellipse_point(segment: Mapping[str, Any], parameter: float) -> Point:
    center = _pt(segment["center"])
    major = _pt(segment["major_axis"])
    length = math.hypot(major[0], major[1]) or 1.0
    ratio = float(segment.get("ratio") or 1.0)
    normal = (-major[1] / length, major[0] / length)
    minor = ratio * length
    return (
        center[0] + math.cos(parameter) * major[0] + math.sin(parameter) * normal[0] * minor,
        center[1] + math.cos(parameter) * major[1] + math.sin(parameter) * normal[1] * minor,
    )


def _adaptive_points(
    point_at: Callable[[float], Point],
    start_parameter: float,
    end_parameter: float,
    tolerance: float,
    depth: int = 0,
) -> list[Point]:
    start = point_at(start_parameter)
    end = point_at(end_parameter)
    mid_parameter = (start_parameter + end_parameter) / 2.0
    mid = point_at(mid_parameter)
    chord_mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    if depth < 16 and _dist(mid, chord_mid) > tolerance:
        left = _adaptive_points(point_at, start_parameter, mid_parameter, tolerance, depth + 1)
        right = _adaptive_points(point_at, mid_parameter, end_parameter, tolerance, depth + 1)
        return left[:-1] + right
    return [start, end]


def _de_boor(controls: Sequence[Point], knots: Sequence[float], degree: int, parameter: float) -> Point:
    count = len(controls)
    if count == 0:
        return (0.0, 0.0)
    if parameter <= knots[degree]:
        return controls[0]
    if parameter >= knots[-degree - 1]:
        return controls[-1]
    span = degree
    while span < count - 1 and not (knots[span] <= parameter < knots[span + 1]):
        span += 1
    working = [controls[index] for index in range(span - degree, span + 1)]
    for level in range(1, degree + 1):
        for index in range(degree, level - 1, -1):
            knot_index = span - degree + index
            denominator = knots[knot_index + degree - level + 1] - knots[knot_index]
            alpha = 0.0 if abs(denominator) <= 1e-15 else (parameter - knots[knot_index]) / denominator
            previous = working[index - 1]
            current = working[index]
            working[index] = (
                (1.0 - alpha) * previous[0] + alpha * current[0],
                (1.0 - alpha) * previous[1] + alpha * current[1],
            )
    return working[degree]


def _sample_general(segment: Mapping[str, Any], tolerance: float) -> list[Point]:
    kind = str(segment.get("kind") or "")
    if kind == "ellipse":
        start = float(segment.get("start_param") or 0.0)
        end = float(segment.get("end_param") or math.tau)
        if end <= start:
            end += math.tau
        return _adaptive_points(lambda parameter: _ellipse_point(segment, parameter), start, end, tolerance)
    if kind == "spline":
        controls = [_pt(point) for point in segment.get("control_points") or ()]
        knots = [float(value) for value in segment.get("knots") or ()]
        degree = int(segment.get("degree") or 3)
        if len(controls) < 2 or len(knots) < degree + 2:
            fit = [_pt(point) for point in segment.get("fit_points") or ()]
            return fit or controls
        start = knots[degree]
        end = knots[-degree - 1]
        return _adaptive_points(
            lambda parameter: _de_boor(controls, knots, degree, parameter),
            start,
            end,
            tolerance,
        )
    return [_pt(segment["start"]), _pt(segment["end"])]


def sample_segment(segment: Mapping[str, Any], tolerance: float = CURVE_CHORD_TOLERANCE_MM) -> list[Point]:
    kind = str(segment.get("kind") or "")
    if kind in {"arc", "circle"}:
        return _sample_arc(segment, tolerance)
    if kind in {"ellipse", "spline"}:
        return _sample_general(segment, tolerance)
    return [_pt(segment["start"]), _pt(segment["end"])]


def sample_loop(
    segments: Sequence[Mapping[str, Any]],
    *,
    closed: bool,
    tolerance: float = CURVE_CHORD_TOLERANCE_MM,
) -> list[Point]:
    points: list[Point] = []
    for segment in segments:
        sampled = sample_segment(segment, tolerance)
        if points and sampled and _dist(points[-1], sampled[0]) <= 1e-6:
            sampled = sampled[1:]
        points.extend(sampled)
    if closed and len(points) >= 2 and _dist(points[0], points[-1]) <= 1e-6:
        points.pop()
    return points


def _left_normal(start: Point, end: Point) -> Point:
    length = _dist(start, end) or 1.0
    return (-(end[1] - start[1]) / length, (end[0] - start[0]) / length)


def _offset_point(point: Point, normal: Point, sign: float, distance: float) -> Point:
    return (point[0] + sign * normal[0] * distance, point[1] + sign * normal[1] * distance)


def _radial(point: Point, center: Point, radius: float) -> Point:
    length = _dist(point, center) or 1.0
    return (
        center[0] + (point[0] - center[0]) / length * radius,
        center[1] + (point[1] - center[1]) / length * radius,
    )


def _offset_primitive(segment: Mapping[str, Any], distance: float, sign: float) -> dict[str, Any] | None:
    kind = str(segment.get("kind") or "")
    if kind == "line":
        start = _pt(segment["start"])
        end = _pt(segment["end"])
        normal = _left_normal(start, end)
        return line_segment(
            _offset_point(start, normal, sign, distance),
            _offset_point(end, normal, sign, distance),
        )
    if kind in {"arc", "circle"}:
        radius = float(segment["radius"])
        delta = -sign * distance if segment.get("ccw", True) else sign * distance
        new_radius = radius + delta
        if new_radius <= _MIN_RADIUS_MM:
            return None
        center = _pt(segment["center"])
        if kind == "circle":
            return circle_segment(center, new_radius, ccw=bool(segment.get("ccw", True)))
        return arc_segment(
            _radial(_pt(segment["start"]), center, new_radius),
            _radial(_pt(segment["end"]), center, new_radius),
            center,
            new_radius,
            ccw=bool(segment.get("ccw")),
        )
    points = sample_segment(segment, CURVE_CHORD_TOLERANCE_MM)
    expanded: list[dict[str, Any]] = []
    for start, end in zip(points, points[1:]):
        if _dist(start, end) <= 1e-8:
            continue
        moved = _offset_primitive(line_segment(start, end), distance, sign)
        if moved is not None:
            expanded.append(moved)
    return {"kind": "chain", "segments": expanded}


def _line_intersection(first: tuple[Point, Point], second: tuple[Point, Point]) -> Point | None:
    start, end = first
    other_start, other_end = second
    direction = (end[0] - start[0], end[1] - start[1])
    other = (other_end[0] - other_start[0], other_end[1] - other_start[1])
    denominator = direction[0] * other[1] - direction[1] * other[0]
    if abs(denominator) <= 1e-9:
        return None
    step = (
        (other_start[0] - start[0]) * other[1] - (other_start[1] - start[1]) * other[0]
    ) / denominator
    return (start[0] + direction[0] * step, start[1] + direction[1] * step)


def _circle_line_hits(center: Point, radius: float, start: Point, end: Point) -> list[Point]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    fx = start[0] - center[0]
    fy = start[1] - center[1]
    aa = dx * dx + dy * dy
    if aa <= 1e-18:
        return []
    bb = 2.0 * (fx * dx + fy * dy)
    cc = fx * fx + fy * fy - radius * radius
    discriminant = bb * bb - 4.0 * aa * cc
    if discriminant < 0.0:
        return []
    root = math.sqrt(discriminant)
    return [
        (start[0] + ((-bb + sign * root) / (2.0 * aa)) * dx, start[1] + ((-bb + sign * root) / (2.0 * aa)) * dy)
        for sign in (-1.0, 1.0)
    ]


def _circle_circle_hits(first: Point, first_radius: float, second: Point, second_radius: float) -> list[Point]:
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    separation = math.hypot(dx, dy)
    if separation <= 1e-12:
        return []
    reach = (first_radius * first_radius - second_radius * second_radius + separation * separation) / (
        2.0 * separation
    )
    height_sq = first_radius * first_radius - reach * reach
    if height_sq < -1e-8:
        return []
    height = math.sqrt(max(height_sq, 0.0))
    base = (first[0] + reach * dx / separation, first[1] + reach * dy / separation)
    offset = (height * -dy / separation, height * dx / separation)
    if height <= 1e-8:
        return [base]
    return [(base[0] + offset[0], base[1] + offset[1]), (base[0] - offset[0], base[1] - offset[1])]


def _supporting_line(segment: Mapping[str, Any]) -> tuple[Point, Point]:
    return (_pt(segment["start"]), _pt(segment["end"]))


def _join_point(previous: Mapping[str, Any], current: Mapping[str, Any]) -> Point:
    previous_end = _pt(previous["end"])
    current_start = _pt(current["start"])
    if _dist(previous_end, current_start) <= 1e-4:
        return previous_end
    hits: list[Point] = []
    previous_kind = str(previous.get("kind") or "")
    current_kind = str(current.get("kind") or "")
    if previous_kind == "line" and current_kind == "line":
        hit = _line_intersection(_supporting_line(previous), _supporting_line(current))
        if hit is not None:
            hits.append(hit)
    elif previous_kind == "line" and current_kind == "arc":
        hits.extend(
            _circle_line_hits(
                _pt(current["center"]),
                float(current["radius"]),
                *_supporting_line(previous),
            )
        )
    elif previous_kind == "arc" and current_kind == "line":
        hits.extend(
            _circle_line_hits(
                _pt(previous["center"]),
                float(previous["radius"]),
                *_supporting_line(current),
            )
        )
    elif previous_kind == "arc" and current_kind == "arc":
        hits.extend(
            _circle_circle_hits(
                _pt(previous["center"]),
                float(previous["radius"]),
                _pt(current["center"]),
                float(current["radius"]),
            )
        )
    if not hits:
        return previous_end
    return min(hits, key=lambda hit: _dist(hit, previous_end) + _dist(hit, current_start))


def _with_ends(segment: Mapping[str, Any], start: Point, end: Point) -> dict[str, Any]:
    updated = dict(segment)
    if str(segment.get("kind")) == "arc":
        center = _pt(segment["center"])
        radius = float(segment["radius"])
        updated["start"] = _radial(start, center, radius)
        updated["end"] = _radial(end, center, radius)
        return updated
    updated["start"] = start
    updated["end"] = end
    return updated


def _expand(segment: Mapping[str, Any], distance: float, sign: float) -> list[dict[str, Any]]:
    moved = _offset_primitive(segment, distance, sign)
    if moved is None:
        return []
    if moved.get("kind") == "chain":
        return list(moved["segments"])
    return [moved]


def _is_null_line(segment: Mapping[str, Any]) -> bool:
    """A repeated LWPOLYLINE vertex is a zero-length line, not geometry."""

    if str(segment.get("kind") or "") != "line":
        return False
    return _dist(_pt(segment["start"]), _pt(segment["end"])) <= 1e-6


def offset_loop(segments: Sequence[Mapping[str, Any]], distance: float, sign: float) -> list[dict[str, Any]]:
    """Offset a closed manufacturing loop. Arc centers stay fixed."""

    segments = [segment for segment in segments if not _is_null_line(segment)]
    if len(segments) == 1 and str(segments[0].get("kind")) == "circle":
        moved = _offset_primitive(segments[0], distance, sign)
        return [moved] if moved is not None else []
    expanded: list[dict[str, Any]] = []
    for segment in segments:
        expanded.extend(_expand(segment, distance, sign))
    if not expanded:
        return []
    joined: list[dict[str, Any]] = []
    count = len(expanded)
    for index, segment in enumerate(expanded):
        start = _join_point(expanded[(index - 1) % count], segment)
        end = _join_point(segment, expanded[(index + 1) % count])
        updated = _with_ends(segment, start, end)
        if _dist(_pt(updated["start"]), _pt(updated["end"])) <= 1e-5 and str(updated.get("kind")) == "line":
            continue
        joined.append(updated)
    return joined


def _map_point_value(value: Sequence[float], mapper: Mapper) -> Point:
    return mapper(_pt(value))


def map_segment(segment: Mapping[str, Any], mapper: Mapper, *, reflection: bool, scale: float) -> dict[str, Any]:
    kind = str(segment.get("kind") or "")
    updated = dict(segment)
    updated["start"] = _map_point_value(segment["start"], mapper)
    updated["end"] = _map_point_value(segment["end"], mapper)
    factor = abs(float(scale))
    if kind in {"arc", "circle"}:
        updated["center"] = _map_point_value(segment["center"], mapper)
        updated["radius"] = abs(float(segment["radius"])) * factor
        if reflection:
            updated["ccw"] = not bool(segment.get("ccw", True))
    elif kind == "ellipse":
        center = _pt(segment["center"])
        major_end = (center[0] + float(segment["major_axis"][0]), center[1] + float(segment["major_axis"][1]))
        mapped_center = mapper(center)
        mapped_major = mapper(major_end)
        updated["center"] = mapped_center
        updated["major_axis"] = (
            mapped_major[0] - mapped_center[0],
            mapped_major[1] - mapped_center[1],
        )
        if reflection:
            start = float(segment.get("start_param") or 0.0)
            end = float(segment.get("end_param") or math.tau)
            updated["start_param"] = -end
            updated["end_param"] = -start
    elif kind == "spline":
        updated["control_points"] = [
            list(mapper(_pt(point))) for point in segment.get("control_points") or ()
        ]
        updated["fit_points"] = [list(mapper(_pt(point))) for point in segment.get("fit_points") or ()]
    return updated


def map_loops(
    loops: Sequence[Mapping[str, Any]],
    mapper: Mapper,
    *,
    reflection: bool = False,
    scale: float = 1.0,
) -> list[Loop]:
    mapped: list[Loop] = []
    for loop in loops:
        mapped.append(
            {
                "role": loop.get("role") or "outer",
                "closed": bool(loop.get("closed", True)),
                "segments": [
                    map_segment(segment, mapper, reflection=reflection, scale=scale)
                    for segment in loop.get("segments") or ()
                ],
            }
        )
    return mapped


def translate_loops(loops: Sequence[Mapping[str, Any]], dx: float, dy: float) -> list[Loop]:
    return map_loops(loops, lambda point: (point[0] + dx, point[1] + dy))


def rotate_loops(
    loops: Sequence[Mapping[str, Any]],
    pivot: Sequence[float],
    angle_deg: float,
) -> list[Loop]:
    radians = math.radians(float(angle_deg))
    cosine = math.cos(radians)
    sine = math.sin(radians)
    origin = _pt(pivot)

    def mapper(point: Point) -> Point:
        dx = point[0] - origin[0]
        dy = point[1] - origin[1]
        return (origin[0] + dx * cosine - dy * sine, origin[1] + dx * sine + dy * cosine)

    return map_loops(loops, mapper)


def reflect_loops(
    loops: Sequence[Mapping[str, Any]],
    *,
    axis: str,
    center: float,
) -> list[Loop]:
    def mapper(point: Point) -> Point:
        if axis == "v":
            return (point[0], 2.0 * center - point[1])
        return (2.0 * center - point[0], point[1])

    return map_loops(loops, mapper, reflection=True)


def loops_have_curves(loops: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        str(segment.get("kind") or "") not in {"", "line"}
        for loop in loops
        for segment in loop.get("segments") or ()
    )


def _loop_segments(loop: Mapping[str, Any]) -> list[tuple[Point, Point]]:
    points = sample_loop(
        list(loop.get("segments") or ()),
        closed=bool(loop.get("closed", True)),
        tolerance=CURVE_CHORD_TOLERANCE_MM,
    )
    if len(points) < 2:
        return []
    pairs = list(zip(points, points[1:]))
    if loop.get("closed", True) and _dist(points[0], points[-1]) > 1e-6:
        pairs.append((points[-1], points[0]))
    return pairs


def _segment_points(segment: tuple[Point, Point], spacing: float) -> list[Point]:
    start, end = segment
    length = _dist(start, end)
    if length <= 1e-9:
        return [start]
    count = max(1, int(math.ceil(length / spacing)))
    return [
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(count + 1)
    ]


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-18:
        return _dist(point, start)
    ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq))
    return _dist(point, (start[0] + ratio * dx, start[1] + ratio * dy))


def _network_distance(point: Point, segments: Sequence[tuple[Point, Point]]) -> float:
    if not segments:
        return math.inf
    return min(_distance_to_segment(point, start, end) for start, end in segments)


def _network_length(segments: Sequence[tuple[Point, Point]]) -> float:
    return sum(_dist(start, end) for start, end in segments)


def classify_curve_centers(
    observed: Sequence[Mapping[str, Any]],
    expected: Sequence[Mapping[str, Any]],
    material: Sequence[tuple[Sequence[Point], Sequence[Sequence[Point]]]],
    *,
    tolerance: float = PATH_MATCH_TOLERANCE_MM,
) -> str:
    """Match cutter centers by geometry, ignoring vertex count and entity type."""

    if not observed or not any(loop.get("segments") for loop in observed):
        return SAW_CURVE_ABSENT
    if not expected:
        return SAW_CURVE_INVALID
    from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
        merge_collinear_segments,
    )

    observed_segments = merge_collinear_segments(
        [segment for loop in observed for segment in _loop_segments(loop)],
        tolerance=tolerance,
    )
    expected_segments = merge_collinear_segments(
        [segment for loop in expected for segment in _loop_segments(loop)],
        tolerance=tolerance,
    )
    if not observed_segments or not expected_segments:
        return SAW_CURVE_INVALID
    observed_length = _network_length(observed_segments)
    expected_length = _network_length(expected_segments)
    if abs(observed_length - expected_length) > max(tolerance, 0.002 * expected_length):
        return SAW_CURVE_INVALID
    for source, target in (
        (observed_segments, expected_segments),
        (expected_segments, observed_segments),
    ):
        for segment in source:
            for point in _segment_points(segment, 1.0):
                if _network_distance(point, target) > tolerance:
                    return SAW_CURVE_INVALID
    for loop in observed:
        for point in sample_loop(list(loop.get("segments") or ()), closed=bool(loop.get("closed", True))):
            if _point_in_material(point, material):
                return SAW_CURVE_INVALID
    return SAW_CURVE_MATCH


def _point_in_material(
    point: Point,
    material: Sequence[tuple[Sequence[Point], Sequence[Sequence[Point]]]],
) -> bool:
    for outer, holes in material:
        if not point_in_polygon(point, outer):
            continue
        if any(point_in_polygon(point, hole) for hole in holes):
            continue
        return True
    return False


def validate_manufacturing(value: Any) -> dict[str, Any] | None:
    """Return a canonical manufacturing payload, or None when the field is absent."""

    if value in (None, "", []):
        return None
    if not isinstance(value, Mapping):
        raise ValueError("manufacturing geometry must be an object.")
    loops_value = value.get("loops")
    if not isinstance(loops_value, Sequence) or isinstance(loops_value, (str, bytes)):
        raise ValueError("manufacturing.loops must be an array.")
    loops = []
    for loop in loops_value:
        if not isinstance(loop, Mapping):
            raise ValueError("manufacturing loop must be an object.")
        segments = []
        for segment in loop.get("segments") or ():
            if not isinstance(segment, Mapping) or "kind" not in segment:
                raise ValueError("manufacturing segment is incomplete.")
            kind = str(segment["kind"])
            if kind not in {"line", "arc", "circle", "spline", "ellipse"}:
                raise ValueError("manufacturing segment kind is unsupported.")
            cleaned = {"kind": kind, "start": list(_pt(segment["start"])), "end": list(_pt(segment["end"]))}
            if kind in {"arc", "circle"}:
                cleaned["center"] = list(_pt(segment["center"]))
                cleaned["radius"] = float(segment["radius"])
                cleaned["ccw"] = bool(segment.get("ccw", True))
            elif kind == "ellipse":
                cleaned["center"] = list(_pt(segment["center"]))
                cleaned["major_axis"] = list(_pt(segment["major_axis"]))
                cleaned["ratio"] = float(segment["ratio"])
                cleaned["start_param"] = float(segment.get("start_param") or 0.0)
                cleaned["end_param"] = float(segment.get("end_param") or math.tau)
            elif kind == "spline":
                cleaned["degree"] = int(segment.get("degree") or 3)
                cleaned["control_points"] = [list(_pt(point)) for point in segment.get("control_points") or ()]
                cleaned["knots"] = [float(item) for item in segment.get("knots") or ()]
                cleaned["fit_points"] = [list(_pt(point)) for point in segment.get("fit_points") or ()]
            segments.append(cleaned)
        if segments:
            loops.append(
                {
                    "role": str(loop.get("role") or "outer"),
                    "closed": bool(loop.get("closed", True)),
                    "segments": segments,
                }
            )
    if not loops:
        return None
    return {"schema_version": 1, "loops": loops}


def manufacturing_payload(loops: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    return validate_manufacturing({"schema_version": 1, "loops": list(loops)})


def place_door_loops_mm(
    loops: Sequence[Mapping[str, Any]],
    *,
    x_cm: float,
    y_cm: float,
    blank_w_cm: float,
    blank_h_cm: float,
    viewport_w_cm: float,
    viewport_h_cm: float,
    rotated: bool,
) -> list[Loop]:
    """Place door-local centimetre curves into usable-sheet millimetres."""

    scale_w = blank_h_cm if rotated else blank_w_cm
    scale_h = blank_w_cm if rotated else blank_h_cm
    if scale_w <= 0 or scale_h <= 0:
        return []
    factor_x = (viewport_w_cm / scale_w) * 10.0
    factor_y = (viewport_h_cm / scale_h) * 10.0

    def mapper(point: Point) -> Point:
        px, py = point
        if rotated:
            px, py = blank_h_cm - py, px
        return (x_cm * 10.0 + px * factor_x, y_cm * 10.0 + py * factor_y)

    scale = factor_x if abs(factor_x - factor_y) <= 1e-6 else (factor_x + factor_y) / 2.0
    return map_loops(loops, mapper, scale=scale)
