"""Minimum-trail join of CUT_PATH cutter-center segments.

Joins connected approved cut segments into the fewest continuous trails that
cover each undirected edge exactly once. Virtual edges used only to reason
about odd-degree pairing are never emitted as CNC travel. Near-miss gaps are
never bridged. Failed validation returns the original segments unchanged.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.cnc.operational_file import OperationalFileError
from almdina_erp.almdina_erp.domain.cnc.perimeter import (
    POINT_QUANTUM_MM,
    SHEET_PERIMETER_PATH_KEY,
    edge_sets_equal,
    polyline_segments,
    quantize_point,
    segment_edge_multiset,
    split_segments_at_vertices,
)
from almdina_erp.almdina_erp.domain.cnc.program import direction_invariant_identity


JOIN_CUTTING_PATHS_NO = "no"
JOIN_CUTTING_PATHS_YES = "yes"
JOINED_PATH_KEY_PREFIX = "cut_path:joined:"


@dataclass(frozen=True, slots=True)
class JoinedTrail:
    points: tuple[tuple[float, float], ...]
    closed: bool
    path_key: str
    piece_instance_id: str = ""
    piece_label: str = ""
    ring: str = "open"


@dataclass(frozen=True, slots=True)
class JoinCuttingPathsResult:
    trails: tuple[JoinedTrail, ...]
    joined: bool
    source_edge_count: int
    trail_count: int
    theoretical_minimum: int


def normalize_join_cutting_paths(value: object) -> str:
    token = str(value or "").strip().lower()
    if token in {"", JOIN_CUTTING_PATHS_NO, "0", "false", "off"}:
        return JOIN_CUTTING_PATHS_NO
    if token in {JOIN_CUTTING_PATHS_YES, "1", "true", "on"}:
        return JOIN_CUTTING_PATHS_YES
    raise OperationalFileError("join_cutting_paths_invalid")


def join_cutting_paths_enabled(value: object) -> bool:
    return normalize_join_cutting_paths(value) == JOIN_CUTTING_PATHS_YES


def theoretical_minimum_trails(odd_degree_count: int, *, has_edges: bool) -> int:
    if not has_edges:
        return 0
    if odd_degree_count <= 0:
        return 1
    return odd_degree_count // 2


def _stable_path_key(points: Sequence[tuple[float, float]], *, closed: bool) -> str:
    shape = direction_invariant_identity(tuple(points), closed)
    digest = hashlib.sha1(shape.encode("utf-8")).hexdigest()[:16]
    return f"{JOINED_PATH_KEY_PREFIX}{digest}"


def _components_from_ends(
    ends: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> list[set[tuple[float, float]]]:
    adjacency: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    nodes: set[tuple[float, float]] = set()
    for start, end in ends:
        adjacency[start].add(end)
        adjacency[end].add(start)
        nodes.add(start)
        nodes.add(end)
    remaining = set(nodes)
    components: list[set[tuple[float, float]]] = []
    while remaining:
        origin = min(remaining)
        queue: deque[tuple[float, float]] = deque([origin])
        remaining.remove(origin)
        seen = {origin}
        while queue:
            node = queue.popleft()
            for nxt in adjacency.get(node, ()):
                if nxt in remaining:
                    remaining.remove(nxt)
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(seen)
    components.sort(key=lambda group: (min(group), len(group)))
    return components


def _hierholzer_circuit(
    start: tuple[float, float],
    *,
    adjacency: dict[tuple[float, float], list[int]],
    ends: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    unused: set[int],
) -> list[tuple[tuple[float, float], int | None]]:
    """Return ordered (vertex, inbound_edge) pairs for one Euler circuit.

    ``inbound_edge`` is ``None`` for the start vertex. Virtual edges may appear
    in ``ends`` / ``unused``; callers strip them before emitting CNC trails.
    """

    stack: list[tuple[tuple[float, float], int | None]] = [(start, None)]
    circuit: list[tuple[tuple[float, float], int | None]] = []
    while stack:
        node, inbound = stack[-1]
        choices = [edge for edge in adjacency.get(node, []) if edge in unused]
        if not choices:
            circuit.append(stack.pop())
            continue
        ranked: list[tuple[tuple[float, float], int]] = []
        for edge_index in choices:
            left, right = ends[edge_index]
            other = right if left == node else left
            ranked.append((other, edge_index))
        ranked.sort(key=lambda item: (item[0][0], item[0][1], item[1]))
        other, edge_index = ranked[0]
        unused.remove(edge_index)
        stack.append((other, edge_index))
    circuit.reverse()
    return circuit


def _trail_from_vertices(
    vertices: Sequence[tuple[float, float]],
) -> JoinedTrail | None:
    cleaned: list[tuple[float, float]] = []
    for point in vertices:
        if not cleaned or cleaned[-1] != point:
            cleaned.append(point)
    if len(cleaned) < 2:
        return None
    closed = cleaned[0] == cleaned[-1] and len(cleaned) >= 4
    if closed:
        cleaned = cleaned[:-1]
    points = tuple(cleaned)
    return JoinedTrail(
        points=points,
        closed=closed,
        path_key=_stable_path_key(points, closed=closed),
        ring="outer" if closed else "open",
    )


def _trails_from_euler_circuit(
    circuit: Sequence[tuple[tuple[float, float], int | None]],
    *,
    virtual_edges: set[int],
) -> list[JoinedTrail]:
    """Split an Euler circuit on virtual edges; emit only real CNC trails."""

    trails: list[JoinedTrail] = []
    current: list[tuple[float, float]] = []
    for node, inbound in circuit:
        if inbound is None:
            current = [node]
            continue
        if inbound in virtual_edges:
            trail = _trail_from_vertices(current)
            if trail is not None:
                trails.append(trail)
            current = [node]
            continue
        if not current:
            current = [node]
        else:
            current.append(node)
    trail = _trail_from_vertices(current)
    if trail is not None:
        trails.append(trail)
    return trails


def decompose_minimum_trails(
    segments: Sequence[Sequence[Sequence[float]]],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> JoinCuttingPathsResult:
    """Cover every planarized undirected edge exactly once with minimum trails."""

    if not segments:
        return JoinCuttingPathsResult((), False, 0, 0, 0)
    try:
        planar = split_segments_at_vertices(segments, quantum=quantum)
    except OperationalFileError:
        return JoinCuttingPathsResult((), False, 0, 0, 0)
    if not planar:
        return JoinCuttingPathsResult((), False, 0, 0, 0)

    ends: list[tuple[tuple[float, float], tuple[float, float]]] = []
    adjacency: dict[tuple[float, float], list[int]] = defaultdict(list)
    for index, (start, end) in enumerate(planar):
        left = quantize_point(start, quantum=quantum)
        right = quantize_point(end, quantum=quantum)
        if left == right:
            continue
        ends.append((left, right))
        adjacency[left].append(index)
        adjacency[right].append(index)
    if not ends:
        return JoinCuttingPathsResult((), False, 0, 0, 0)

    real_edge_count = len(ends)
    components = _components_from_ends(ends)
    trails: list[JoinedTrail] = []
    theoretical = 0
    for component in components:
        component_edges = [
            index
            for index, (start, end) in enumerate(ends)
            if start in component and end in component
        ]
        if not component_edges:
            continue
        degrees = {
            node: sum(1 for index in adjacency[node] if index in component_edges)
            for node in component
        }
        odd_nodes = sorted(node for node, degree in degrees.items() if degree % 2 == 1)
        expected = theoretical_minimum_trails(len(odd_nodes), has_edges=True)
        theoretical += expected

        local_adj = {node: [edge for edge in adjacency[node] if edge in component_edges] for node in component}
        local_ends = list(ends)
        virtual_edges: set[int] = set()
        # Deterministic pairing of odd vertices with analysis-only virtual edges.
        for index in range(0, len(odd_nodes) - 1, 2):
            left = odd_nodes[index]
            right = odd_nodes[index + 1]
            edge_index = len(local_ends)
            local_ends.append((left, right))
            local_adj.setdefault(left, []).append(edge_index)
            local_adj.setdefault(right, []).append(edge_index)
            virtual_edges.add(edge_index)

        unused = set(component_edges) | set(virtual_edges)
        start = odd_nodes[0] if odd_nodes else min(component)
        circuit = _hierholzer_circuit(
            start,
            adjacency=local_adj,
            ends=local_ends,
            unused=unused,
        )
        if unused:
            return JoinCuttingPathsResult((), False, real_edge_count, 0, theoretical)
        component_trails = _trails_from_euler_circuit(circuit, virtual_edges=virtual_edges)
        if len(component_trails) != expected:
            return JoinCuttingPathsResult((), False, real_edge_count, 0, theoretical)
        trails.extend(component_trails)

    trails.sort(
        key=lambda trail: (
            0 if trail.closed else 1,
            trail.points[0][0],
            trail.points[0][1],
            trail.points[-1][0],
            trail.points[-1][1],
            trail.path_key,
        )
    )
    if not trails_cover_segments(
        planar,
        [trail.points for trail in trails],
        closed_flags=[trail.closed for trail in trails],
        quantum=quantum,
    ):
        return JoinCuttingPathsResult((), False, real_edge_count, 0, theoretical)
    if theoretical > 0 and len(trails) != theoretical:
        return JoinCuttingPathsResult((), False, real_edge_count, 0, theoretical)
    return JoinCuttingPathsResult(
        trails=tuple(trails),
        joined=True,
        source_edge_count=real_edge_count,
        trail_count=len(trails),
        theoretical_minimum=theoretical,
    )


def trails_cover_segments(
    source_segments: Sequence[Sequence[Sequence[float]]],
    trail_polylines: Sequence[Sequence[Sequence[float]]],
    *,
    closed_flags: Sequence[bool] | None = None,
    quantum: float = POINT_QUANTUM_MM,
) -> bool:
    """True when trails cover exactly the source undirected edge multiset."""

    flags = list(closed_flags or [False] * len(trail_polylines))
    if len(flags) != len(trail_polylines):
        return False
    rebuilt: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for points, closed in zip(trail_polylines, flags, strict=True):
        rebuilt.extend(polyline_segments(points, closed=closed))
    try:
        return edge_sets_equal(source_segments, rebuilt, quantum=quantum)
    except OperationalFileError:
        return False


def trails_are_continuous(
    trails: Sequence[JoinedTrail],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> bool:
    for trail in trails:
        if len(trail.points) < 2:
            return False
        for index in range(len(trail.points) - 1):
            left = quantize_point(trail.points[index], quantum=quantum)
            right = quantize_point(trail.points[index + 1], quantum=quantum)
            if left == right:
                return False
        if trail.closed and len(trail.points) < 3:
            return False
    return True


def join_reduces_or_keeps_path_count(original_count: int, joined_count: int) -> bool:
    if original_count < 0 or joined_count < 0:
        return False
    return joined_count <= original_count


def effective_cut_preset(
    path_key: str,
    *,
    operation_presets: Mapping[str, str] | None = None,
    path_overrides: Mapping[str, str] | None = None,
) -> str:
    overrides = path_overrides or {}
    presets = operation_presets or {}
    key = str(path_key or "").strip()
    if key and str(overrides.get(key) or "").strip():
        return str(overrides.get(key) or "").strip()
    return str(presets.get("cut_path") or "").strip()


def segments_have_real_gap(
    left_end: Sequence[float],
    right_start: Sequence[float],
    *,
    quantum: float = POINT_QUANTUM_MM,
) -> bool:
    """True when endpoints do not coincide under the project join quantum."""

    return quantize_point(left_end, quantum=quantum) != quantize_point(right_start, quantum=quantum)


def join_cut_path_entities(
    entities: Sequence[object],
    *,
    operation_presets: Mapping[str, str] | None = None,
    path_overrides: Mapping[str, str] | None = None,
    quantum: float = POINT_QUANTUM_MM,
) -> tuple[list[object], JoinCuttingPathsResult | None]:
    """Rewrite CUT_PATH tool-center entities into minimum trails when proven.

    Non-cut layers and the connected sheet perimeter entity are preserved.
    Groups that fail geometric validation keep their original entities.
    """

    from almdina_erp.almdina_erp.domain.cnc.program import CncSourceEntity

    kept: list[object] = []
    joinable: list[CncSourceEntity] = []
    for entity in entities:
        if not isinstance(entity, CncSourceEntity):
            kept.append(entity)
            continue
        if entity.layer.upper() != "CUT_PATH" or entity.role != "tool_center":
            kept.append(entity)
            continue
        if str(entity.path_key or "") == SHEET_PERIMETER_PATH_KEY:
            kept.append(entity)
            continue
        joinable.append(entity)
    if len(joinable) <= 1:
        return list(entities), None

    groups: dict[str, list[CncSourceEntity]] = defaultdict(list)
    for entity in joinable:
        preset = effective_cut_preset(
            entity.path_key,
            operation_presets=operation_presets,
            path_overrides=path_overrides,
        )
        groups[preset].append(entity)

    rebuilt: list[object] = list(kept)
    aggregate_trails: list[JoinedTrail] = []
    source_edges = 0
    theoretical = 0
    any_joined = False
    for preset in sorted(groups):
        group = groups[preset]
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for entity in group:
            segments.extend(polyline_segments(entity.points, closed=entity.closed))
        result = decompose_minimum_trails(segments, quantum=quantum)
        if (
            not result.joined
            or not result.trails
            or not trails_are_continuous(result.trails, quantum=quantum)
            or not join_reduces_or_keeps_path_count(len(group), result.trail_count)
        ):
            rebuilt.extend(group)
            continue
        # Preserve single closed source identities when the trail matches one entity.
        source_by_edges = []
        for entity in group:
            source_by_edges.append(
                (
                    entity,
                    segment_edge_multiset(
                        polyline_segments(entity.points, closed=entity.closed),
                        quantum=quantum,
                    ),
                )
            )
        # No geometric reduction — keep stable source identities.
        if result.trail_count == len(group):
            rebuilt.extend(group)
            continue
        for trail in result.trails:
            trail_edges = segment_edge_multiset(
                polyline_segments(trail.points, closed=trail.closed),
                quantum=quantum,
            )
            matched = next(
                (
                    entity
                    for entity, edges in source_by_edges
                    if edges == trail_edges
                ),
                None,
            )
            piece_ids = {
                str(entity.piece_instance_id or "")
                for entity in group
                if segment_edge_multiset(
                    polyline_segments(entity.points, closed=entity.closed),
                    quantum=quantum,
                )
                & trail_edges
            }
            piece_ids.discard("")
            piece_id = next(iter(piece_ids)) if len(piece_ids) == 1 else ""
            label = ""
            ring = trail.ring
            if matched is not None:
                piece_id = matched.piece_instance_id
                label = matched.piece_label
                ring = matched.ring if matched.closed else trail.ring
                path_key = matched.path_key or trail.path_key
            else:
                path_key = trail.path_key
                if piece_id:
                    label = next(
                        (
                            entity.piece_label
                            for entity in group
                            if entity.piece_instance_id == piece_id
                        ),
                        "",
                    )
            rebuilt.append(
                CncSourceEntity(
                    layer="CUT_PATH",
                    points=trail.points,
                    closed=trail.closed,
                    entity_type="LWPOLYLINE" if len(trail.points) > 2 or trail.closed else "LINE",
                    role="tool_center",
                    ring=ring if trail.closed else "open",
                    path_key=path_key,
                    piece_instance_id=piece_id,
                    piece_label=label,
                )
            )
            any_joined = True
            aggregate_trails.append(
                JoinedTrail(
                    points=trail.points,
                    closed=trail.closed,
                    path_key=path_key,
                    piece_instance_id=piece_id,
                    piece_label=label,
                    ring=ring if trail.closed else "open",
                )
            )
        source_edges += result.source_edge_count
        theoretical += result.theoretical_minimum

    if not any_joined:
        return list(entities), None
    summary = JoinCuttingPathsResult(
        trails=tuple(aggregate_trails),
        joined=True,
        source_edge_count=source_edges,
        trail_count=len(aggregate_trails),
        theoretical_minimum=theoretical or len(aggregate_trails),
    )
    return rebuilt, summary


__all__ = [
    "JOINED_PATH_KEY_PREFIX",
    "JOIN_CUTTING_PATHS_NO",
    "JOIN_CUTTING_PATHS_YES",
    "JoinCuttingPathsResult",
    "JoinedTrail",
    "decompose_minimum_trails",
    "effective_cut_preset",
    "join_cut_path_entities",
    "join_cutting_paths_enabled",
    "join_reduces_or_keeps_path_count",
    "normalize_join_cutting_paths",
    "segments_have_real_gap",
    "theoretical_minimum_trails",
    "trails_are_continuous",
    "trails_cover_segments",
]
