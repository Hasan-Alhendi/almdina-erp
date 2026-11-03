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


@dataclass(frozen=True, slots=True)
class NetworkComponentDiagnosis:
    index: int
    closed: bool
    role: str
    bounds: tuple[float, float, float, float]
    point_count: int
    edge_count: int
    sample_point: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class PerimeterNetworkDiagnosis:
    component_count: int
    closed_component_count: int
    uploaded_closed_polyline_count: int
    components: tuple[NetworkComponentDiagnosis, ...]
    outer_index: int | None
    reject_code: str | None


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


def _signed_area(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    total = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        total += point[0] * nxt[1] - nxt[0] * point[1]
    return 0.5 * total


def _bounds(points: Sequence[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(point[0] for point in points) / float(len(points)),
        sum(point[1] for point in points) / float(len(points)),
    )


def _point_in_ring(
    point: tuple[float, float],
    ring: Sequence[tuple[float, float]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> bool:
    """Ray-cast containment; boundary points count as inside."""

    if any(
        _point_on_segment(point, ring[index], ring[(index + 1) % len(ring)], quantum=quantum)
        or point == ring[index]
        for index in range(len(ring))
    ):
        return True
    x, y = point
    inside = False
    for index, start in enumerate(ring):
        end = ring[(index + 1) % len(ring)]
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) == (y2 > y):
            continue
        if abs(y2 - y1) <= quantum:
            continue
        crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        if crossing_x > x:
            inside = not inside
    return inside


def _split_graph_components(
    graph: Mapping[tuple[float, float], Sequence[tuple[float, float]]],
) -> list[dict[tuple[float, float], list[tuple[float, float]]]]:
    unseen = set(graph)
    components: list[dict[tuple[float, float], list[tuple[float, float]]]] = []
    while unseen:
        start = unseen.pop()
        stack = [start]
        nodes = {start}
        while stack:
            node = stack.pop()
            for neighbor in graph[node]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    nodes.add(neighbor)
                    stack.append(neighbor)
        components.append(
            {node: [neighbor for neighbor in graph[node] if neighbor in nodes] for node in nodes}
        )
    return components


def _walk_outer_face(
    graph: Mapping[tuple[float, float], Sequence[tuple[float, float]]],
) -> tuple[tuple[float, float], ...]:
    """Trace the exterior face of one connected straight-line planar graph."""

    if not graph:
        raise OperationalFileError("perimeter_unavailable")
    if any(len(neighbors) < 2 for neighbors in graph.values()):
        raise OperationalFileError("perimeter_not_closed")

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
    if points[-1] == start:
        points = points[:-1]
    if len(points) < 3:
        raise OperationalFileError("perimeter_unavailable")
    return tuple(points)


def _cycle_from_component(
    graph: Mapping[tuple[float, float], Sequence[tuple[float, float]]],
) -> tuple[tuple[float, float], ...] | None:
    pruned = _prune_dangling_edges(dict(graph))
    if not pruned:
        return None
    try:
        return _walk_outer_face(pruned)
    except OperationalFileError:
        return None


def _boundary_graph_from_segments(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> dict[tuple[float, float], list[tuple[float, float]]]:
    counts = segment_edge_multiset(segments, quantum=quantum)
    if not counts:
        return {}
    doubled = [edge for edge, count in counts.items() if count == 1]
    if doubled and all(count <= 2 for count in counts.values()) and any(
        count == 2 for count in counts.values()
    ):
        pruned = _prune_dangling_edges(_adjacency(doubled))
        if pruned:
            return pruned
    candidates = _candidate_boundary_edges(counts)
    return _prune_dangling_edges(_adjacency(candidates))


def _select_outer_cycle(
    cycles: Sequence[tuple[tuple[float, float], ...]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> tuple[tuple[float, float], ...]:
    if not cycles:
        raise OperationalFileError("perimeter_unavailable")
    ranked = sorted(
        cycles,
        key=lambda ring: (abs(_signed_area(ring)), _bounds(ring)[2] - _bounds(ring)[0]),
        reverse=True,
    )
    outer = ranked[0]
    for ring in ranked[1:]:
        if not all(_point_in_ring(point, outer, quantum=quantum) for point in ring):
            raise OperationalFileError("perimeter_components_disconnected")
    return outer


def diagnose_cut_network(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    uploaded_cut_paths: Sequence[Mapping[str, object]] | None = None,
    quantum: float = POINT_QUANTUM_MM,
) -> PerimeterNetworkDiagnosis:
    """Explain how CUT_PATH components relate before choosing a perimeter."""

    graph = _boundary_graph_from_segments(segments, quantum=quantum)
    components = _split_graph_components(graph) if graph else []
    closed_rings: list[tuple[tuple[float, float], ...]] = []
    rows: list[NetworkComponentDiagnosis] = []
    for index, component in enumerate(components):
        cycle = _cycle_from_component(component)
        points = tuple(sorted(component))
        if cycle is not None:
            closed_rings.append(cycle)
            sample = _centroid(cycle)
            bounds = _bounds(cycle)
            closed = True
            point_count = len(cycle)
            edge_count = len(cycle)
        else:
            sample = points[0] if points else None
            bounds = _bounds(points) if points else (0.0, 0.0, 0.0, 0.0)
            closed = False
            point_count = len(points)
            edge_count = sum(len(neighbors) for neighbors in component.values()) // 2
        rows.append(
            NetworkComponentDiagnosis(
                index=index,
                closed=closed,
                role="unresolved",
                bounds=bounds,
                point_count=point_count,
                edge_count=edge_count,
                sample_point=sample,
            )
        )
    reject: str | None = None
    outer_index: int | None = None
    try:
        if closed_rings:
            outer = _select_outer_cycle(closed_rings, quantum=quantum)
            outer_edges = segment_edge_multiset(
                polyline_segments(outer, closed=True),
                quantum=quantum,
            )
            for row, component in zip(rows, components):
                cycle = _cycle_from_component(component)
                if cycle is None:
                    sample = row.sample_point
                    role = (
                        "internal"
                        if sample is not None and _point_in_ring(sample, outer, quantum=quantum)
                        else "open"
                    )
                elif segment_edge_multiset(
                    polyline_segments(cycle, closed=True),
                    quantum=quantum,
                ) == outer_edges:
                    role = "outer"
                    outer_index = row.index
                elif all(_point_in_ring(point, outer, quantum=quantum) for point in cycle):
                    role = "internal"
                else:
                    role = "external_disconnected"
                rows[row.index] = NetworkComponentDiagnosis(
                    index=row.index,
                    closed=row.closed,
                    role=role,
                    bounds=row.bounds,
                    point_count=row.point_count,
                    edge_count=row.edge_count,
                    sample_point=row.sample_point,
                )
        elif components:
            reject = "perimeter_not_closed"
        else:
            reject = "perimeter_unavailable"
    except OperationalFileError as exc:
        reject = exc.code
        rows = [
            NetworkComponentDiagnosis(
                index=row.index,
                closed=row.closed,
                role="external_disconnected" if row.closed else row.role,
                bounds=row.bounds,
                point_count=row.point_count,
                edge_count=row.edge_count,
                sample_point=row.sample_point,
            )
            for row in rows
        ]
    uploaded_closed = 0
    for path in uploaded_cut_paths or ():
        if bool(path.get("closed")) and isinstance(path.get("points"), Sequence) and len(path.get("points") or []) >= 3:
            uploaded_closed += 1
    return PerimeterNetworkDiagnosis(
        component_count=len(components),
        closed_component_count=sum(1 for row in rows if row.closed),
        uploaded_closed_polyline_count=uploaded_closed,
        components=tuple(rows),
        outer_index=outer_index,
        reject_code=reject,
    )


def extract_connected_perimeter(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> PerimeterResult:
    """Return one closed outer cycle from the approved cut-segment network.

    Separate internal closed loops (holes / interior cuts) do not force
    ``perimeter_components_disconnected``. Only truly separate external
    components are rejected.
    """

    graph = _boundary_graph_from_segments(segments, quantum=quantum)
    if not graph:
        raise OperationalFileError("perimeter_unavailable")
    cycles: list[tuple[tuple[float, float], ...]] = []
    for component in _split_graph_components(graph):
        cycle = _cycle_from_component(component)
        if cycle is not None:
            cycles.append(cycle)
    if not cycles:
        raise OperationalFileError("perimeter_not_closed")
    points = _select_outer_cycle(cycles, quantum=quantum)
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
    """Compatibility helper for legacy within-CUT_PATH sequence storage.

    Operation order is the authority for connected perimeter placement.
    ``perimeter_early_confirmed`` is retained for call-site compatibility and
    no longer rejects perimeter-before-internals here.
    """

    _ = perimeter_early_confirmed
    present_keys = [str(key) for key in present]
    present_set = set(present_keys)
    if SHEET_PERIMETER_PATH_KEY not in present_set and CUT_PATH_INTERNAL_SEQUENCE_KEY not in present_set:
        return tuple(present_keys)
    ordered = coerce_cut_path_sequence_request(requested)
    if ordered is None:
        ordered = default_cut_path_sequence(present_keys)
    if set(ordered) != set(CONNECTED_CUT_PATH_ORDER_KEYS) or len(ordered) != 2:
        raise OperationalFileError("cut_path_sequence_invalid")
    return ordered


def prefer_uploaded_perimeter_polyline(
    cut_paths: Sequence[Mapping[str, object]],
    expected_outer_segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> PerimeterResult | None:
    """Reuse a closed uploaded polyline when it is the approved outer perimeter.

    Closed interior rings are ignored. A valid uploaded outer polyline is
    accepted even when interior cut components are disconnected from it.
    """

    network_edges = segment_edge_multiset(expected_outer_segments, quantum=quantum)
    if not network_edges:
        return None
    candidates: list[
        tuple[float, tuple[tuple[float, float], ...], Counter[tuple[tuple[float, float], tuple[float, float]]]]
    ] = []
    for path in cut_paths:
        if not bool(path.get("closed")):
            continue
        points = path.get("points") or []
        if not isinstance(points, Sequence) or len(points) < 3:
            continue
        ordered = tuple(quantize_point(point, quantum=quantum) for point in points)
        if ordered[0] == ordered[-1] and len(ordered) > 1:
            ordered = ordered[:-1]
        if len(ordered) < 3:
            continue
        candidate_edges = segment_edge_multiset(
            polyline_segments(ordered, closed=True),
            quantum=quantum,
        )
        if any(network_edges[edge] < count for edge, count in candidate_edges.items()):
            continue
        if not candidate_edges:
            continue
        candidates.append((abs(_signed_area(ordered)), ordered, candidate_edges))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_area, best_points, best_edges = candidates[0]
    if best_area <= 0:
        return None
    # Reject a hole mistaken as outer when a larger valid closed ring exists.
    for area, points, _edges in candidates[1:]:
        if area >= best_area:
            continue
        if not all(_point_in_ring(point, best_points, quantum=quantum) for point in points):
            # Sibling exterior ring → cannot prefer one uploaded polyline alone.
            return None
    # Prefer exact outer match when network extraction succeeds; otherwise keep
    # the largest uploaded ring whose edges exist in the approved network.
    try:
        expected = extract_connected_perimeter(expected_outer_segments, quantum=quantum)
    except OperationalFileError:
        expected = None
    if expected is not None:
        expected_edges = segment_edge_multiset(
            polyline_segments(expected.points, closed=True),
            quantum=quantum,
        )
        if best_edges == expected_edges:
            return PerimeterResult(
                points=best_points,
                closed=True,
                edge_count=len(best_edges),
            )
        for _area, points, edges in candidates:
            if edges == expected_edges:
                return PerimeterResult(points=points, closed=True, edge_count=len(edges))
        return None
    return PerimeterResult(points=best_points, closed=True, edge_count=len(best_edges))


__all__ = [
    "CONNECTED_CUT_PATH_ORDER_KEYS",
    "CUT_PATH_INTERNAL_SEQUENCE_KEY",
    "PERIMETER_JOIN_CONNECTED",
    "PERIMETER_JOIN_SEPARATE",
    "POINT_QUANTUM_MM",
    "NetworkComponentDiagnosis",
    "PerimeterNetworkDiagnosis",
    "PerimeterResult",
    "SHEET_PERIMETER_PATH_KEY",
    "coerce_cut_path_sequence_request",
    "connected_cut_path_order_keys",
    "default_cut_path_sequence",
    "diagnose_cut_network",
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
