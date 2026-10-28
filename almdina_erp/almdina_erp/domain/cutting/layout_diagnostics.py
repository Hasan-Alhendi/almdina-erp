"""Bounded numeric projections for read-only failure previews, never production."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

MAX_PREVIEW_VERTICES = 512
MAX_IDENTITY_DIAGNOSTIC_PIECES = 200
MAX_IDENTITY_DIAGNOSTIC_VERTICES = 8192


def layout_preview(pieces: Sequence[Mapping[str, Any]], keys: Sequence[Any]) -> dict | None:
    """Keep only the two affected material outlines/holes, in DXF millimeters.

    No bounding-box approximation or partial polygon is drawn when the limit is
    exceeded. Rendering partial geometry would make the diagnosis misleading.
    """
    selected = [piece for piece in pieces if piece.get("id") in keys]
    if len(selected) != 2:
        return None
    paths = []
    count = 0
    for piece in selected:
        rings = []
        for source in [piece.get("_outline_mm") or (), *(piece.get("_holes_mm") or ())]:
            count += len(source)
            if count > MAX_PREVIEW_VERTICES or len(source) < 3:
                return None
            ring = []
            for point in source:
                if not isinstance(point, (list, tuple)) or len(point) != 2:
                    return None
                x, y = float(point[0]), float(point[1])
                if not isfinite(x) or not isfinite(y) or max(abs(x), abs(y)) > 1e8:
                    return None
                ring.append([x, y])
            rings.append(ring)
        paths.append(rings)
    points = [point for rings in paths for ring in rings for point in ring]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return {"paths": paths, "bounds": [min(xs), min(ys), max(xs), max(ys)]}


def public_layout_preview(value: Any) -> dict | None:
    """Whitelist an already projected preview; recompute all numeric bounds."""
    if not isinstance(value, Mapping) or not isinstance(value.get("paths"), (list, tuple)):
        return None
    paths = value["paths"]
    if len(paths) != 2 or any(not isinstance(rings, (list, tuple)) or not rings for rings in paths):
        return None
    try:
        return layout_preview([
            {"id": i, "_outline_mm": rings[0], "_holes_mm": rings[1:]}
            for i, rings in enumerate(paths)
        ], (0, 1))
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
