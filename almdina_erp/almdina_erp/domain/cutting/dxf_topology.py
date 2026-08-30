from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from .dxf_geometry import (
    EPSILON,
    bbox,
    point_in_polygon,
    polygon_distance,
    polygons_overlap,
    validate_polygon,
)

Point = tuple[float, float]
Polygon = tuple[Point, ...]


class DxfTopologyError(ValueError):
    """Deterministic, framework-free DXF topology failure."""

    def __init__(
        self,
        code: str,
        *,
        first_key: str | int | None = None,
        second_key: str | int | None = None,
    ) -> None:
        self.code = code
        self.first_key = first_key
        self.second_key = second_key
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
    if not all(point_in_polygon(point, outer, tolerance) for point in inner):
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
    """Collision of MDF material, preserving ordinary solid containment as overlap."""
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


def _inventory_can_match(
    selected: Sequence[ContourCandidate],
    expected: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
) -> bool:
    if len(selected) != len(expected):
        return False

    candidate_indexes: list[list[int]] = []
    for expected_piece in expected:
        matches = [
            index
            for index, contour in enumerate(selected)
            if _dimensions_match(
                contour,
                expected_piece,
                dimension_tolerance=dimension_tolerance,
            )
        ]
        if not matches:
            return False
        candidate_indexes.append(matches)

    contour_owner: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for contour_index in candidate_indexes[expected_index]:
            if contour_index in visited:
                continue
            visited.add(contour_index)
            previous_expected = contour_owner.get(contour_index)
            if previous_expected is None or assign(previous_expected, visited):
                contour_owner[contour_index] = expected_index
                return True
        return False

    order = sorted(
        range(len(expected)),
        key=lambda index: (len(candidate_indexes[index]), index),
    )
    return all(assign(expected_index, set()) for expected_index in order)


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
) -> ResolvedTopology | None:
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
            )
        )

    try:
        validate_material_layout(
            tuple(
                PlacedPartGeometry(key=part.contour_key, geometry=part.geometry)
                for part in parts
            ),
            required_clearance=0.0,
            geometry_tolerance=geometry_tolerance,
        )
    except DxfTopologyError:
        return None

    return ResolvedTopology(
        parts=tuple(sorted(parts, key=lambda part: _contour_sort_key(
            next(contour for contour in selected if contour.key == part.contour_key)
        )))
    )


def resolve_contour_ownership(
    contours: Sequence[ContourCandidate],
    expected_pieces: Sequence[ExpectedPieceEvidence],
    *,
    dimension_tolerance: float,
    geometry_tolerance: float = EPSILON,
) -> ResolvedTopology:
    """Resolve actual DCO contours and owned holes from expected-piece evidence.

    Extra closed contours are never assumed to be holes. The resolver accepts a
    classification only when the expected DCO inventory can be matched exactly,
    every remaining contour has exactly one proven owner, and the resulting MDF
    material footprints are structurally valid. Multiple valid classifications
    fail closed instead of using contour order, nesting parity, or size guesses.
    """
    ordered_contours = tuple(sorted(contours, key=_contour_sort_key))
    expected = tuple(expected_pieces)
    if len(ordered_contours) < len(expected):
        raise DxfTopologyError("EXPECTED_PIECE_MISMATCH")
    if not expected:
        if ordered_contours:
            raise DxfTopologyError("UNRESOLVED_CONTOUR_OWNERSHIP")
        return ResolvedTopology(parts=())

    extra_count = len(ordered_contours) - len(expected)
    if extra_count <= 0:
        if not _inventory_can_match(
            ordered_contours,
            expected,
            dimension_tolerance=dimension_tolerance,
        ):
            raise DxfTopologyError("EXPECTED_PIECE_MISMATCH")
        topology = _classify_selection(
            ordered_contours,
            (),
            geometry_tolerance=geometry_tolerance,
        )
        if topology is None:
            raise DxfTopologyError("INVALID_PART_TOPOLOGY")
        return topology

    valid: dict[
        tuple[tuple[int, tuple[int, ...]], ...],
        ResolvedTopology,
    ] = {}
    indexes = range(len(ordered_contours))
    for leftover_indexes in combinations(indexes, extra_count):
        leftover_set = frozenset(leftover_indexes)
        selected = tuple(
            contour
            for index, contour in enumerate(ordered_contours)
            if index not in leftover_set
        )
        if not _inventory_can_match(
            selected,
            expected,
            dimension_tolerance=dimension_tolerance,
        ):
            continue
        leftovers = tuple(
            contour
            for index, contour in enumerate(ordered_contours)
            if index in leftover_set
        )
        topology = _classify_selection(
            selected,
            leftovers,
            geometry_tolerance=geometry_tolerance,
        )
        if topology is None:
            continue
        signature = tuple(
            (part.contour_key, tuple(sorted(part.hole_contour_keys)))
            for part in topology.parts
        )
        valid.setdefault(signature, topology)
        if len(valid) > 1:
            raise DxfTopologyError("AMBIGUOUS_CONTOUR_OWNERSHIP")

    if not valid:
        raise DxfTopologyError("UNRESOLVED_CONTOUR_OWNERSHIP")
    return next(iter(valid.values()))


__all__ = [
    "ContourCandidate",
    "DxfTopologyError",
    "ExpectedPieceEvidence",
    "PartGeometry",
    "PlacedPartGeometry",
    "ResolvedPartGeometry",
    "ResolvedTopology",
    "containing_hole",
    "material_footprints_overlap",
    "polygon_strictly_contains_polygon",
    "resolve_contour_ownership",
    "validate_material_layout",
]
