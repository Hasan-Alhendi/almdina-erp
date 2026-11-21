"""Compile one adopted drawing path into the existing special-shape polygon.

The result is the centimetre polygon already accepted by
``special_shape_geometry_json``. It contains no images, guide lines, notes,
or cutter offset. Kerf stays in the existing export path.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    ROLE_MANUFACTURING_HOLE,
    ROLE_MANUFACTURING_OUTER,
    SEGMENT_ARC,
    SEGMENT_BEZIER,
    SEGMENT_LINE,
    DrawingDocumentError,
    normalize_document,
)

MAX_VERTICES = 64
CHORD_ERROR_MM = 0.05
STORAGE_EPSILON_CM = 0.001
_MIN_SAMPLE_MM = 0.02
_MAX_BEZIER_DEPTH = 16
# 0.042 + 0.005*sqrt(2) rounding <= 0.05 for chords the 0.02 mm filter keeps.
# 0.022 + 0.02 collapse + the same rounding <= 0.05 for shorter chords.
_LONG_CHORD_TOLERANCE_MM = 0.042
_SHORT_CHORD_TOLERANCE_MM = 0.022


def compile_manufacturing_geometry(
    document: Mapping[str, Any],
    *,
    blank_width_mm: float,
    blank_length_mm: float,
) -> dict[str, Any]:
    """Return ``status`` absent, ready, or rejected.

    Absent means the drawing has no manufacturing role, so a plan copy keeps
    the geometry it already had. Rejected means an adopted path cannot be cut,
    and a plan copy must stop instead of falling back to the old outline.
    """

    try:
        normalized = normalize_document(document)
    except DrawingDocumentError as exc:
        return _rejected(exc.code, "path-1")
    width = float(blank_width_mm)
    length = float(blank_length_mm)
    if not math.isfinite(width) or not math.isfinite(length) or width <= 0 or length <= 0:
        return _rejected("blank_invalid", "")
    outers = [path for path in normalized["paths"] if path["role"] == ROLE_MANUFACTURING_OUTER]
    holes = [path for path in normalized["paths"] if path["role"] == ROLE_MANUFACTURING_HOLE]
    if holes:
        return _rejected("holes_unsupported", str(holes[0]["id"]))
    if not outers:
        return {"status": "absent", "code": "", "path_id": "", "geometry": None}
    if len(outers) > 1:
        return _rejected("multiple_outers", str(outers[1]["id"]))
    path = outers[0]
    if not path["closed"]:
        return _rejected("path_open", str(path["id"]))
    points = _flatten_path(path)
    if isinstance(points, dict):
        points["path_id"] = str(path["id"])
        return points
    checked = _polygon(points, width, length, str(path["id"]))
    if checked["status"] != "ready":
        return checked
    geometry = {
        "version": 1,
        "kind": "polygon",
        "units": "cm",
        "template": "drawing",
        "blank_width_cm": round(width / 10.0, 3),
        "blank_length_cm": round(length / 10.0, 3),
        "points": checked["points"],
        "exact": True,
    }
    # Full-span polygons stay on the historical contract. An interior contour
    # keeps its offset and reserves the whole blank instead of the contour box.
    if not checked["spans_blank"]:
        geometry["reservation"] = "blank"
    return {
        "status": "ready",
        "code": "",
        "path_id": str(path["id"]),
        "geometry": geometry,
        "fingerprint": manufacturing_fingerprint(geometry),
    }


def manufacturing_fingerprint(geometry: Mapping[str, Any]) -> str:
    payload = {
        "kind": geometry.get("kind"),
        "units": geometry.get("units"),
        "points": geometry.get("points"),
        "blank_width_cm": geometry.get("blank_width_cm"),
        "blank_length_cm": geometry.get("blank_length_cm"),
        "reservation": geometry.get("reservation") or "",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _rejected(code: str, path_id: str) -> dict[str, Any]:
    return {"status": "rejected", "code": code, "path_id": path_id, "geometry": None}


def _flatten_path(path: Mapping[str, Any]) -> list[tuple[float, float]] | dict[str, Any]:
    nodes = {str(node["id"]): node for node in path["nodes"]}
    samples: list[tuple[float, float]] = []
    for segment in path["segments"]:
        start = nodes[str(segment["from_node"])]
        end = nodes[str(segment["to_node"])]
        start_point = (float(start["x_mm"]), float(start["y_mm"]))
        end_point = (float(end["x_mm"]), float(end["y_mm"]))
        if segment["kind"] == SEGMENT_LINE:
            if _distance(start_point, end_point) < _MIN_SAMPLE_MM:
                return _rejected("zero_edge", str(path["id"]))
            piece = [start_point, end_point]
        elif segment["kind"] == SEGMENT_ARC:
            piece = _flatten_arc(start_point, end_point, segment)
        else:
            controls = segment["controls"]
            piece = _flatten_bezier(
                start_point,
                (float(controls[0]["x_mm"]), float(controls[0]["y_mm"])),
                (float(controls[1]["x_mm"]), float(controls[1]["y_mm"])),
                end_point,
            )
        if piece is None:
            return _rejected("curve_unrepresentable", str(path["id"]))
        if samples and _distance(samples[-1], piece[0]) <= _MIN_SAMPLE_MM:
            piece = piece[1:]
        samples.extend(piece)
    if len(samples) >= 2 and _distance(samples[0], samples[-1]) <= _MIN_SAMPLE_MM:
        samples.pop()
    return samples


def _flatten_arc(
    start: tuple[float, float],
    end: tuple[float, float],
    segment: Mapping[str, Any],
) -> list[tuple[float, float]] | None:
    radius = float(segment["radius_mm"])
    large = bool(segment["large_arc"])
    sweep = bool(segment["sweep_clockwise"])
    center = _arc_frame(start, end, radius, large, sweep)
    if center is None:
        return None
    cx, cy, theta, delta = center
    count = max(1, int(math.ceil(abs(delta) / max(_step(radius), 1e-6))))
    if count > MAX_VERTICES:
        return None
    fractions = {index / count for index in range(count + 1)}
    for angle in _axis_angles(theta, delta):
        fraction = (angle - theta) / delta if abs(delta) > 1e-12 else 0.0
        if 0.0 < fraction < 1.0:
            fractions.add(fraction)
    ordered = [theta + delta * fraction for fraction in sorted(fractions)]
    points = [(cx + radius * math.cos(angle), cy + radius * math.sin(angle)) for angle in ordered]
    points[0] = start
    points[-1] = end
    return points


def _arc_frame(start, end, radius, large, sweep):
    x1, y1 = start
    x2, y2 = end
    dx = (x1 - x2) / 2.0
    dy = (y1 - y2) / 2.0
    chord2 = dx * dx + dy * dy
    if chord2 <= 1e-12:
        return None
    radius2 = radius * radius
    if radius2 < chord2 - 1e-9:
        return None
    factor = math.sqrt(max(0.0, radius2 / chord2 - 1.0))
    sign = -1.0 if large == sweep else 1.0
    cx = (x1 + x2) / 2.0 + sign * factor * dy
    cy = (y1 + y2) / 2.0 + sign * factor * -dx
    theta = math.atan2(y1 - cy, x1 - cx)
    theta2 = math.atan2(y2 - cy, x2 - cx)
    delta = theta2 - theta
    if sweep and delta < 0:
        delta += math.tau
    if not sweep and delta > 0:
        delta -= math.tau
    return cx, cy, theta, delta


def _step(radius: float) -> float:
    ratio = max(-1.0, min(1.0, 1.0 - CHORD_ERROR_MM / max(radius, CHORD_ERROR_MM)))
    return 2.0 * math.acos(ratio)


def _axis_angles(theta: float, delta: float) -> list[float]:
    found = []
    end = theta + delta
    low, high = (theta, end) if delta >= 0 else (end, theta)
    turn = math.floor(low / (math.pi / 2.0))
    candidate = turn * (math.pi / 2.0)
    while candidate <= high + 1e-9:
        if candidate > low + 1e-9:
            found.append(candidate)
        candidate += math.pi / 2.0
    return found


def _flatten_bezier(p0, c1, c2, p1) -> list[tuple[float, float]] | None:
    """Adaptive De Casteljau subdivision. Endpoints stay exactly as drawn.

    Acceptance uses ``_chord_deviation_bound``, which is an upper bound on the
    distance from the cubic to its chord, not a midpoint sample. A long chord
    may stop at 0.042 mm because rounding adds at most 0.005*sqrt(2) mm. A
    chord shorter than the 0.02 mm sample filter must already be within 0.022 mm
    so dropping it still leaves the stored polygon inside 0.05 mm.
    """

    return _adaptive_bezier(p0, c1, c2, p1, 0, MAX_VERTICES)


def _adaptive_bezier(p0, c1, c2, p1, depth, budget):
    if not all(math.isfinite(value) for point in (p0, c1, c2, p1) for value in point):
        return None
    if _controls_within_chord(p0, c1, c2, p1):
        if budget < 2:
            return None
        return [p0, p1]
    if depth >= _MAX_BEZIER_DEPTH or budget <= 2:
        return None
    left, right = _split_bezier(p0, c1, c2, p1)
    left_points = _adaptive_bezier(*left, depth + 1, budget)
    if left_points is None:
        return None
    right_budget = budget - len(left_points) + 1
    right_points = _adaptive_bezier(*right, depth + 1, right_budget)
    if right_points is None:
        return None
    return left_points[:-1] + right_points


def _split_bezier(p0, c1, c2, p1):
    def mid(a, b):
        return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)

    a = mid(p0, c1)
    b = mid(c1, c2)
    c = mid(c2, p1)
    d = mid(a, b)
    e = mid(b, c)
    f = mid(d, e)
    return (p0, a, d, f), (f, e, c, p1)


def _controls_within_chord(p0, c1, c2, p1) -> bool:
    bound = _chord_deviation_bound(p0, c1, c2, p1)
    if bound <= _SHORT_CHORD_TOLERANCE_MM:
        return True
    return bound <= _LONG_CHORD_TOLERANCE_MM and _distance(p0, p1) >= _MIN_SAMPLE_MM


def _chord_deviation_bound(p0, c1, c2, p1) -> float:
    """Upper bound on the distance from the cubic to its chord segment.

    The Bernstein weights 3(1-t)^2 t and 3(1-t)t^2 each peak at 4/9. When both
    controls project onto the chord, the curve does too, and its distance is at
    most (4/9) times the sum of the control heights. Otherwise the convex-hull
    distance to the segment remains the bound.
    """

    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-18:
        return max(_distance(c1, p0), _distance(c2, p0))
    length = math.sqrt(length2)

    def along(point) -> float:
        return ((point[0] - p0[0]) * dx + (point[1] - p0[1]) * dy) / length

    def height(point) -> float:
        return abs((point[0] - p0[0]) * dy - (point[1] - p0[1]) * dx) / length

    span_1 = along(c1)
    span_2 = along(c2)
    if 0.0 <= span_1 <= length and 0.0 <= span_2 <= length:
        return (4.0 / 9.0) * (height(c1) + height(c2))
    return max(_distance_to_segment(c1, p0, p1), _distance_to_segment(c2, p0, p1))


def _distance_to_segment(point, start, end) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-18:
        return _distance(point, start)
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2
    if ratio <= 0.0:
        return _distance(point, start)
    if ratio >= 1.0:
        return _distance(point, end)
    return math.hypot(point[0] - (start[0] + ratio * dx), point[1] - (start[1] + ratio * dy))


def _polygon(points, width_mm, length_mm, path_id):
    kept: list[tuple[float, float]] = []
    for point in points:
        if not all(math.isfinite(value) for value in point):
            return _rejected("non_finite", path_id)
        if kept and _distance(kept[-1], point) < _MIN_SAMPLE_MM:
            continue
        kept.append(point)
    if len(kept) >= 2 and _distance(kept[0], kept[-1]) < _MIN_SAMPLE_MM:
        kept.pop()
    rounded = [(round(point[0] / 10.0, 3), round(point[1] / 10.0, 3)) for point in kept]
    compact: list[list[float]] = []
    for point in rounded:
        if compact and compact[-1] == [point[0], point[1]]:
            return _rejected("zero_edge", path_id)
        compact.append([point[0], point[1]])
    if len(compact) > MAX_VERTICES:
        return _rejected("curve_unrepresentable", path_id)
    if len(compact) < 3:
        return _rejected("invalid_area", path_id)
    width_cm = round(width_mm / 10.0, 3)
    length_cm = round(length_mm / 10.0, 3)
    if any(
        point[0] < -STORAGE_EPSILON_CM
        or point[1] < -STORAGE_EPSILON_CM
        or point[0] > width_cm + STORAGE_EPSILON_CM
        or point[1] > length_cm + STORAGE_EPSILON_CM
        for point in compact
    ):
        return _rejected("outside_blank", path_id)
    xs = [point[0] for point in compact]
    ys = [point[1] for point in compact]
    spans_blank = (
        abs(min(xs)) <= STORAGE_EPSILON_CM
        and abs(max(xs) - width_cm) <= STORAGE_EPSILON_CM
        and abs(min(ys)) <= STORAGE_EPSILON_CM
        and abs(max(ys) - length_cm) <= STORAGE_EPSILON_CM
    )
    if _edges_cross(compact) or _edges_overlap(compact):
        return _rejected("self_intersection", path_id)
    if abs(_area(compact)) <= STORAGE_EPSILON_CM:
        return _rejected("invalid_area", path_id)
    return {"status": "ready", "points": compact, "path_id": path_id, "spans_blank": spans_blank}


def _edges_cross(points: Sequence[Sequence[float]]) -> bool:
    count = len(points)
    for index in range(count):
        a, b = points[index], points[(index + 1) % count]
        for other in range(index + 1, count):
            if other == index or (other + 1) % count == index or other == (index + 1) % count:
                continue
            c, d = points[other], points[(other + 1) % count]
            if _proper_cross(a, b, c, d):
                return True
    return False


def _edges_overlap(points: Sequence[Sequence[float]]) -> bool:
    count = len(points)
    for index in range(count):
        a, b = points[index], points[(index + 1) % count]
        for other in range(index + 1, count):
            c, d = points[other], points[(other + 1) % count]
            if _collinear_overlap(a, b, c, d):
                return True
    return False


def _proper_cross(a, b, c, d) -> bool:
    return _turn(a, b, c) * _turn(a, b, d) < 0 and _turn(c, d, a) * _turn(c, d, b) < 0


def _collinear_overlap(a, b, c, d) -> bool:
    if abs(_turn(a, b, c)) > 1e-9 or abs(_turn(a, b, d)) > 1e-9:
        return False
    return _ranges_overlap(a[0], b[0], c[0], d[0]) and _ranges_overlap(a[1], b[1], c[1], d[1])


def _ranges_overlap(a1, a2, b1, b2) -> bool:
    return max(min(a1, a2), min(b1, b2)) + 1e-9 < min(max(a1, a2), max(b1, b2))


def _turn(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _area(points: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        total += point[0] * nxt[1] - nxt[0] * point[1]
    return total / 2.0


def _distance(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])
