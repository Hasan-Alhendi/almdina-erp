"""Read operational DXF entities without turning them into machine motion.

INSERT transforms stay in the existing reader. Sheet-local coordinates are the
entity coordinates minus that sheet outline's minimum corner. A missing
outline does not become a machine origin.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.operations import CNC_OPERATION_TYPES
from almdina_erp.almdina_erp.domain.cnc.program import chain_line_paths
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    DxfReadError,
    read_dxf_geometry,
)


_CANONICAL_LAYER = {operation.dxf_layer.upper(): operation.dxf_layer for operation in CNC_OPERATION_TYPES}
_OUTLINE = "SHEET_OUTLINE"


def _length_unit(file_path: str) -> str:
    try:
        import ezdxf
    except ImportError as exc:
        raise DxfReadError(
            "مكتبة قراءة DXF غير متوفرة على الخادم.",
            code="DXF_LIBRARY_MISSING",
        ) from exc
    try:
        document = ezdxf.readfile(file_path)
        code = int(document.header.get("$INSUNITS", 0) or 0)
    except (OSError, TypeError, ValueError) as exc:
        raise DxfReadError(
            "تعذر قراءة وحدات ملف DXF.",
            code="DXF_UNREADABLE",
        ) from exc
    return "mm" if code in (0, 4) else "unknown"


def _polyline(segments: list[dict[str, Any]]) -> tuple[list[tuple[float, float]], bool]:
    points = [tuple(segments[0]["start"])]
    for segment in segments:
        points.append(tuple(segment["end"]))
    return points, bool(segments[0].get("closed"))


def read_operational_dxf(file_path: str, *, sheet_no: int) -> dict[str, Any]:
    """Return one sheet's operational entities in sheet-local millimetres."""

    units = _length_unit(file_path)
    geometry = read_dxf_geometry(
        file_path,
        relevant_layers=set(_CANONICAL_LAYER) | {_OUTLINE},
    )
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for segment in geometry.get("segments") or []:
        grouped[(int(segment["entity_id"]), str(segment["layer"]))].append(segment)

    outline_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for (_entity_id, layer), segments in grouped.items():
        if layer != _OUTLINE:
            continue
        points, _closed = _polyline(segments)
        outline_segments.extend(zip(points, points[1:]))
    outlines = []
    for points, closed in chain_line_paths(outline_segments):
        if not closed or len(points) < 3:
            continue
        min_x = min(point[0] for point in points)
        min_y = min(point[1] for point in points)
        outlines.append((min_y, min_x, (min_x, min_y)))
    outlines.sort()
    origin = outlines[int(sheet_no) - 1][2] if 0 < int(sheet_no) <= len(outlines) else None

    def local(point: tuple[float, float]) -> tuple[float, float]:
        if origin is None:
            return point
        return (point[0] - origin[0], point[1] - origin[1])

    cut_segments = []
    overlays = []
    for (_entity_id, layer), segments in grouped.items():
        if layer == _OUTLINE:
            continue
        canonical = _CANONICAL_LAYER.get(layer)
        if canonical is None:
            continue
        points, closed = _polyline(segments)
        local_points = [local(point) for point in points]
        if canonical == "CUT_PATH":
            cut_segments.extend(zip(local_points, local_points[1:]))
            continue
        entity_type = str(segments[0].get("entity_type") or "LWPOLYLINE")
        if entity_type == "LINE" and len(local_points) == 2:
            overlays.append(
                {
                    "layer": canonical,
                    "points": local_points,
                    "closed": False,
                    "entity_type": "LINE",
                }
            )
            continue
        overlays.append(
            {
                "layer": canonical,
                "points": local_points,
                "closed": closed,
                "entity_type": "LWPOLYLINE",
            }
        )
    unsupported = [
        item
        for item in geometry.get("unsupported") or []
        if str(item.get("layer") or "").upper() in _CANONICAL_LAYER
    ]
    return {
        "units": units,
        "origin": origin,
        "sheet_count": len(outlines),
        "cut_segments": [(start, end) for start, end in cut_segments],
        "overlays": overlays,
        "unsupported": unsupported,
        "unreadable": False,
    }


__all__ = ["read_operational_dxf"]
