"""Bind an imported corner contour to one dihedral transform.

Edge identity is the unordered set of boundary edges after collinear vertices
are collapsed. Vertex order, the start point, and winding are not used.
The eight candidates are the four clockwise quarter-turns, plus one horizontal
reflection followed by those same four turns. A vertical reflection is not a
separate candidate: it is one of those eight. Several representations are
accepted only when they place every semantic edge on the same physical edge.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    CLIPPED_CORNER_POSITIONS,
    CLIPPED_CORNER_TYPE,
    L_SHAPED_CORNER_TYPE,
    is_corner_cut,
)

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class CornerContourMatch:
    quarter_turns: int | None
    reason: str
    mirrored: bool = False


def match_corner_contour(
    outer_mm: Sequence[Sequence[float]],
    *,
    piece_type: str,
    position: str,
    width_cm: float,
    length_cm: float,
    cut_width_cm: float,
    cut_length_cm: float,
    tolerance_mm: float = GEOMETRY_TOLERANCE_MM,
    edge_bands: Mapping[str, str] | None = None,
) -> CornerContourMatch:
    """Return the unique dihedral transform of the saved corner, or no match."""

    if not is_corner_cut(piece_type):
        return CornerContourMatch(None, "invalid")
    if position not in CLIPPED_CORNER_POSITIONS:
        return CornerContourMatch(None, "invalid")

    width_mm = float(width_cm) * 10.0
    height_mm = float(length_cm) * 10.0
    cut_x = float(cut_width_cm) * 10.0
    cut_y = float(cut_length_cm) * 10.0
    if not (
        width_mm > 0
        and height_mm > 0
        and 0 < cut_x < width_mm
        and 0 < cut_y < height_mm
    ):
        return CornerContourMatch(None, "invalid")

    canonical = _corner_polygon_mm(
        piece_type=piece_type,
        position=position,
        width_mm=width_mm,
        height_mm=height_mm,
        cut_x_mm=cut_x,
        cut_y_mm=cut_y,
    )
    if canonical is None:
        return CornerContourMatch(None, "invalid")

    actual = _prepare_ring(outer_mm, tolerance_mm)
    if len(actual) < 3:
        return CornerContourMatch(None, "none")
    actual = _localize(_collapse_collinear(actual, tolerance_mm))

    groups: dict[frozenset[tuple[int, str]], list[tuple[bool, int]]] = {}
    for mirrored in (False, True):
        for quarter_turns in range(4):
            signature = _contour_signature(
                actual,
                canonical,
                mirrored=mirrored,
                quarter_turns=quarter_turns,
                width=width_mm,
                height=height_mm,
                tolerance_mm=tolerance_mm,
                edge_bands=edge_bands,
            )
            if signature is None:
                continue
            groups.setdefault(signature, []).append((mirrored, quarter_turns))

    if not groups:
        return CornerContourMatch(None, "none")
    if len(groups) > 1:
        return CornerContourMatch(None, "ambiguous")
    mirrored, quarter_turns = min(
        next(iter(groups.values())),
        key=lambda item: (item[0], item[1]),
    )
    return CornerContourMatch(quarter_turns, "unique", mirrored)


def _transform_point(
    point: Point,
    *,
    mirrored: bool,
    quarter_turns: int,
    width: float,
    height: float,
) -> Point:
    """Apply the horizontal reflection first, then clockwise quarter-turns."""

    x, y = point
    box_width, box_height = width, height
    if mirrored:
        x = box_width - x
    for _ in range(quarter_turns):
        x, y = box_height - y, x
        box_width, box_height = box_height, box_width
    return (x, y)


def _transform_polygon(
    points: Sequence[Point],
    *,
    mirrored: bool,
    quarter_turns: int,
    width: float,
    height: float,
) -> list[Point]:
    current = [
        _transform_point(
            point,
            mirrored=mirrored,
            quarter_turns=0,
            width=width,
            height=height,
        )
        if mirrored
        else point
        for point in points
    ]
    box_width, box_height = width, height
    for _ in range(quarter_turns):
        current, box_width, box_height = _rotate_clockwise(current, box_width, box_height)
    return current


def _edge_role(start: Point, end: Point, width: float, height: float) -> str:
    """Name a canonical edge before any transform. The name travels with the edge."""

    limit = GEOMETRY_TOLERANCE_MM
    horizontal = abs(start[1] - end[1]) <= limit
    vertical = abs(start[0] - end[0]) <= limit
    if horizontal and abs(start[1]) <= limit and abs(end[1]) <= limit:
        return "top"
    if horizontal and abs(start[1] - height) <= limit and abs(end[1] - height) <= limit:
        return "bottom"
    if vertical and abs(start[0]) <= limit and abs(end[0]) <= limit:
        return "left"
    if vertical and abs(start[0] - width) <= limit and abs(end[0] - width) <= limit:
        return "right"
    if horizontal:
        return "inner_horizontal"
    if vertical:
        return "inner_vertical"
    return "chord"


def _contour_signature(
    actual: Sequence[Point],
    canonical: Sequence[Point],
    *,
    mirrored: bool,
    quarter_turns: int,
    width: float,
    height: float,
    tolerance_mm: float,
    edge_bands: Mapping[str, str] | None = None,
) -> frozenset[tuple[int, str]] | None:
    transformed = _transform_polygon(
        canonical,
        mirrored=mirrored,
        quarter_turns=quarter_turns,
        width=width,
        height=height,
    )
    prepared = _collapse_collinear(transformed, tolerance_mm)
    if len(prepared) < 3:
        return None
    origin_x = min(point[0] for point in prepared)
    origin_y = min(point[1] for point in prepared)
    localized = [(point[0] - origin_x, point[1] - origin_y) for point in prepared]
    if not _same_edge_set(actual, localized, tolerance_mm):
        return None

    actual_edges = _edges(actual)
    unused = set(range(len(actual_edges)))
    signature: list[tuple[int, str]] = []
    for index, start in enumerate(canonical):
        end = canonical[(index + 1) % len(canonical)]
        moved = (
            _transform_point(
                start,
                mirrored=mirrored,
                quarter_turns=quarter_turns,
                width=width,
                height=height,
            ),
            _transform_point(
                end,
                mirrored=mirrored,
                quarter_turns=quarter_turns,
                width=width,
                height=height,
            ),
        )
        local_edge = (
            (moved[0][0] - origin_x, moved[0][1] - origin_y),
            (moved[1][0] - origin_x, moved[1][1] - origin_y),
        )
        match = next(
            (
                edge_index
                for edge_index in unused
                if _same_undirected_edge(local_edge, actual_edges[edge_index], tolerance_mm)
            ),
            None,
        )
        if match is None:
            return None
        unused.remove(match)
        role = _edge_role(start, end, width, height)
        token = role if edge_bands is None else str(edge_bands.get(role, role))
        signature.append((match, token))
    if unused:
        return None
    return frozenset(signature)


def _corner_polygon_mm(
    *,
    piece_type: str,
    position: str,
    width_mm: float,
    height_mm: float,
    cut_x_mm: float,
    cut_y_mm: float,
) -> list[Point] | None:
    """Finished-orientation polygon in the same y-down frame as usable-sheet geometry."""

    width = width_mm
    height = height_mm
    cut_x = cut_x_mm
    cut_y = cut_y_mm
    if piece_type == L_SHAPED_CORNER_TYPE:
        polygons = {
            "Top Right": [
                (0.0, 0.0),
                (width - cut_x, 0.0),
                (width - cut_x, cut_y),
                (width, cut_y),
                (width, height),
                (0.0, height),
            ],
            "Top Left": [
                (cut_x, 0.0),
                (width, 0.0),
                (width, height),
                (0.0, height),
                (0.0, cut_y),
                (cut_x, cut_y),
            ],
            "Bottom Right": [
                (0.0, 0.0),
                (width, 0.0),
                (width, height - cut_y),
                (width - cut_x, height - cut_y),
                (width - cut_x, height),
                (0.0, height),
            ],
            "Bottom Left": [
                (0.0, 0.0),
                (width, 0.0),
                (width, height),
                (cut_x, height),
                (cut_x, height - cut_y),
                (0.0, height - cut_y),
            ],
        }
    elif piece_type == CLIPPED_CORNER_TYPE:
        polygons = {
            "Top Right": [
                (0.0, 0.0),
                (width - cut_x, 0.0),
                (width, cut_y),
                (width, height),
                (0.0, height),
            ],
            "Top Left": [
                (cut_x, 0.0),
                (width, 0.0),
                (width, height),
                (0.0, height),
                (0.0, cut_y),
            ],
            "Bottom Right": [
                (0.0, 0.0),
                (width, 0.0),
                (width, height - cut_y),
                (width - cut_x, height),
                (0.0, height),
            ],
            "Bottom Left": [
                (0.0, 0.0),
                (width, 0.0),
                (width, height),
                (cut_x, height),
                (0.0, height - cut_y),
            ],
        }
    else:
        return None
    return polygons.get(position)


def _prepare_ring(
    outer_mm: Sequence[Sequence[float]],
    tolerance_mm: float,
) -> list[Point]:
    points: list[Point] = []
    for point in outer_mm:
        if len(point) != 2:
            continue
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        points.append((x, y))
    return _dedupe_ring(points, tolerance_mm)


def _dedupe_ring(points: Sequence[Point], tolerance_mm: float) -> list[Point]:
    """Drop repeated vertices without consuming a real edge.

    Match tolerance may be widened by a caller, but duplicate removal stays at
    the geometry contract so a long tolerance cannot collapse the ring first.
    """

    if not points:
        return []
    limit = min(float(tolerance_mm), GEOMETRY_TOLERANCE_MM)
    deduped = [points[0]]
    for point in points[1:]:
        if math.dist(deduped[-1], point) > limit:
            deduped.append(point)
    if len(deduped) > 1 and math.dist(deduped[0], deduped[-1]) <= limit:
        deduped.pop()
    return deduped


def _localize(points: Sequence[Point]) -> list[Point]:
    if not points:
        return []
    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    return [(point[0] - min_x, point[1] - min_y) for point in points]


def _rotate_clockwise(
    points: Sequence[Point],
    width: float,
    height: float,
) -> tuple[list[Point], float, float]:
    # Screen/usable-sheet y grows downward. One clockwise quarter-turn:
    # (x, y) -> (height - y, x), then the new width is the old height.
    return [(height - point[1], point[0]) for point in points], height, width


def _collapse_collinear(points: Sequence[Point], tolerance_mm: float) -> list[Point]:
    current = list(points)
    changed = True
    while changed and len(current) >= 4:
        changed = False
        count = len(current)
        kept: list[Point] = []
        for index, point in enumerate(current):
            previous = current[(index - 1) % count]
            nxt = current[(index + 1) % count]
            if _on_segment(point, previous, nxt, tolerance_mm):
                changed = True
                continue
            kept.append(point)
        current = _dedupe_ring(kept, tolerance_mm)
    return current


def _on_segment(point: Point, start: Point, end: Point, tolerance_mm: float) -> bool:
    segment = math.dist(start, end)
    if segment <= tolerance_mm:
        return math.dist(point, start) <= tolerance_mm
    cross = abs(
        (point[0] - start[0]) * (end[1] - start[1])
        - (point[1] - start[1]) * (end[0] - start[0])
    )
    if cross / segment > tolerance_mm:
        return False
    dot = (point[0] - start[0]) * (end[0] - start[0]) + (point[1] - start[1]) * (
        end[1] - start[1]
    )
    return -tolerance_mm * segment <= dot <= (segment * segment) + (tolerance_mm * segment)


def _edges(points: Sequence[Point]) -> list[tuple[Point, Point]]:
    return [
        (points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    ]


def _same_edge_set(
    actual: Sequence[Point],
    expected: Sequence[Point],
    tolerance_mm: float,
) -> bool:
    if len(actual) != len(expected) or len(actual) < 3:
        return False
    unused = set(range(len(actual)))
    actual_edges = _edges(actual)
    for edge in _edges(expected):
        match = next(
            (
                index
                for index in unused
                if _same_undirected_edge(edge, actual_edges[index], tolerance_mm)
            ),
            None,
        )
        if match is None:
            return False
        unused.remove(match)
    return not unused


def _same_undirected_edge(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
    tolerance_mm: float,
) -> bool:
    start, end = first
    other_start, other_end = second
    return (
        math.dist(start, other_start) <= tolerance_mm
        and math.dist(end, other_end) <= tolerance_mm
    ) or (
        math.dist(start, other_end) <= tolerance_mm
        and math.dist(end, other_start) <= tolerance_mm
    )
