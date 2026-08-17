from __future__ import annotations

from typing import Any, Callable

SUPPORTED_DXF_ENTITY_TYPES = frozenset({
    "LINE",
    "LWPOLYLINE",
    "POLYLINE",
    "ARC",
    "CIRCLE",
    "SPLINE",
    "ELLIPSE",
})
CURVE_FLATTENING_TOLERANCE_MM = 0.25


class DxfReadError(ValueError):
    pass


def _segments_from_points(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return [(points[index], points[index + 1]) for index in range(len(points) - 1) if points[index] != points[index + 1]]


def read_dxf_geometry(
    file_path: str,
    *,
    relevant_layers: set[str],
    legacy_line_parser: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Read DXF geometry and normalize curves to validation-only segments.

    The source DXF is never rewritten. Curves are flattened only in memory so
    domain validation can operate on a consistent segment representation.
    """
    try:
        import ezdxf
        from ezdxf import path as ezpath
    except ImportError:
        if legacy_line_parser is None:
            raise DxfReadError("مكتبة قراءة DXF غير متوفرة على الخادم.")
        rows = legacy_line_parser()
        return {
            "segments": [
                {
                    "layer": row.get("layer"),
                    "entity_type": "LINE",
                    "start": (float(row.get("x1") or 0), float(row.get("y1") or 0)),
                    "end": (float(row.get("x2") or 0), float(row.get("y2") or 0)),
                }
                for row in rows
            ],
            "unsupported": [],
        }

    try:
        doc = ezdxf.readfile(file_path)
    except Exception as exc:
        raise DxfReadError("تعذر قراءة بنية ملف DXF. تأكد أن الملف DXF صالح وغير تالف.") from exc

    segments: list[dict[str, Any]] = []
    unsupported: list[dict[str, str]] = []
    for entity in doc.modelspace():
        layer = str(getattr(entity.dxf, "layer", "") or "")
        if layer not in relevant_layers:
            continue
        entity_type = entity.dxftype().upper()
        if entity_type not in SUPPORTED_DXF_ENTITY_TYPES:
            unsupported.append({"layer": layer, "entity_type": entity_type})
            continue
        try:
            path = ezpath.make_path(entity)
            flattened = [(float(vertex.x), float(vertex.y)) for vertex in path.flattening(
                distance=CURVE_FLATTENING_TOLERANCE_MM,
                segments=8,
            )]
        except Exception as exc:
            raise DxfReadError(
                f"تعذر تحليل عنصر {entity_type} على الطبقة {layer}. أعد حفظ الرسم كـ DXF قياسي ثم حاول مجددًا."
            ) from exc
        for start, end in _segments_from_points(flattened):
            segments.append(
                {
                    "layer": layer,
                    "entity_type": entity_type,
                    "start": start,
                    "end": end,
                }
            )
    return {"segments": segments, "unsupported": unsupported}
