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
    # Shape freedom is distinct from manufacturing-envelope freedom. Special
    # pieces may use arbitrary valid polygons, but their bbox must still match
    # the persisted cut dimensions below.
    arbitrary_outline: bool = False


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
) -> tuple[int, ...] | None:
    """Return one expected-piece index per selected contour, if injective.

    Every piece, including Special, is bound to its persisted manufacturing
    envelope. The contour itself may be any valid polygon inside that envelope.
    """
    if len(selected) > len(expected):
        return None

    candidate_indexes: list[list[int]] = []
    for contour in selected:
        matches = [
            index
            for index, expected_piece in enumerate(expected)
            if _dimensions_match(
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