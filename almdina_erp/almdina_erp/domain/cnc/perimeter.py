"""Connected outer CUT_PATH perimeter extracted from approved cutter centers.

The perimeter is the outer boundary of the cut-network itself, not the
rectangular ``SHEET_OUTLINE``. Shared internal edges are excluded. The
extractor never invents segments that are absent from the approved network.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.cnc.operational_file import OperationalFileError


SHEET_PERIMETER_PATH_KEY = "cut_path:sheet_perimeter"
CUT_PATH_INTERNAL_SEQUENCE_KEY = "cut_path:internals"
PERIMETER_JOIN_SEPARATE = "separate"
PERIMETER_JOIN_CONNECTED = "connected"
POINT_QUANTUM_MM = 0.05
CONNECTED_CUT_PATH_ORDER_KEYS = (
    CUT_PATH_INTERNAL_SEQUENCE_KEY,
    SHEET_PERIMETER_PATH_KEY,
)


@dataclass(frozen=True, slots=True)
class PerimeterResult:
    points: tuple[tuple[float, float], ...]
    closed: bool
    edge_count: int


def normalize_perimeter_join_mode(value: object) -> str:
    token = str(value or "").strip().lower()
    if token in {"", PERIMETER_JOIN_SEPARATE, "disconnected"}:
        return PERIMETER_JOIN_SEPARATE
    if token == PERIMETER_JOIN_CONNECTED:
        return PERIMETER_JOIN_CONNECTED
    raise OperationalFileError("perimeter_join_mode_invalid")


def quantize_point(point: Sequence[float], *, quantum: float = POINT_QUANTUM_MM) -> tuple[float, float]:
    scale = 1.0 / float(quantum)
    return (round(float(point[0]) * scale) / scale, round(float(point[1]) * scale) / scale)


def undirected_edge(
    start: Sequence[float],
    end: Sequence[float],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> tuple[tuple[float, float], tuple[float, float]]:
    left = quantize_point(start, quantum=quantum)
    right = quantize_point(end, quantum=quantum)
    if left == right:
        raise OperationalFileError("perimeter_geometry_invalid")
    return (left, right) if left <= right else (right, left)


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> bool:
    if point in {start, end}:
        return False
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 0:
        return False
    cross = abs((point[0] - start[0]) * dy - (point[1] - start[1]) * dx)
    if cross > quantum * (length2 ** 0.5 + quantum):
        return False
    dot = (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    return -quantum <= dot <= length2 + quantum


def split_segments_at_vertices(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Split edges where another network vertex lands mid-segment (T-joints)."""

    quantized: list[tuple[tuple[float, float], tuple[float, float]]] = []
    vertices: set[tuple[float, float]] = set()
    for segment in segments:
        if not isinstance(segment, Sequence) or len(segment) != 2:
            raise OperationalFileError("perimeter_geometry_invalid")
        start = quantize_point(segment[0], quantum=quantum)
        end = quantize_point(segment[1], quantum=quantum)
        if start == end:
            raise OperationalFileError("perimeter_geometry_invalid")
        quantized.append((start, end))
        vertices.add(start)
        vertices.add(end)
    split: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for start, end in quantized:
        mids = [
            point
            for point in vertices
            if _point_on_segment(point, start, end, quantum=quantum)
        ]
        if not mids:
            split.append((start, end))
            continue
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        ordered = sorted(
            mids,
            key=lambda point: (point[0] - start[0]) * dx + (point[1] - start[1]) * dy,
        )
        cursor = start
        for point in ordered:
            if point == cursor:
                continue
            split.append((cursor, point))
            cursor = point
        if cursor != end:
            split.append((cursor, end))
    return split


def segment_edge_multiset(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> Counter[tuple[tuple[float, float], tuple[float, float]]]:
    counts: Counter[tuple[tuple[float, float], tuple[float, float]]] = Counter()
    for segment in split_segments_at_vertices(segments, quantum=quantum):
        counts[undirected_edge(segment[0], segment[1], quantum=quantum)] += 1
    return counts


def polyline_segments(
    points: Sequence[Sequence[float]],
    *,
    closed: bool,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if len(points) < 2:
        return []
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for index in range(len(points) - 1):
        edges.append((tuple(points[index]), tuple(points[index + 1])))
    if closed and len(points) >= 3:
        first = tuple(points[0])
        last = tuple(points[-1])
        if first != last:
            edges.append((last, first))
    return edges


def edge_sets_equal(
    left: Sequence[Sequence[Sequence[float]]],
    right: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> bool:
    return segment_edge_multiset(left, quantum=quantum) == segment_edge_multiset(right, quantum=quantum)


def _candidate_boundary_edges(
    counts: Counter[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    if any(count > 2 for count in counts.values()):
        raise OperationalFileError("perimeter_geometry_ambiguous")
    candidates = [edge for edge, count in counts.items() if count == 1]
    if not candidates:
        raise OperationalFileError("perimeter_unavailable")
    return candidates


def _adjacency(
    edges: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> dict[tuple[float, float], list[tuple[float, float]]]:
    graph: dict[tuple[float, float], list[tuple[float, float]]] = defaultdict(list)
    for start, end in edges:
        graph[start].append(end)
        graph[end].append(start)
    for node, neighbors in list(graph.items()):
        graph[node] = sorted(set(neighbors))
    return graph


def _prune_dangling_edges(
    graph: dict[tuple[float, float], list[tuple[float, float]]],
) -> dict[tuple[float, float], list[tuple[float, float]]]:
    """Remove tree stubs (T-joints) attached to the cut network."""

    working = {node: list(neighbors) for node, neighbors in graph.items()}
    changed = True
    while changed:
        changed = False
        leaves = [node for node, neighbors in working.items() if len(neighbors) == 1]
        for leaf in leaves:
            if leaf not in working or len(working[leaf]) != 1:
                continue
            neighbor = working[leaf][0]
            working[leaf] = []
            if neighbor in working:
                working[neighbor] = [node for node in working[neighbor] if node != leaf]
            changed = True
    return {
        node: sorted(set(neighbors))
        for node, neighbors in working.items()
        if neighbors
    }


def _turn_angle(
    previous: tuple[float, float],
    current: tuple[float, float],
    nxt: tuple[float, float],
) -> float:
    incoming = (current[0] - previous[0], current[1] - previous[1])
    outgoing = (nxt[0] - current[0], nxt[1] - current[1])
    return math.atan2(
        incoming[0] * outgoing[1] - incoming[1] * outgoing[0],
        incoming[0] * outgoing[0] + incoming[1] * outgoing[1],
    )


def _walk_outer_face(
    graph: Mapping[tuple[float, float], Sequence[tuple[float, float]]],
) -> tuple[tuple[float, float], ...]:
    """Trace the exterior face of a connected straight-line planar graph.

    Shared internal cuts remain as chords. The walk always keeps the exterior
    on the right so the resulting cycle is the true outer perimeter.
    """

    if not graph:
        raise OperationalFileError("perimeter_unavailable")
    if any(len(neighbors) < 2 for neighbors in graph.values()):
        raise OperationalFileError("perimeter_not_closed")
    components = 0
    unseen = set(graph)
    while unseen:
        components += 1
        stack = [unseen.pop()]
        while stack:
            node = stack.pop()
            for neighbor in graph[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
    if components > 1:
        raise OperationalFileError("perimeter_components_disconnected")

    start = min(graph, key=lambda point: (point[1], point[0]))
    first = min(
        graph[start],
        key=lambda point: (
            math.atan2(point[1] - start[1], point[0] - start[0]),
            math.hypot(point[0] - start[0], point[1] - start[1]),
        ),
    )
    points: list[tuple[float, float]] = [start]
    previous, current = start, first
    visited_directed: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    while True:
        if (previous, current) in visited_directed:
            raise OperationalFileError("perimeter_geometry_ambiguous")
        visited_directed.add((previous, current))
        points.append(current)
        options = [node for node in graph[current] if node != previous]
        if not options:
            raise OperationalFileError("perimeter_not_closed")
        if len(options) == 1:
            nxt = options[0]
        else:
            # Most clockwise turn keeps the exterior on the right.
            nxt = min(options, key=lambda node: _turn_angle(previous, current, node))
        previous, current = current, nxt
        if previous == start and current == first:
            break
        if len(points) > len(graph) * 2 + 2:
            raise OperationalFileError("perimeter_geometry_ambiguous")
    if len(points) < 4:
        raise OperationalFileError("perimeter_unavailable")
    # points = [start, first, ..., start]; drop the repeated close.
    if points[-1] == start:
        points = points[:-1]
    if len(points) < 3:
        raise OperationalFileError("perimeter_unavailable")
    return tuple(points)


def extract_connected_perimeter(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> PerimeterResult:
    """Return one closed outer cycle from the approved cut-segment network."""

    counts = segment_edge_multiset(segments, quantum=quantum)
    if not counts:
        raise OperationalFileError("perimeter_unavailable")
    # Prefer undirected multiplicity when shared walls still appear twice
    # (independent closed rings). Fall back to an outer-face walk when the
    # manufacturing network has already merged shared centers to one edge.
    doubled = [edge for edge, count in counts.items() if count == 1]
    if doubled and all(count <= 2 for count in counts.values()) and any(
        count == 2 for count in counts.values()
    ):
        pruned = _prune_dangling_edges(_adjacency(doubled))
        if pruned and all(len(neighbors) == 2 for neighbors in pruned.values()):
            points = _walk_outer_face(pruned)
            return PerimeterResult(points=points, closed=True, edge_count=len(points))
    candidates = _candidate_boundary_edges(counts)
    pruned = _prune_dangling_edges(_adjacency(candidates))
    points = _walk_outer_face(pruned)
    return PerimeterResult(points=points, closed=True, edge_count=len(points))


def remaining_segments_after_perimeter(
    segments: Sequence[Sequence[Sequence[float]]],
    perimeter: PerimeterResult,
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Return non-perimeter edges without inventing or dropping coverage."""

    before = segment_edge_multiset(segments, quantum=quantum)
    perimeter_edges = segment_edge_multiset(
        polyline_segments(perimeter.points, closed=perimeter.closed),
        quantum=quantum,
    )
    if any(before[edge] < count for edge, count in perimeter_edges.items()):
        raise OperationalFileError("perimeter_geometry_invalid")
    remaining = before.copy()
    remaining.subtract(perimeter_edges)
    leftover: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for edge, count in remaining.items():
        for _ in range(count):
            leftover.append(edge)
    restored = segment_edge_multiset(
        leftover + list(polyline_segments(perimeter.points, closed=True)),
        quantum=quantum,
    )
    if restored != before:
        raise OperationalFileError("perimeter_geometry_invalid")
    return leftover


def connected_cut_path_order_keys() -> tuple[str, ...]:
    """Stable reorder identities honored by compile/NC for connected perimeter."""

    return CONNECTED_CUT_PATH_ORDER_KEYS


def default_cut_path_sequence(path_keys: Sequence[str] | None = None) -> tuple[str, ...]:
    """Perimeter runs after the internal CUT_PATH bucket by default."""

    _ = path_keys  # retained for call-site compatibility
    return CONNECTED_CUT_PATH_ORDER_KEYS


def coerce_cut_path_sequence_request(
    requested: Sequence[str] | None,
) -> tuple[str, ...] | None:
    """Return None for unset/empty; otherwise a canonical two-key order.

    Legacy saved sequences that listed piece path keys are reduced to the
    perimeter-early / perimeter-late contract the engine can actually honor.
    Explicit non-empty sequences that cannot be interpreted are rejected.
    """

    if requested is None:
        return None
    keys = [str(item or "").strip() for item in requested if str(item or "").strip()]
    if not keys:
        return None
    if len(keys) != len(set(keys)):
        raise OperationalFileError("cut_path_sequence_invalid")
    canonical = set(CONNECTED_CUT_PATH_ORDER_KEYS)
    if set(keys) == canonical and len(keys) == 2:
        if keys[0] not in canonical or keys[1] not in canonical:
            raise OperationalFileError("cut_path_sequence_invalid")
        return (keys[0], keys[1])
    if SHEET_PERIMETER_PATH_KEY in keys:
        if keys[0] == SHEET_PERIMETER_PATH_KEY:
            return (SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY)
        return CONNECTED_CUT_PATH_ORDER_KEYS
    raise OperationalFileError("cut_path_sequence_invalid")


def resolve_cut_path_sequence(
    present: Sequence[str],
    requested: Sequence[str] | None,
    *,
    perimeter_early_confirmed: bool = False,
) -> tuple[str, ...]:
    present_keys = [str(key) for key in present]
    present_set = set(present_keys)
    if SHEET_PERIMETER_PATH_KEY not in present_set and CUT_PATH_INTERNAL_SEQUENCE_KEY not in present_set:
        return tuple(present_keys)
    ordered = coerce_cut_path_sequence_request(requested)
    if ordered is None:
        ordered = default_cut_path_sequence(present_keys)
    if set(ordered) != set(CONNECTED_CUT_PATH_ORDER_KEYS) or len(ordered) != 2:
        raise OperationalFileError("cut_path_sequence_invalid")
    if ordered[0] == SHEET_PERIMETER_PATH_KEY and not perimeter_early_confirmed:
        raise OperationalFileError("perimeter_cut_early_unconfirmed")
    return ordered


def prefer_uploaded_perimeter_polyline(
    cut_paths: Sequence[Mapping[str, object]],
    expected_outer_segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> PerimeterResult | None:
    """Reuse a closed uploaded polyline when its edges match the outer network."""

    expected = extract_connected_perimeter(expected_outer_segments, quantum=quantum)
    expected_edges = segment_edge_multiset(
        polyline_segments(expected.points, closed=True),
        quantum=quantum,
    )
    for path in cut_paths:
        if not bool(path.get("closed")):
            continue
        points = path.get("points") or []
        if not isinstance(points, Sequence) or len(points) < 3:
            continue
        candidate_edges = segment_edge_multiset(
            polyline_segments(points, closed=True),
            quantum=quantum,
        )
        if candidate_edges != expected_edges:
            continue
        ordered = tuple(quantize_point(point, quantum=quantum) for point in points)
        if ordered[0] == ordered[-1] and len(ordered) > 1:
            ordered = ordered[:-1]
        if len(ordered) < 3:
            continue
        return PerimeterResult(points=ordered, closed=True, edge_count=len(candidate_edges))
    return None


__all__ = [
    "CONNECTED_CUT_PATH_ORDER_KEYS",
    "CUT_PATH_INTERNAL_SEQUENCE_KEY",
    "PERIMETER_JOIN_CONNECTED",
    "PERIMETER_JOIN_SEPARATE",
    "POINT_QUANTUM_MM",
    "PerimeterResult",
    "SHEET_PERIMETER_PATH_KEY",
    "coerce_cut_path_sequence_request",
    "connected_cut_path_order_keys",
    "default_cut_path_sequence",
    "edge_sets_equal",
    "extract_connected_perimeter",
    "normalize_perimeter_join_mode",
    "polyline_segments",
    "prefer_uploaded_perimeter_polyline",
    "quantize_point",
    "remaining_segments_after_perimeter",
    "resolve_cut_path_sequence",
    "segment_edge_multiset",
    "split_segments_at_vertices",
    "undirected_edge",
]
