"""Read operational DXF entities without turning them into machine motion.

INSERT transforms stay in the existing reader. Sheet-local coordinates are the
entity coordinates minus that sheet outline's minimum corner. A missing
outline does not become a machine origin. ``$INSUNITS`` 0 is unspecified and
is not treated as millimetres.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.operations import CNC_OPERATION_TYPES
from almdina_erp.almdina_erp.domain.cnc.program import chain_line_paths
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import bbox, is_axis_aligned_rectangle
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import (
    DxfReadError,
    read_dxf_geometry,
)


_CANONICAL_LAYER = {operation.dxf_layer.upper(): operation.dxf_layer for operation in CNC_OPERATION_TYPES}
_OUTLINE = "SHEET_OUTLINE"
_EDGE_TOLERANCE_MM = 0.05
_SHEET_FRAME_UNKNOWN = "sheet_frame_unknown"
_AFFILIATION_AMBIGUOUS = "path_sheet_affiliation_ambiguous"
_PATH_OUTSIDE_SHEET = "path_outside_sheet"


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
    if code == 4:
        return "mm"
    if code == 0:
        return "unspecified"
    return "unknown"


def _polyline(segments: list[dict[str, Any]]) -> tuple[list[tuple[float, float]], bool]:
    points = [tuple(segments[0]["start"])]
    for segment in segments:
        points.append(tuple(segment["end"]))
    return points, bool(segments[0].get("closed"))


def _sheet_frames(grouped: dict[tuple[int, str], list[dict[str, Any]]]) -> tuple[list[dict[str, float]], str]:
    """Number closed rectangular outlines the same way plan import does.

    Approved uploaded plans store ``sheet_no`` after sorting ``SHEET_OUTLINE``
    by minimum Y, then minimum X. Coordinate order is used only because that
    import contract is the numbering already stored on the approved plan.
    """

    outline_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for (_entity_id, layer), segments in grouped.items():
        if layer != _OUTLINE:
            continue
        points, _closed = _polyline(segments)
        outline_segments.extend(zip(points, points[1:]))
    frames: list[dict[str, float]] = []
    for points, closed in chain_line_paths(outline_segments):
        if not closed or len(points) < 4:
            continue
        if not is_axis_aligned_rectangle(points, _EDGE_TOLERANCE_MM):
            return [], _SHEET_FRAME_UNKNOWN
        min_x, min_y, max_x, max_y = bbox(points)
        frames.append(
            {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
            }
        )
    frames.sort(key=lambda frame: (frame["min_y"], frame["min_x"]))
    return frames, ""


def _covers_sheet(
    points: list[tuple[float, float]],
    frame: dict[str, float],
    allowance_mm: float,
) -> bool:
    pad = max(0.0, float(allowance_mm)) + _EDGE_TOLERANCE_MM
    return all(
        frame["min_x"] - pad <= point[0] <= frame["max_x"] + pad
        and frame["min_y"] - pad <= point[1] <= frame["max_y"] + pad
        for point in points
    )


def _empty_read(
    *,
    units: str,
    origin: tuple[float, float] | None,
    sheet_count: int,
    read_error: str,
    unsupported: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "units": units,
        "origin": origin,
        "sheet_count": sheet_count,
        "cut_segments": [],
        "cut_paths": [],
        "overlays": [],
        "unsupported": unsupported or [],
        "unreadable": False,
        "read_error": read_error,
    }


def read_operational_dxf(
    file_path: str,
    *,
    sheet_no: int,
    boundary_allowance_mm: float = 0.0,
) -> dict[str, Any]:
    """Return one sheet's operational entities in sheet-local millimetres.

    ``boundary_allowance_mm`` is the approved cutter-center offset. A path may
    extend past the sheet edge by that amount and still belong to the sheet.
    A path that fits more than one expanded sheet, or none, is rejected
    instead of being assigned by guess.
    """

    units = _length_unit(file_path)
    geometry = read_dxf_geometry(
        file_path,
        relevant_layers=set(_CANONICAL_LAYER) | {_OUTLINE},
    )
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for segment in geometry.get("segments") or []:
        grouped[(int(segment["entity_id"]), str(segment["layer"]))].append(segment)
    unsupported = [
        item
        for item in geometry.get("unsupported") or []
        if str(item.get("layer") or "").upper() in _CANONICAL_LAYER
    ]
    frames, frame_error = _sheet_frames(grouped)
    requested = int(sheet_no)
    if frame_error or not (0 < requested <= len(frames)):
        return _empty_read(
            units=units,
            origin=None,
            sheet_count=len(frames),
            read_error=frame_error or _SHEET_FRAME_UNKNOWN,
            unsupported=unsupported,
        )
    frame = frames[requested - 1]
    origin = (frame["min_x"], frame["min_y"])

    def local(point: tuple[float, float]) -> tuple[float, float]:
        return (point[0] - origin[0], point[1] - origin[1])

    cut_segments = []
    cut_paths = []
    overlays = []
    ambiguous = False
    outside = False
    for (entity_id, layer), segments in grouped.items():
        if layer == _OUTLINE:
            continue
        canonical = _CANONICAL_LAYER.get(layer)
        if canonical is None:
            continue
        points, closed = _polyline(segments)
        if len(points) < 2:
            outside = True
            continue
        owners = [item for item in frames if _covers_sheet(points, item, boundary_allowance_mm)]
        if len(owners) != 1:
            ambiguous = ambiguous or len(owners) > 1
            outside = outside or len(owners) == 0
            continue
        if owners[0] is not frame:
            continue
        local_points = [local(point) for point in points]
        entity_type = str(segments[0].get("entity_type") or "LWPOLYLINE")
        if canonical == "CUT_PATH":
            path_closed = bool(closed) if entity_type != "LINE" else False
            if path_closed and len(local_points) >= 3 and local_points[0] == local_points[-1]:
                path_points = local_points[:-1]
            else:
                path_points = local_points
            cut_paths.append(
                {
                    "entity_id": int(entity_id),
                    "entity_type": entity_type,
                    "points": path_points,
                    "closed": path_closed,
                    "layer": canonical,
                    "sheet_no": requested,
                }
            )
            cut_segments.extend(zip(local_points, local_points[1:]))
            if path_closed and len(local_points) >= 3 and local_points[0] != local_points[-1]:
                cut_segments.append((local_points[-1], local_points[0]))
            continue
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
    if ambiguous or outside:
        return _empty_read(
            units=units,
            origin=origin,
            sheet_count=len(frames),
            read_error=_AFFILIATION_AMBIGUOUS if ambiguous else _PATH_OUTSIDE_SHEET,
            unsupported=unsupported,
        )
    return {
        "units": units,
        "origin": origin,
        "sheet_count": len(frames),
        "cut_segments": [(start, end) for start, end in cut_segments],
        "cut_paths": cut_paths,
        "overlays": overlays,
        "unsupported": unsupported,
        "unreadable": False,
        "read_error": "",
    }


__all__ = ["read_operational_dxf"]
