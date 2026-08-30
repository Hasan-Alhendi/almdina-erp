from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    DxfTopologyError,
    PartGeometry,
    PlacedPartGeometry,
    validate_material_layout,
)

GEOMETRY_SCHEMA_VERSION = 1
GEOMETRY_UNIT = "mm"
GEOMETRY_COORDINATE_SPACE = "usable_sheet"
GEOMETRY_TOLERANCE_MM = 0.25
KERF_NUMERIC_TOLERANCE_MM = 0.1


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
    """Validate/canonicalize only ``sheets[*].pieces[*].geometry`` contracts.

    Other snapshot metadata may legitimately use a generic ``geometry`` key for
    unrelated features. This hotfix owns only uploaded-DXF piece topology and
    therefore deliberately avoids interpreting geometry outside placed pieces.
    """

    if not isinstance(value, Mapping):
        return value

    normalized = dict(value)
    sheets = normalized.get("sheets")
    if isinstance(sheets, list):
        normalized_sheets: list[Any] = []
        for sheet in sheets:
            if not isinstance(sheet, Mapping):
                normalized_sheets.append(sheet)
                continue
            normalized_sheet = dict(sheet)
            pieces = normalized_sheet.get("pieces")
            if isinstance(pieces, list):
                normalized_pieces: list[Any] = []
                for piece in pieces:
                    if not isinstance(piece, Mapping):
                        normalized_pieces.append(piece)
                        continue
                    normalized_piece = dict(piece)
                    if "geometry" in normalized_piece:
                        normalized_piece["geometry"] = serialize_geometry_mm(
                            parse_geometry_mm(normalized_piece["geometry"])
                        )
                    normalized_pieces.append(normalized_piece)
                normalized_sheet["pieces"] = normalized_pieces
            normalized_sheets.append(normalized_sheet)
        normalized["sheets"] = normalized_sheets
    return normalized


def snapshot_geometry_index(snapshot: Any) -> tuple[dict[tuple[int, int], dict[str, Any]], bool]:
    """Index canonical piece geometry by ``(sheet_no, piece_id)``.

    A mixed persisted snapshot is intentionally fail-closed: once any piece has
    public geometry, every persisted piece must have it and every identity must be
    unique. Legacy snapshots with no geometry return ``({}, False)``.
    """

    if not isinstance(snapshot, Mapping):
        return {}, False

    rows: list[tuple[int, Mapping[str, Any]]] = []
    has_geometry = False
    for sheet_index, sheet in enumerate(snapshot.get("sheets") or [], start=1):
        if not isinstance(sheet, Mapping):
            raise DxfGeometrySnapshotError("snapshot sheets must be objects.")
        try:
            sheet_no = int(sheet.get("sheet_no") or sheet_index)
        except (TypeError, ValueError) as exc:
            raise DxfGeometrySnapshotError("sheet_no must be an integer.") from exc
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, Mapping):
                raise DxfGeometrySnapshotError("snapshot pieces must be objects.")
            rows.append((sheet_no, piece))
            has_geometry = has_geometry or "geometry" in piece

    if not has_geometry:
        return {}, False

    indexed: dict[tuple[int, int], dict[str, Any]] = {}
    for sheet_no, piece in rows:
        if "geometry" not in piece:
            raise DxfGeometrySnapshotError(
                "persisted DXF topology is incomplete; a piece is missing geometry."
            )
        try:
            piece_id = int(piece.get("id"))
        except (TypeError, ValueError) as exc:
            raise DxfGeometrySnapshotError(
                "persisted DXF topology requires an integer piece id."
            ) from exc
        if piece_id <= 0:
            raise DxfGeometrySnapshotError(
                "persisted DXF topology requires a positive piece id."
            )
        key = (sheet_no, piece_id)
        if key in indexed:
            raise DxfGeometrySnapshotError(
                f"persisted DXF topology contains duplicate piece identity {sheet_no}:{piece_id}."
            )
        indexed[key] = serialize_geometry_mm(parse_geometry_mm(piece["geometry"]))
    return indexed, True


def validate_snapshot_material_layout(
    snapshot: Any,
    *,
    required_clearance_mm: float,
) -> bool:
    """Validate persisted DXF material topology when present.

    Returns ``False`` for legacy rectangle-only snapshots. Returns ``True`` after
    topology-aware validation succeeds. Malformed/mixed geometry or a material/
    Kerf violation raises instead of silently falling back to rectangles.
    """

    indexed, has_geometry = snapshot_geometry_index(snapshot)
    if not has_geometry:
        return False

    for sheet_index, sheet in enumerate(snapshot.get("sheets") or [], start=1):
        sheet_no = int(sheet.get("sheet_no") or sheet_index)
        placed: list[PlacedPartGeometry] = []
        for piece in sheet.get("pieces") or []:
            piece_id = int(piece.get("id"))
            placed.append(
                PlacedPartGeometry(
                    key=piece.get("label") or piece_id,
                    geometry=parse_geometry_mm(indexed[(sheet_no, piece_id)]),
                )
            )
        validate_material_layout(
            placed,
            required_clearance=max(0.0, float(required_clearance_mm or 0.0)),
            geometry_tolerance=GEOMETRY_TOLERANCE_MM,
            numeric_tolerance=KERF_NUMERIC_TOLERANCE_MM,
        )
    return True


__all__ = [
    "DxfGeometrySnapshotError",
    "DxfTopologyError",
    "GEOMETRY_COORDINATE_SPACE",
    "GEOMETRY_SCHEMA_VERSION",
    "GEOMETRY_TOLERANCE_MM",
    "GEOMETRY_UNIT",
    "KERF_NUMERIC_TOLERANCE_MM",
    "canonicalize_snapshot_geometries",
    "geometry_mm_to_cm",
    "parse_geometry_mm",
    "serialize_geometry_from_cm",
    "serialize_geometry_mm",
    "snapshot_geometry_index",
    "validate_snapshot_material_layout",
]
