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
    samples = [0.0, 1.0]
    samples.extend(_bezier_extrema(p0, c1, c2, p1))
    samples = sorted(set(round(value, 6) for value in samples if 0.0 <= value <= 1.0))
    points = [_bezier_point(p0, c1, c2, p1, samples[0])]
    for left, right in zip(samples, samples[1:]):
        piece = _adaptive_bezier(p0, c1, c2, p1, left, right, 0)
        if piece is None:
            return None
        points.extend(piece[1:])
    return points


def _adaptive_bezier(p0, c1, c2, p1, left, right, depth):
    if depth > 16:
        return None
    start = _bezier_point(p0, c1, c2, p1, left)
    end = _bezier_point(p0, c1, c2, p1, right)
    mid_t = (left + right) / 2.0
    mid = _bezier_point(p0, c1, c2, p1, mid_t)
    if _chord_gap(start, end, mid) <= CHORD_ERROR_MM:
        return [start, end]
    left_part = _adaptive_bezier(p0, c1, c2, p1, left, mid_t, depth + 1)
    right_part = _adaptive_bezier(p0, c1, c2, p1, mid_t, right, depth + 1)
    if left_part is None or right_part is None:
        return None
    return left_part[:-1] + right_part


def _bezier_point(p0, c1, c2, p1, t):
    u = 1.0 - t
    return (
        u ** 3 * p0[0] + 3 * u ** 2 * t * c1[0] + 3 * u * t ** 2 * c2[0] + t ** 3 * p1[0],
        u ** 3 * p0[1] + 3 * u ** 2 * t * c1[1] + 3 * u * t ** 2 * c2[1] + t ** 3 * p1[1],
    )


def _bezier_extrema(p0, c1, c2, p1) -> list[float]:
    found = []
    for axis in (0, 1):
        a = -p0[axis] + 3 * c1[axis] - 3 * c2[axis] + p1[axis]
        b = 2 * p0[axis] - 4 * c1[axis] + 2 * c2[axis]
        c = -p0[axis] + c1[axis]
        found.extend(_quadratic_roots(a, b, c))
    return [value for value in found if 0.0 < value < 1.0]


def _quadratic_roots(a, b, c) -> list[float]:
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return []
        return [-c / b]
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    root = math.sqrt(disc)
    return [(-b + root) / (2 * a), (-b - root) / (2 * a)]


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
    if (
        abs(min(xs)) > STORAGE_EPSILON_CM
        or abs(max(xs) - width_cm) > STORAGE_EPSILON_CM
        or abs(min(ys)) > STORAGE_EPSILON_CM
        or abs(max(ys) - length_cm) > STORAGE_EPSILON_CM
    ):
        return _rejected("bounds_not_touched", path_id)
    if _edges_cross(compact) or _edges_overlap(compact):
        return _rejected("self_intersection", path_id)
    if abs(_area(compact)) <= STORAGE_EPSILON_CM:
        return _rejected("invalid_area", path_id)
    return {"status": "ready", "points": compact, "path_id": path_id}


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


def _chord_gap(start, end, mid) -> float:
    length = _distance(start, end)
    if length <= 1e-9:
        return _distance(start, mid)
    area = abs(_turn(start, end, mid))
    return area / length


def _distance(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])
