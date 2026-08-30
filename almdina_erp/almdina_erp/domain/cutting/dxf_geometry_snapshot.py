from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry

GEOMETRY_SCHEMA_VERSION = 1
GEOMETRY_UNIT = "mm"
GEOMETRY_COORDINATE_SPACE = "usable_sheet"


class DxfGeometrySnapshotError(ValueError):
    """Raised when persisted DXF topology cannot be trusted."""


def _number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DxfGeometrySnapshotError(f"{field} must contain numeric coordinates.")
    number = float(value)
    if not math.isfinite(number):
        raise DxfGeometrySnapshotError(f"{field} contains a non-finite coordinate.")
    return number


def _polygon(value: Any, *, field: str) -> tuple[tuple[float, float], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) < 3:
        raise DxfGeometrySnapshotError(f"{field} must contain at least three points.")

    points: list[tuple[float, float]] = []
    for index, point in enumerate(value):
        if isinstance(point, (str, bytes)) or not isinstance(point, Sequence) or len(point) != 2:
            raise DxfGeometrySnapshotError(f"{field}[{index}] must be an [x, y] point.")
        points.append(
            (
                _number(point[0], field=f"{field}[{index}][0]"),
                _number(point[1], field=f"{field}[{index}][1]"),
            )
        )
    return tuple(points)


def serialize_geometry_mm(geometry: PartGeometry) -> dict[str, Any]:
    """Serialize plan-local material topology using one versioned public contract.

    Coordinates are millimetres in the usable-sheet coordinate space: origin at
    the usable sheet's top-left, x grows right, y grows down. This is the same
    coordinate system used by persisted Cutting Plan x/y values.
    """

    return {
        "schema_version": GEOMETRY_SCHEMA_VERSION,
        "unit": GEOMETRY_UNIT,
        "coordinate_space": GEOMETRY_COORDINATE_SPACE,
        "outer": [[float(x), float(y)] for x, y in geometry.outer],
        "holes": [
            [[float(x), float(y)] for x, y in hole]
            for hole in geometry.holes
        ],
    }


def serialize_geometry_from_cm(geometry: PartGeometry) -> dict[str, Any]:
    """Serialize plan-local centimetre geometry as the canonical mm contract."""

    return serialize_geometry_mm(
        PartGeometry(
            outer=tuple((x * 10.0, y * 10.0) for x, y in geometry.outer),
            holes=tuple(
                tuple((x * 10.0, y * 10.0) for x, y in hole)
                for hole in geometry.holes
            ),
        )
    )


def parse_geometry_mm(value: Any) -> PartGeometry:
    """Parse persisted geometry, failing closed on any unsupported contract."""

    if not isinstance(value, Mapping):
        raise DxfGeometrySnapshotError("geometry must be an object.")
    if value.get("schema_version") != GEOMETRY_SCHEMA_VERSION:
        raise DxfGeometrySnapshotError("geometry schema_version is unsupported.")
    if value.get("unit") != GEOMETRY_UNIT:
        raise DxfGeometrySnapshotError("geometry unit must be mm.")
    if value.get("coordinate_space") != GEOMETRY_COORDINATE_SPACE:
        raise DxfGeometrySnapshotError("geometry coordinate_space is unsupported.")

    holes_value = value.get("holes", [])
    if isinstance(holes_value, (str, bytes)) or not isinstance(holes_value, Sequence):
        raise DxfGeometrySnapshotError("geometry.holes must be an array.")

    return PartGeometry(
        outer=_polygon(value.get("outer"), field="geometry.outer"),
        holes=tuple(
            _polygon(hole, field=f"geometry.holes[{index}]")
            for index, hole in enumerate(holes_value)
        ),
    )


def geometry_mm_to_cm(geometry: PartGeometry) -> PartGeometry:
    return PartGeometry(
        outer=tuple((x / 10.0, y / 10.0) for x, y in geometry.outer),
        holes=tuple(
            tuple((x / 10.0, y / 10.0) for x, y in hole)
            for hole in geometry.holes
        ),
    )


def canonicalize_snapshot_geometries(value: Any) -> Any:
    """Validate and canonicalize every public ``geometry`` object in a snapshot."""

    if isinstance(value, Mapping):
        normalized = dict(value)
        if "geometry" in normalized:
            normalized["geometry"] = serialize_geometry_mm(parse_geometry_mm(normalized["geometry"]))
        return {
            key: canonicalize_snapshot_geometries(item)
            for key, item in normalized.items()
        }
    if isinstance(value, list):
        return [canonicalize_snapshot_geometries(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize_snapshot_geometries(item) for item in value]
    return value


__all__ = [
    "DxfGeometrySnapshotError",
    "GEOMETRY_COORDINATE_SPACE",
    "GEOMETRY_SCHEMA_VERSION",
    "GEOMETRY_UNIT",
    "canonicalize_snapshot_geometries",
    "geometry_mm_to_cm",
    "parse_geometry_mm",
    "serialize_geometry_from_cm",
    "serialize_geometry_mm",
]
