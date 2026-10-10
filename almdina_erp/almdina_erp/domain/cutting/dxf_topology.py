from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .dxf_geometry import (
    EPSILON,
    bbox,
    point_in_polygon,
    polygon_distance,
    polygons_overlap,
    validate_polygon,
)
from .piece_cut_dimensions import dimensions_match_exact

Point = tuple[float, float]
Polygon = tuple[Point, ...]


@dataclass(frozen=True, slots=True)
class ForbiddenRotationEvidence:
    """A minimum, globally feasible set of confirmed forbidden rotations."""

    rotation_count: int
    source_piece_nos: tuple[int, ...]
    measurements_mm: tuple[tuple[float, float, float, float], ...]
    expected_piece_index: int | None = None


class DxfTopologyError(ValueError):
    """Deterministic, framework-free DXF topology failure."""

    def __init__(
        self,
        code: str,
        *,
        first_key: str | int | None = None,
        second_key: str | int | None = None,
        expected_piece_index: int | None = None,
        expected_width: float | None = None,
        expected_height: float | None = None,
        actual_width: float | None = None,
        actual_height: float | None = None,
        rotation_evidence: Sequence[ForbiddenRotationEvidence] = (),
    ) -> None:
        self.code = code
        self.first_key = first_key
        self.second_key = second_key
        self.expected_piece_index = expected_piece_index
        self.expected_width = expected_width
        self.expected_height = expected_height
        self.actual_width = actual_width
        self.actual_height = actual_height
        self.rotation_evidence = tuple(rotation_evidence)
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ContourCandidate:
    key: int
    polygon: Polygon


@dataclass(frozen=True, slots=True)
class ExpectedPieceEvidence:
    width: float
    height: float
    allow_rotation: bool
    # Shape freedom is distinct from manufacturing-envelope freedom. Special
    # pieces may use arbitrary valid polygons, but their bbox must still match
    # the persisted cut dimensions below.
    arbitrary_outline: bool = False
    source_piece_no: int | None = None
    copy_no: int | None = None


@dataclass(frozen=True, slots=True)
class PartGeometry:
    outer: Polygon
    holes: tuple[Polygon, ...] = ()


@dataclass(frozen=True, slots=True)
class PlacedPartGeometry:
    key: str | int
    geometry: PartGeometry


@dataclass(frozen=True, slots=True)
class ResolvedPartGeometry:
    contour_key: int
    geometry: PartGeometry
    hole_contour_keys: tuple[int, ...] = ()
    expected_piece_index: int | None = None


@dataclass(frozen=True, slots=True)
class ResolvedTopology:
    parts: tuple[ResolvedPartGeometry, ...]

    @property
    def actual_contour_keys(self) -> tuple[int, ...]:
        return tuple(part.contour_key for part in self.parts)

    @property
    def hole_contour_keys(self) -> tuple[int, ...]:
        return tuple(
            hole_key
            for part in self.parts
            for hole_key in part.hole_contour_keys
        )


def _open_ring(points: Sequence[Point]) -> Polygon:
    polygon = tuple((float(x), float(y)) for x, y in points)
    if len(polygon) > 1 and polygon[0] == polygon[-1]:
        polygon = polygon[:-1]
    return polygon


def _canonical_ring(points: Sequence[Point]) -> Polygon:
    polygon = _open_ring(points)
    if not polygon:
        return ()
    forward = [polygon[index:] + polygon[:index] for index in range(len(polygon))]
    reversed_polygon = tuple(reversed(polygon))
    backward = [
        reversed_polygon[index:] + reversed_polygon[:index]
        for index in range(len(reversed_polygon))
    ]
    return min((*forward, *backward))


def _contour_sort_key(contour: ContourCandidate) -> tuple[object, ...]:
    min_x, min_y, max_x, max_y = bbox(contour.polygon)
    return (min_x, min_y, max_x, max_y, _canonical_ring(contour.polygon))


def polygon_contains_polygon(
    container: Sequence[Point],
    nested: Sequence[Point],
    *,
    tolerance: float = EPSILON,
) -> bool:
    """Return True when the nested polygon lies wholly inside, including boundary contact."""
    outer = _open_ring(container)
    inner = _open_ring(nested)
    if len(outer) < 3 or len(inner) < 3:
        return False
    return all(point_in_polygon(point, outer, tolerance) for point in inner)


def polygon_strictly_contains_polygon(
    container: Sequence[Point],
    nested: Sequence[Point],
    *,
    tolerance: float = EPSILON,
) -> bool:
    """Return True only when the nested polygon is wholly inside with no boundary touch."""
    outer = _open_ring(container)
    inner = _open_ring(nested)
    if len(outer) < 3 or len(inner) < 3:
        return False
    if not polygon_contains_polygon(outer, inner, tolerance=tolerance):
        return False
    return polygon_distance(outer, inner, tolerance) > tolerance


def containing_hole(
    owner: PartGeometry,
    nested_outer: Sequence[Point],
    *,
    tolerance: float = EPSILON,
) -> Polygon | None:
    matches = tuple(
        hole
        for hole in owner.holes
        if polygon_strictly_contains_polygon(hole, nested_outer, tolerance=tolerance)
    )
    if len(matches) == 1:
        return matches[0]
    return None


def material_footprints_overlap(
    first: PartGeometry,
    second: PartGeometry,
    *,
    tolerance: float = EPSILON,
) -> bool:
    """Return whether the two MDF material footprints overlap.

    A part nested wholly inside exactly one owned hole does not collide with the
    hole owner because the owner's material is ``outer - holes``. Ordinary solid
    containment remains an overlap.
    """
    if not polygons_overlap(first.outer, second.outer, tolerance=tolerance):
        return False
    if containing_hole(first, second.outer, tolerance=tolerance) is not None:
        return False
    if containing_hole(second, first.outer, tolerance=tolerance) is not None:
        return False
    return True


def validate_material_layout(
    parts: Sequence[PlacedPartGeometry],
    *,
    required_clearance: float,
    geometry_tolerance: float = EPSILON,
    numeric_tolerance: float = 0.0,
) -> None:
    """Validate MDF collision and canonical pairwise/hole-boundary clearance."""
    clearance = max(0.0, float(required_clearance))
    ordered = tuple(sorted(parts, key=lambda part: str(part.key)))
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            if material_footprints_overlap(
                first.geometry,
                second.geometry,
                tolerance=geometry_tolerance,
            ):
                raise DxfTopologyError(
                    "MATERIAL_FOOTPRINT_OVERLAP",
                    first_key=first.key,
                    second_key=second.key,
                )

            first_hole = containing_hole(
                first.geometry,
                second.geometry.outer,
                tolerance=geometry_tolerance,
            )
            second_hole = containing_hole(
                second.geometry,
                first.geometry.outer,
                tolerance=geometry_tolerance,
            )
            if first_hole is not None:
                distance = polygon_distance(
                    first_hole,
                    second.geometry.outer,
                    geometry_tolerance,
                )
                violation_code = "HOLE_CLEARANCE_VIOLATION"
            elif second_hole is not None:
                distance = polygon_distance(
                    second_hole,
                    first.geometry.outer,
                    geometry_tolerance,
                )
                violation_code = "HOLE_CLEARANCE_VIOLATION"
            else:
                distance = polygon_distance(
                    first.geometry.outer,
                    second.geometry.outer,
                    geometry_tolerance,
                )
                violation_code = "PART_CLEARANCE_VIOLATION"

            if distance + numeric_tolerance < clearance:
                raise DxfTopologyError(
                    violation_code,
                    first_key=first.key,
                    second_key=second.key,
                )


def _dimensions_match(
    contour: ContourCandidate,
    expected: ExpectedPieceEvidence,
    *,
    dimension_tolerance: float,
) -> bool:
    min_x, min_y, max_x, max_y = bbox(contour.polygon)
    width = max_x - min_x
    height = max_y - min_y
    direct = (
        abs(width - expected.width) <= dimension_tolerance
        and abs(height - expected.height) <= dimension_tolerance
    )
    if direct:
        return True
    return bool(
        expected.allow_rotation
        and abs(width - expected.height) <= dimension_tolerance
        and abs(height - expected.width) <= dimension_tolerance
    )


def _matches_any_expected(
    contour: ContourCandidate,
    expected: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
) -> bool:
    return any(
        _dimensions_match(
            contour,
            expected_piece,
            dimension_tolerance=dimension_tolerance,
        )
        for expected_piece in expected
    )


def _inventory_assignment(
    selected: Sequence[ContourCandidate],
    expected: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
    excluded_edge: tuple[int, int] | None = None,
) -> tuple[int, ...] | None:
    """Return one expected-piece index per selected contour, if injective.

    Every piece, including Special, is bound to its persisted manufacturing
    envelope. The contour itself may be any valid polygon inside that envelope.
    """
    if len(selected) > len(expected):
        return None

    candidate_indexes: list[list[int]] = []
    for contour_index, contour in enumerate(selected):
        matches = [
            index
            for index, expected_piece in enumerate(expected)
            if (contour_index, index) != excluded_edge and _dimensions_match(
                contour,
                expected_piece,
                dimension_tolerance=dimension_tolerance,
            )
        ]
        if not matches:
            return None
        candidate_indexes.append(matches)

    expected_owner: dict[int, int] = {}

    def assign(contour_index: int, visited: set[int]) -> bool:
        for expected_index in candidate_indexes[contour_index]:
            if expected_index in visited:
                continue
            visited.add(expected_index)
            previous_contour = expected_owner.get(expected_index)
            if previous_contour is None or assign(previous_contour, visited):
                expected_owner[expected_index] = contour_index
                return True
        return False

    order = sorted(
        range(len(selected)),
        key=lambda index: (len(candidate_indexes[index]), index),
    )
    if not all(assign(contour_index, set()) for contour_index in order):
        return None

    contour_to_expected = {
        contour_index: expected_index
        for expected_index, contour_index in expected_owner.items()
    }
    return tuple(contour_to_expected[index] for index in range(len(selected)))


def _minimum_cost_assignment(
    costs: Sequence[Sequence[int | None]],
) -> tuple[int, tuple[int, ...], tuple[int, ...], tuple[int, ...]] | None:
    """Find a deterministic minimum-cost perfect matching in O(n^3)."""
    size = len(costs)
    if any(len(row) != size for row in costs):
        return None
    if size == 0:
        return 0, (), (), ()

    infinity = 10**12
    row_potential = [0] * (size + 1)
    column_potential = [0] * (size + 1)
    column_owner = [0] * (size + 1)
    previous_column = [0] * (size + 1)

    for row_number in range(1, size + 1):
        column_owner[0] = row_number
        current_column = 0
        best_slack = [infinity] * (size + 1)
        visited_columns = [False] * (size + 1)
        while True:
            visited_columns[current_column] = True
            current_row = column_owner[current_column]
            delta = infinity
            next_column = 0
            for column_number in range(1, size + 1):
                if visited_columns[column_number]:
                    continue
                cost = costs[current_row - 1][column_number - 1]
                if cost is not None:
                    reduced_cost = (
                        cost
                        - row_potential[current_row]
                        - column_potential[column_number]
                    )
                    if reduced_cost < best_slack[column_number]:
                        best_slack[column_number] = reduced_cost
                        previous_column[column_number] = current_column
                if best_slack[column_number] < delta:
                    delta = best_slack[column_number]
                    next_column = column_number
            if delta == infinity:
                return None
            for column_number in range(size + 1):
                if visited_columns[column_number]:
                    row_potential[column_owner[column_number]] += delta
                    column_potential[column_number] -= delta
                else:
                    best_slack[column_number] -= delta
            current_column = next_column
            if column_owner[current_column] == 0:
                break

        while True:
            prior_column = previous_column[current_column]
            column_owner[current_column] = column_owner[prior_column]
            current_column = prior_column
            if current_column == 0:
                break

    assignment = [-1] * size
    for column_number in range(1, size + 1):
        assignment[column_owner[column_number] - 1] = column_number - 1
    if any(column < 0 for column in assignment):
        return None
    if any(costs[row][column] is None for row, column in enumerate(assignment)):
        return None
    total = sum(costs[row][column] for row, column in enumerate(assignment))
    return total, tuple(assignment), tuple(row_potential), tuple(column_potential)


def _strong_components(graph: Sequence[Sequence[int]]) -> tuple[int, ...]:
    """Return strongly connected component IDs using iterative Kosaraju traversal."""
    reverse_graph: list[list[int]] = [[] for _ in graph]
    for node, neighbours in enumerate(graph):
        for neighbour in neighbours:
            reverse_graph[neighbour].append(node)

    visited: set[int] = set()
    finishing_order: list[int] = []
    for start in range(len(graph)):
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, 0)]
        while stack:
            node, offset = stack[-1]
            if offset < len(graph[node]):
                neighbour = graph[node][offset]
                stack[-1] = (node, offset + 1)
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append((neighbour, 0))
            else:
                finishing_order.append(node)
                stack.pop()

    component_ids = [-1] * len(graph)
    component_id = 0
    for start in reversed(finishing_order):
        if component_ids[start] != -1:
            continue
        component_ids[start] = component_id
        stack = [start]
        while stack:
            node = stack.pop()
            for neighbour in reverse_graph[node]:
                if component_ids[neighbour] == -1:
                    component_ids[neighbour] = component_id
                    stack.append(neighbour)
        component_id += 1
    return tuple(component_ids)


def _optimal_assignment_edges(
    costs: Sequence[Sequence[int | None]],
    assignment: Sequence[int],
    row_potential: Sequence[int],
    column_potential: Sequence[int],
) -> tuple[set[tuple[int, int]], tuple[int, ...]]:
    """Return edges participating in any minimum-cost perfect matching."""
    size = len(costs)
    graph: list[list[int]] = [[] for _ in range(size * 2)]
    tight_edges: set[tuple[int, int]] = set()
    for row in range(size):
        for column in range(size):
            cost = costs[row][column]
            if cost is None:
                continue
            if cost == row_potential[row + 1] + column_potential[column + 1]:
                tight_edges.add((row, column))
                if assignment[row] == column:
                    graph[size + column].append(row)
                else:
                    graph[row].append(size + column)

    component_ids = _strong_components(graph)
    possible_edges = {
        (row, column)
        for row, column in tight_edges
        if assignment[row] == column
        or component_ids[row] == component_ids[size + column]
    }
    return possible_edges, component_ids


def _matching_components(
    size: int,
    possible_edges: set[tuple[int, int]],
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Partition the optimal-edge graph into independent matching components."""
    graph: list[list[int]] = [[] for _ in range(size * 2)]
    for row, column in possible_edges:
        contour_node = size + column
        graph[row].append(contour_node)
        graph[contour_node].append(row)

    visited: set[int] = set()
    components = []
    for start, neighbours in enumerate(graph):
        if start in visited or not neighbours:
            continue
        visited.add(start)
        stack = [start]
        nodes = []
        while stack:
            node = stack.pop()
            nodes.append(node)
            for neighbour in graph[node]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(neighbour)
        rows = tuple(sorted(node for node in nodes if node < size))
        contours = tuple(sorted(node - size for node in nodes if node >= size))
        components.append((rows, contours))
    return tuple(sorted(components, key=lambda item: item[0][0] if item[0] else size))


def _forbidden_rotation_error(
    contours: Sequence[ContourCandidate],
    expected: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
) -> DxfTopologyError | None:
    """Diagnose the minimum forbidden rotations across all feasible assignments.

    The minimum-cost bipartite matching separates the existence and count of
    rotation violations from the identity of interchangeable copies. Tight-edge
    components identify which assignments are equally valid; only edges that
    occur in every optimum retain individual copy identity.
    """
    relaxed = tuple(
        ExpectedPieceEvidence(
            width=piece.width,
            height=piece.height,
            allow_rotation=True,
            arbitrary_outline=piece.arbitrary_outline,
            source_piece_no=piece.source_piece_no,
            copy_no=piece.copy_no,
        )
        for piece in expected
    )
    candidates = tuple(
        contour
        for contour in contours
        if _matches_any_expected(
            contour,
            relaxed,
            dimension_tolerance=dimension_tolerance,
        )
    )
    size = len(expected)
    if len(candidates) != size or size == 0:
        return None

    costs: list[list[int | None]] = []
    measurements: dict[tuple[int, int], tuple[float, float, float, float]] = {}
    for piece in expected:
        row_costs: list[int | None] = []
        direct_piece = ExpectedPieceEvidence(
            width=piece.width,
            height=piece.height,
            allow_rotation=False,
            arbitrary_outline=piece.arbitrary_outline,
            source_piece_no=piece.source_piece_no,
            copy_no=piece.copy_no,
        )
        for contour_index, contour in enumerate(candidates):
            if _dimensions_match(
                contour,
                direct_piece,
                dimension_tolerance=dimension_tolerance,
            ):
                row_costs.append(0)
                continue

            min_x, min_y, max_x, max_y = bbox(contour.polygon)
            actual_width = max_x - min_x
            actual_height = max_y - min_y
            actual_width_cm = actual_width / 10.0
            actual_height_cm = actual_height / 10.0
            expected_width_cm = piece.width / 10.0
            expected_height_cm = piece.height / 10.0
            exact_rotated = dimensions_match_exact(
                actual_width_cm,
                actual_height_cm,
                expected_height_cm,
                expected_width_cm,
            )
            if piece.allow_rotation and _dimensions_match(
                contour,
                piece,
                dimension_tolerance=dimension_tolerance,
            ):
                row_costs.append(0)
            elif exact_rotated and not piece.arbitrary_outline:
                row_costs.append(1)
                measurements[(len(costs), contour_index)] = (
                    actual_width,
                    actual_height,
                    piece.width,
                    piece.height,
                )
            else:
                row_costs.append(None)
        costs.append(row_costs)

    solved = _minimum_cost_assignment(costs)
    if solved is None:
        return None
    minimum_rotations, assignment, row_potential, column_potential = solved
    if minimum_rotations <= 0:
        return None

    possible_edges, component_ids = _optimal_assignment_edges(
        costs,
        assignment,
        row_potential,
        column_potential,
    )
    evidence: list[ForbiddenRotationEvidence] = []
    for expected_indexes, contour_indexes in _matching_components(size, possible_edges):
        chosen_rotations = [
            (row, assignment[row])
            for row in expected_indexes
            if costs[row][assignment[row]] == 1
        ]
        if not chosen_rotations:
            continue

        forced_rotations = [
            (row, column)
            for row, column in chosen_rotations
            if component_ids[row] != component_ids[size + column]
        ]
        for row, column in forced_rotations:
            measurement = measurements[(row, column)]
            source_piece_no = expected[row].source_piece_no
            evidence.append(
                ForbiddenRotationEvidence(
                    rotation_count=1,
                    source_piece_nos=(source_piece_no,) if source_piece_no is not None else (),
                    measurements_mm=(measurement,),
                    expected_piece_index=row,
                )
            )

        remaining_count = len(chosen_rotations) - len(forced_rotations)
        if remaining_count <= 0:
            continue
        forced_edges = set(forced_rotations)
        possible_rotation_edges = [
            (row, column)
            for row in expected_indexes
            for column in contour_indexes
            if (row, column) in possible_edges
            and costs[row][column] == 1
            and (row, column) not in forced_edges
        ]
        source_piece_nos = tuple(sorted({
            int(expected[row].source_piece_no)
            for row, _column in possible_rotation_edges
            if expected[row].source_piece_no is not None
        }))
        possible_measurements = tuple(sorted({
            measurements[(row, column)]
            for row, column in possible_rotation_edges
        }))
        evidence.append(
            ForbiddenRotationEvidence(
                rotation_count=remaining_count,
                source_piece_nos=source_piece_nos,
                measurements_mm=possible_measurements,
            )
        )

    if not evidence or sum(item.rotation_count for item in evidence) != minimum_rotations:
        return None

    only = evidence[0] if len(evidence) == 1 else None
    only_measurement = only.measurements_mm[0] if only and len(only.measurements_mm) == 1 else None
    return DxfTopologyError(
        "FORBIDDEN_ROTATION",
        expected_piece_index=only.expected_piece_index if only else None,
        actual_width=only_measurement[0] if only_measurement else None,
        actual_height=only_measurement[1] if only_measurement else None,
        expected_width=only_measurement[2] if only_measurement else None,
        expected_height=only_measurement[3] if only_measurement else None,
        rotation_evidence=evidence,
    )


def _root_contours(
    contours: Sequence[ContourCandidate],
    *,
    geometry_tolerance: float,
) -> tuple[ContourCandidate, ...]:
    """Return contours that cannot structurally be holes of another contour."""
    return tuple(
        contour
        for contour in contours
        if not any(
            owner.key != contour.key
            and polygon_strictly_contains_polygon(
                owner.polygon,
                contour.polygon,
                tolerance=geometry_tolerance,
            )
            for owner in contours
        )
    )


def _validate_part_topology(
    geometry: PartGeometry,
    *,
    tolerance: float,
) -> bool:
    if validate_polygon(geometry.outer, tolerance):
        return False
    for hole in geometry.holes:
        if validate_polygon(hole, tolerance):
            return False
        if not polygon_strictly_contains_polygon(
            geometry.outer,
            hole,
            tolerance=tolerance,
        ):
            return False
    for index, first in enumerate(geometry.holes):
        for second in geometry.holes[index + 1 :]:
            if polygons_overlap(first, second, tolerance=tolerance):
                return False
            if polygon_distance(first, second, tolerance) <= tolerance:
                return False
    return True


def _classify_selection(
    selected: Sequence[ContourCandidate],
    leftovers: Sequence[ContourCandidate],
    *,
    geometry_tolerance: float,
    expected_piece_indexes: dict[int, int],
) -> ResolvedTopology | None:
    """Attach each proven hole to exactly one selected outer contour.

    This function resolves structural ownership only. Material overlap and Kerf
    remain a separate domain validation step so classification never hides a
    placement error behind a generic ownership failure.
    """
    holes_by_owner: dict[int, list[ContourCandidate]] = {
        contour.key: [] for contour in selected
    }
    for hole in leftovers:
        owners = [
            owner
            for owner in selected
            if polygon_strictly_contains_polygon(
                owner.polygon,
                hole.polygon,
                tolerance=geometry_tolerance,
            )
        ]
        if len(owners) != 1:
            return None
        holes_by_owner[owners[0].key].append(hole)

    parts: list[ResolvedPartGeometry] = []
    for contour in selected:
        owned_holes = sorted(
            holes_by_owner[contour.key],
            key=_contour_sort_key,
        )
        geometry = PartGeometry(
            outer=_open_ring(contour.polygon),
            holes=tuple(_open_ring(hole.polygon) for hole in owned_holes),
        )
        if not _validate_part_topology(
            geometry,
            tolerance=geometry_tolerance,
        ):
            return None
        parts.append(
            ResolvedPartGeometry(
                contour_key=contour.key,
                geometry=geometry,
                hole_contour_keys=tuple(hole.key for hole in owned_holes),
                expected_piece_index=expected_piece_indexes.get(contour.key),
            )
        )

    # Keep the original CUT_PATH contour order for downstream piece IDs/labels.
    # Ownership itself does not depend on this order; it is only a compatibility
    # guarantee for existing no-hole DXF snapshots and equal-dimension pieces.
    return ResolvedTopology(parts=tuple(sorted(parts, key=lambda part: part.contour_key)))


def diagnostic_piece_contours(
    contours: Sequence[ContourCandidate],
    expected_pieces: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
    geometry_tolerance: float = EPSILON,
    include_nested_piece_candidates: bool = True,
) -> tuple[ContourCandidate, ...]:
    """Return contours with the same piece evidence used by topology resolution.

    This inventory view is diagnostic only. It does not accept or reject a DXF;
    it excludes structural holes while retaining nested contours whose dimensions
    prove they may be independent pieces.
    """
    ordered = tuple(sorted(contours, key=_contour_sort_key))
    roots = _root_contours(ordered, geometry_tolerance=geometry_tolerance)
    if not include_nested_piece_candidates:
        return roots
    root_keys = {contour.key for contour in roots}
    selected_keys = root_keys | {
        contour.key
        for contour in ordered
        if _matches_any_expected(
            contour,
            expected_pieces,
            dimension_tolerance=dimension_tolerance,
        )
    }
    return tuple(contour for contour in ordered if contour.key in selected_keys)


def resolve_contour_ownership(
    contours: Sequence[ContourCandidate],
    expected_pieces: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
    geometry_tolerance: float = EPSILON,
) -> ResolvedTopology:
    """Resolve actual DCO contours and owned holes from expected-piece evidence.

    The decision is deterministic and intentionally fail-closed:

    * a contour not contained by another contour must be an actual piece;
    * every actual piece, including Special, must match the persisted cut-width
      and cut-length envelope (or its allowed rotation);
    * a Special outer may still be concave or otherwise non-rectangular as long
      as its valid polygon has the required manufacturing bounding box;
    * a nested contour matching expected piece dimensions remains an actual piece
      candidate (supporting pieces placed inside proven holes);
    * a nested contour without piece evidence can be considered a hole only when
      it is strictly contained by exactly one selected outer contour;
    * if there are more piece-like contours than expected pieces, ownership is
      ambiguous and the DXF is rejected instead of guessing from contour order,
      nesting parity, or size.

    This avoids combinatorial contour-subset searches on plans with many internal
    openings while preserving exact order-piece identity as the source of truth.
    """
    ordered_contours = tuple(sorted(contours, key=_contour_sort_key))
    expected = tuple(expected_pieces)
    if len(ordered_contours) < len(expected):
        raise DxfTopologyError("EXPECTED_PIECE_MISMATCH")
    if not expected:
        if ordered_contours:
            raise DxfTopologyError("UNRESOLVED_CONTOUR_OWNERSHIP")
        return ResolvedTopology(parts=())

    roots = _root_contours(
        ordered_contours,
        geometry_tolerance=geometry_tolerance,
    )
    dimension_candidates = tuple(
        contour
        for contour in ordered_contours
        if _matches_any_expected(
            contour,
            expected,
            dimension_tolerance=dimension_tolerance,
        )
    )
    selected_keys = {
        contour.key for contour in (*roots, *dimension_candidates)
    }
    selected = tuple(
        contour for contour in ordered_contours if contour.key in selected_keys
    )
    leftovers = tuple(
        contour for contour in ordered_contours if contour.key not in selected_keys
    )

    if len(selected) < len(expected):
        diagnostic = _forbidden_rotation_error(
            ordered_contours, expected,
            dimension_tolerance=dimension_tolerance,
        )
        if diagnostic is not None:
            raise diagnostic
        raise DxfTopologyError("EXPECTED_PIECE_MISMATCH")
    if len(selected) > len(expected):
        if _inventory_assignment(
            roots,
            expected,
            dimension_tolerance=dimension_tolerance,
        ) is None:
            raise DxfTopologyError("UNRESOLVED_CONTOUR_OWNERSHIP")
        raise DxfTopologyError("AMBIGUOUS_CONTOUR_OWNERSHIP")
    assignment = _inventory_assignment(
        selected,
        expected,
        dimension_tolerance=dimension_tolerance,
    )
    if assignment is None:
        diagnostic = _forbidden_rotation_error(
            ordered_contours, expected,
            dimension_tolerance=dimension_tolerance,
        )
        if diagnostic is not None:
            raise diagnostic
        raise DxfTopologyError("EXPECTED_PIECE_MISMATCH")

    topology = _classify_selection(
        selected,
        leftovers,
        geometry_tolerance=geometry_tolerance,
        expected_piece_indexes={
            contour.key: assignment[index]
            for index, contour in enumerate(selected)
        },
    )
    if topology is None:
        raise DxfTopologyError(
            "UNRESOLVED_CONTOUR_OWNERSHIP" if leftovers else "INVALID_PART_TOPOLOGY"
        )
    return topology


__all__ = [
    "ContourCandidate",
    "DxfTopologyError",
    "ExpectedPieceEvidence",
    "PartGeometry",
    "PlacedPartGeometry",
    "ResolvedPartGeometry",
    "ResolvedTopology",
    "containing_hole",
    "diagnostic_piece_contours",
    "material_footprints_overlap",
    "polygon_contains_polygon",
    "polygon_strictly_contains_polygon",
    "resolve_contour_ownership",
    "validate_material_layout",
]
