"""Resolve finished piece outlines for manufacturing consumers such as CNC.

System cutting plans often omit snapshot ``geometry.outer`` / ``holes``. The
trusted cut outline still lives in the approved placement fields and is the
same source used by Glass-nest layout and export validation. This module does
not invent rectangles for Special doors that lack an exact polygon.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    parse_geometry_mm,
    serialize_geometry_from_cm,
    serialize_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    finished_part_geometry_cm,
    material_outline_cm,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import num

# Match glass_opening_nesting._SPECIAL_EPSILON_CM without importing a private.
_SPECIAL_BLANK_EPSILON_CM = 0.001


def _copy_optional(source: dict[str, Any], piece: Mapping[str, Any], stored: Mapping[str, Any], key: str) -> None:
    value = piece.get(key)
    if value in (None, "", []):
        value = stored.get(key)
    if value not in (None, "", []):
        source[key] = value


def _special_blank_cm(raw: Any) -> tuple[float, float] | None:
    if isinstance(raw, str):
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
    elif isinstance(raw, Mapping):
        payload = raw
    else:
        return None
    if (
        not isinstance(payload, Mapping)
        or payload.get("version") != 1
        or payload.get("kind") != "polygon"
        or payload.get("units") != "cm"
        or payload.get("exact") is False
    ):
        return None
    blank_w = round(num(payload.get("blank_width_cm")), 3)
    blank_h = round(num(payload.get("blank_length_cm")), 3)
    if blank_w <= 0 or blank_h <= 0:
        return None
    return blank_w, blank_h


def _align_special_originals_to_blank(source: dict[str, Any]) -> dict[str, Any]:
    """Recover finished blank identity for approved System Specials.

    Historical System snapshots stored cut nesting sizes in ``original_*`` while
    ``special_shape_geometry_json`` blanks stay finished. Prefer the exact blank
    so ``_special_outline`` can rebuild without inventing a rectangle. When the
    blank already matches, leave sizes unchanged.
    """

    if str(source.get("piece_type") or "Regular") != "Special":
        return source
    blank = _special_blank_cm(source.get("special_shape_geometry_json"))
    if blank is None:
        return source
    blank_w, blank_h = blank
    expected_w = num(
        source.get("original_w")
        or source.get("original_width_cm")
        or source.get("width_cm")
        or blank_w
    )
    expected_h = num(
        source.get("original_h")
        or source.get("original_length_cm")
        or source.get("length_cm")
        or blank_h
    )
    if (
        abs(blank_w - expected_w) <= _SPECIAL_BLANK_EPSILON_CM
        and abs(blank_h - expected_h) <= _SPECIAL_BLANK_EPSILON_CM
    ):
        return source
    aligned = dict(source)
    aligned["original_w"] = blank_w
    aligned["original_h"] = blank_h
    aligned["original_width_cm"] = blank_w
    aligned["original_length_cm"] = blank_h
    # Keep width_cm/length_cm as finished identity for outline helpers that fall
    # back to those keys when original_* are absent.
    aligned["width_cm"] = blank_w
    aligned["length_cm"] = blank_h
    return aligned


def placed_source_for_finished_geometry(
    piece: Mapping[str, Any],
    stored: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the centimetre placement contract expected by material outlines."""

    stored = stored or {}
    width_mm = num(piece.get("width_mm"))
    height_mm = num(piece.get("height_mm"))
    if width_mm <= 0:
        width_mm = num(stored.get("w")) * 10.0
    if height_mm <= 0:
        height_mm = num(stored.get("h")) * 10.0
    x_mm = num(piece.get("x_mm"))
    y_mm = num(piece.get("y_mm"))
    if piece.get("x_mm") is None and "x" in stored:
        x_mm = num(stored.get("x")) * 10.0
    if piece.get("y_mm") is None and "y" in stored:
        y_mm = num(stored.get("y")) * 10.0
    source = {
        "x": (x_mm / 10.0) if width_mm > 0 or "x" in stored else 0.0,
        "y": (y_mm / 10.0) if height_mm > 0 or "y" in stored else 0.0,
        "w": (width_mm / 10.0) if width_mm > 0 else num(stored.get("w")),
        "h": (height_mm / 10.0) if height_mm > 0 else num(stored.get("h")),
        "piece_type": str(
            piece.get("piece_type") or stored.get("piece_type") or "Regular"
        ),
        "rotated": bool(int(piece.get("rotated") or stored.get("rotated") or 0)),
        "clipped_corner_position": str(
            piece.get("clipped_corner_position")
            or stored.get("clipped_corner_position")
            or ""
        ),
        "clipped_corner_width_cm": num(
            piece.get("clipped_corner_width_cm")
            if piece.get("clipped_corner_width_cm") not in (None, "")
            else stored.get("clipped_corner_width_cm")
        ),
        "clipped_corner_length_cm": num(
            piece.get("clipped_corner_length_cm")
            if piece.get("clipped_corner_length_cm") not in (None, "")
            else stored.get("clipped_corner_length_cm")
        ),
        "special_shape_geometry_json": (
            piece.get("special_shape_geometry_json")
            or stored.get("special_shape_geometry_json")
            or ""
        ),
        "original_w": num(
            piece.get("original_width_cm")
            or stored.get("original_w")
            or stored.get("original_width_cm")
            or stored.get("final_width_cm")
            or stored.get("width_cm")
        ),
        "original_h": num(
            piece.get("original_length_cm")
            or stored.get("original_h")
            or stored.get("original_length_cm")
            or stored.get("final_length_cm")
            or stored.get("length_cm")
        ),
        "original_width_cm": num(
            piece.get("original_width_cm")
            or stored.get("original_w")
            or stored.get("original_width_cm")
            or stored.get("final_width_cm")
        ),
        "original_length_cm": num(
            piece.get("original_length_cm")
            or stored.get("original_h")
            or stored.get("original_length_cm")
            or stored.get("final_length_cm")
        ),
        "width_cm": num(
            piece.get("original_width_cm")
            or stored.get("original_w")
            or stored.get("final_width_cm")
            or stored.get("width_cm")
        ),
        "length_cm": num(
            piece.get("original_length_cm")
            or stored.get("original_h")
            or stored.get("final_length_cm")
            or stored.get("length_cm")
        ),
    }
    for key in (
        "placement_outline_cm",
        "blank_reservation_cm",
        "glass_host_piece_id",
        "glass_hole_local_mm",
        "glass_margin_mm",
        "glass_margin_mode",
        "glass_margin_top_mm",
        "glass_margin_bottom_mm",
        "glass_margin_right_mm",
        "glass_margin_left_mm",
    ):
        _copy_optional(source, piece, stored, key)
    return _align_special_originals_to_blank(source)


def resolve_finished_geometry_mm(
    *,
    stored_geometry: Mapping[str, Any] | None = None,
    piece: Mapping[str, Any] | None = None,
    stored_piece: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return canonical usable-sheet millimetre geometry, or ``None`` if unproven."""

    if isinstance(stored_geometry, Mapping):
        try:
            return serialize_geometry_mm(
                parse_geometry_mm(stored_geometry),
                stored_geometry.get("manufacturing"),
            )
        except DxfGeometrySnapshotError:
            # Fall through to rebuild from approved placement when possible.
            pass
    source = placed_source_for_finished_geometry(piece or {}, stored_piece)
    if material_outline_cm(source) is None:
        return None
    part = finished_part_geometry_cm(source)
    if part is None or not part.outer:
        return None
    return serialize_geometry_from_cm(part)


__all__ = [
    "placed_source_for_finished_geometry",
    "resolve_finished_geometry_mm",
]
