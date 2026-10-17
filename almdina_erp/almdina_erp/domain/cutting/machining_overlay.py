"""Shared machining overlay registry.

Liner, back groove, and recessed handle use one cutter-center toolpath.
``kind`` selects the stored fields and DXF layer. It does not select an algorithm.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerMeasurement,
    LinerPiece,
    compare_liner_path,
    liner_toolpath_mm,
)


@dataclass(frozen=True, slots=True)
class MachiningAddon:
    kind: str
    layer: str
    enabled_field: str
    side_field: str
    offset_field: str
    width_field: str
    start_field: str
    length_field: str


MACHINING_ADDONS: tuple[MachiningAddon, ...] = (
    MachiningAddon(
        "liner",
        "Liner",
        "extra_liner",
        "liner_reference_side",
        "liner_offset_cm",
        "liner_width_cm",
        "liner_start_cm",
        "liner_length_cm",
    ),
    MachiningAddon(
        "back_groove",
        "Rear Groove",
        "extra_back_groove",
        "back_groove_reference_side",
        "back_groove_offset_cm",
        "back_groove_width_cm",
        "back_groove_start_cm",
        "back_groove_length_cm",
    ),
    MachiningAddon(
        "recessed_handle_cutout",
        "Handle Recess",
        "extra_recessed_handle_cutout",
        "recessed_handle_reference_side",
        "recessed_handle_offset_cm",
        "recessed_handle_width_cm",
        "recessed_handle_start_cm",
        "recessed_handle_length_cm",
    ),
)
MACHINING_ADDONS_BY_KIND = {addon.kind: addon for addon in MACHINING_ADDONS}
MACHINING_GEOMETRY_FIELDS = tuple(
    field
    for addon in MACHINING_ADDONS
    for field in (
        addon.enabled_field,
        addon.side_field,
        addon.offset_field,
        addon.width_field,
        addon.start_field,
        addon.length_field,
    )
)


def machining_addon(kind: str) -> MachiningAddon:
    try:
        return MACHINING_ADDONS_BY_KIND[str(kind)]
    except KeyError as exc:
        raise LinerGeometryError("unknown_machining_addon") from exc


def _read(source: Any, name: str, default: Any = 0) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _num(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def machining_values(source: Any) -> dict[str, dict[str, Any]]:
    """Read each add-on's stored parameters without sharing liner fields."""

    values: dict[str, dict[str, Any]] = {}
    for addon in MACHINING_ADDONS:
        values[addon.kind] = {
            "enabled": bool(_read(source, addon.enabled_field, 0)),
            "side": str(_read(source, addon.side_field, "") or ""),
            "offset_cm": _num(_read(source, addon.offset_field, 0)),
            "width_cm": _num(_read(source, addon.width_field, 0)),
            "start_cm": _num(_read(source, addon.start_field, 0)),
            "length_cm": _num(_read(source, addon.length_field, 0)),
        }
    return values


def machining_metadata(source: Any) -> dict[str, Any]:
    """Flat piece metadata for every machining add-on, including inactive zeros."""

    payload: dict[str, Any] = {}
    values = machining_values(source)
    for addon in MACHINING_ADDONS:
        spec = values[addon.kind]
        payload[addon.enabled_field] = 1 if spec["enabled"] else 0
        payload[addon.side_field] = spec["side"]
        payload[addon.offset_field] = spec["offset_cm"]
        payload[addon.width_field] = spec["width_cm"]
        payload[addon.start_field] = spec["start_cm"]
        payload[addon.length_field] = spec["length_cm"]
    return payload


def generate_toolpath(
    *,
    kind: str,
    piece: LinerPiece,
    reference_side: str,
    offset_cm: float,
    width_cm: float,
    start_cm: float | None,
    length_cm: float | None,
    cutter_diameter_mm: float,
    start_sawn: bool | None = None,
    end_sawn: bool | None = None,
) -> list[tuple[float, float]]:
    """Cutter-center zigzag. ``kind`` only checks that the add-on is registered."""

    machining_addon(kind)
    return liner_toolpath_mm(
        piece,
        reference_side,
        offset_cm,
        width_cm,
        cutter_diameter_mm,
        start_cm,
        length_cm,
        start_sawn=start_sawn,
        end_sawn=end_sawn,
    )


def compare_overlay_path(
    path,
    piece: LinerPiece,
    kind: str,
    side: str,
    offset_cm: float,
    width_cm: float,
    cutter_diameter_mm: float | None = None,
    start_cm: float | None = None,
    length_cm: float | None = None,
    *,
    start_sawn: bool | None = None,
    end_sawn: bool | None = None,
) -> LinerMeasurement:
    """Geometric check shared by every machining add-on."""

    machining_addon(kind)
    return compare_liner_path(
        path,
        piece,
        side,
        offset_cm,
        width_cm,
        cutter_diameter_mm,
        start_cm,
        length_cm,
        start_sawn=start_sawn,
        end_sawn=end_sawn,
    )


__all__ = [
    "MACHINING_ADDONS",
    "MACHINING_ADDONS_BY_KIND",
    "MACHINING_GEOMETRY_FIELDS",
    "MachiningAddon",
    "compare_overlay_path",
    "generate_toolpath",
    "machining_addon",
    "machining_metadata",
    "machining_values",
]
