"""Pure manufacturing-direction helpers. A direction preference is NOT a machine-ready toolpath."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

Point = tuple[float, float]
_PRECISION_MM = Decimal("0.001")


class CutDirectionError(ValueError):
    """Reject ambiguous or invalid cutter-path direction requests."""


def _coordinate(value: float) -> int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise CutDirectionError("non_finite_point")
    if abs(value) > 1_000_000:
        raise CutDirectionError("coordinate_out_of_bounds")
    return int((Decimal(str(value)) / _PRECISION_MM).to_integral_value(rounding=ROUND_HALF_UP))


def _vertices(points: Sequence[Sequence[float]], *, closed: bool) -> tuple[tuple[int, int], ...]:
    if not isinstance(points, (tuple, list)) or type(closed) is not bool:
        raise CutDirectionError("invalid_path")
    vertices = []
    for point in points:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise CutDirectionError("invalid_point")
        vertices.append((_coordinate(point[0]), _coordinate(point[1])))
    if closed and len(vertices) >= 4 and vertices[0] == vertices[-1]:
        vertices.pop()
    if len(vertices) < (3 if closed else 2) or len(vertices) > 20000:
        raise CutDirectionError("invalid_path_length")
    if len(set(vertices)) != len(vertices):
        raise CutDirectionError("duplicate_vertices")
    return tuple(vertices)


def _minimum_rotation(vertices: tuple[tuple[int, int], ...]):
    """Lexicographically least rotation in O(n) time."""
    count = len(vertices)
    doubled = vertices + vertices
    first, second, offset = 0, 1, 0
    while first < count and second < count and offset < count:
        left, right = doubled[first + offset], doubled[second + offset]
        if left == right:
            offset += 1
            continue
        if left > right:
            first += offset + 1
            if first == second:
                first += 1
        else:
            second += offset + 1
            if second == first:
                second += 1
        offset = 0
    start = min(first, second)
    return tuple(doubled[start:start + count])


def stable_path_id(sheet_no: int, points: Sequence[Sequence[float]], *, closed: bool) -> str:
    """Path identity scoped to a specific sheet AND an immutable plan revision.

    Orientation and the cyclic starting vertex are irrelevant to the identity.
    Duplicate coincident paths must be detected by the caller, not assigned silently.
    """
    if type(sheet_no) is not int or sheet_no <= 0:
        raise CutDirectionError("invalid_sheet_number")
    vertices = _vertices(points, closed=closed)
    shape = (
        min(_minimum_rotation(vertices), _minimum_rotation(vertices[::-1]))
        if closed else min(vertices, vertices[::-1])
    )
    payload = json.dumps([sheet_no, int(closed), shape], separators=(",", ":"))
    return "path-" + hashlib.sha256(payload.encode("ascii")).hexdigest()[:32]


def _undirected_segments(vertices: tuple[tuple[int, int], ...], *, closed: bool):
    edges = list(zip(vertices, vertices[1:]))
    if closed:
        edges.append((vertices[-1], vertices[0]))
    return Counter(tuple(sorted(edge)) for edge in edges)


def orient_path(
    points: Sequence[Sequence[float]],
    *,
    closed: bool,
    reverse: bool = False,
    start_vertex: int | None = None,
) -> tuple[Point, ...]:
    """Change traversal order only: preserve the exact undirected cut geometry.

    This is not a determination of top/bottom, Climb/Conventional, safe release,
    tool offset, safe Z, or a machine-approved NC program.
    """
    vertices = _vertices(points, closed=closed)
    if type(reverse) is not bool:
        raise CutDirectionError("invalid_reverse_flag")
    if start_vertex is not None:
        if type(start_vertex) is not int or not 0 <= start_vertex < len(vertices):
            raise CutDirectionError("invalid_start_vertex")
        if not closed and start_vertex not in (0, len(vertices) - 1):
            raise CutDirectionError("open_path_requires_endpoint")
    if not closed:
        if start_vertex is not None and reverse:
            raise CutDirectionError("conflicting_start_and_direction")
        result = (
            vertices[::-1] if reverse or start_vertex == len(vertices) - 1 else vertices
        )
    else:
        result = vertices[::-1] if reverse else vertices
        if start_vertex is not None:
            wanted = vertices[start_vertex]
            index = result.index(wanted)
            result = result[index:] + result[:index]
    if _undirected_segments(vertices, closed=closed) != _undirected_segments(result, closed=closed):
        raise CutDirectionError("geometry_changed")
    return tuple((x / 1000.0, y / 1000.0) for x, y in result)


__all__ = ["CutDirectionError", "stable_path_id", "orient_path"]
