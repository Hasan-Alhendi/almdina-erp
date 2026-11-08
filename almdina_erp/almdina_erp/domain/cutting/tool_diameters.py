"""Per-layer machining tool diameters.

The cutting tool diameter stays ``kerf_mm``. It is the nesting gap and the
single CUT_PATH center offset (half the diameter, applied once to the finished
outline). Liner, handle recess, and rear groove each store their own diameter.
A missing value inherits that plan's kerf, so a plan saved before these fields
keeps the historical shared blade and is not rewritten when factory defaults
change. An explicit value must be finite and greater than zero.

These diameters are not part of the packing fingerprint. Changing kerf still
moves every facing gap through the existing nesting contract. Changing a layer
diameter does not rewrite an approved snapshot. On the next calculation, a
tool whose path actually extends toward a neighbour, and whose diameter is
larger than kerf, widens only that facing gap. The draft is marked stale when
a stored diameter changes so the next calculation can apply it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    liner_parameters_active,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    generate_liner_set_toolpaths,
    generate_toolpath,
    machining_values,
)


LAYER_FIELDS: tuple[tuple[str, str], ...] = (
    ("liner", "liner_tool_diameter_mm"),
    ("recessed_handle_cutout", "handle_recess_tool_diameter_mm"),
    ("back_groove", "rear_groove_tool_diameter_mm"),
)
FIELD_BY_KIND = {kind: field for kind, field in LAYER_FIELDS}
KIND_BY_FIELD = {field: kind for kind, field in LAYER_FIELDS}
FACTORY_FIELDS = {
    "liner_tool_diameter_mm": "default_liner_tool_diameter_mm",
    "handle_recess_tool_diameter_mm": "default_handle_recess_tool_diameter_mm",
    "rear_groove_tool_diameter_mm": "default_rear_groove_tool_diameter_mm",
}
TOOL_DIAMETER_FIELDS = tuple(FIELD_BY_KIND.values())


class ToolDiameterError(ValueError):
    def __init__(self, code: str, fieldname: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.fieldname = fieldname


def _read(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def explicit_diameter(value: Any, fieldname: str) -> float | None:
    """Blank inherits. A provided number must be finite and greater than zero."""

    if value is None or value == "":
        return None
    number = _finite(value)
    if number is None or number <= 0:
        raise ToolDiameterError("invalid_tool_diameter", fieldname)
    return number


def _positive(value: Any) -> float | None:
    number = _finite(value)
    if number is None or number <= 0:
        return None
    return number


def diameters_for_record(record: Any, *, kerf_mm: float | None = None) -> dict[str, float]:
    """Resolve stored diameters. Missing or non-positive values inherit kerf."""

    raw_kerf = kerf_mm if kerf_mm is not None else _read(record, "kerf_mm", 0)
    kerf = _finite(0 if raw_kerf is None else raw_kerf)
    if kerf is None or kerf < 0:
        kerf = 0.0
    payload: dict[str, float] = {"kerf_mm": kerf}
    for kind, field in LAYER_FIELDS:
        explicit = _positive(_read(record, field, None))
        resolved = explicit if explicit is not None else kerf
        payload[field] = resolved
        payload[kind] = resolved
    return payload


def initial_diameters(
    *,
    kerf_mm: float,
    lineage: Any = None,
    factory: Any = None,
) -> dict[str, float | None]:
    """Diameters copied onto a new plan.

    A lineage plan is copied from itself and never from today's factory
    defaults. The first plan of an order uses a positive factory default,
    otherwise the cutting diameter it is being created with.
    """

    kerf = _positive(kerf_mm)
    stored: dict[str, float | None] = {}
    for field, factory_field in FACTORY_FIELDS.items():
        chosen: float | None = None
        if lineage is not None:
            chosen = _positive(_read(lineage, field, None))
            if chosen is None:
                chosen = _positive(_read(lineage, "kerf_mm", None))
        else:
            if factory is not None:
                chosen = _positive(_read(factory, factory_field, None))
            if chosen is None:
                chosen = kerf
        stored[field] = chosen
    return stored


def diameter_for_kind(kind: str, diameters: Mapping[str, Any]) -> float | None:
    field = FIELD_BY_KIND.get(str(kind or ""))
    if field is None:
        return None
    raw = diameters.get(kind, diameters.get(field))
    return _positive(raw)


def assignment_radius_mm(diameters: Mapping[str, Any]) -> float:
    """Largest tool radius, used only to keep a path attached to its door."""

    positives = [
        number
        for number in (
            _positive(diameters.get("kerf_mm")),
            *(_positive(diameters.get(field)) for field in TOOL_DIAMETER_FIELDS),
        )
        if number is not None
    ]
    if not positives:
        return 0.0
    return max(positives) / 2.0


def _piece_from_snapshot(piece: Mapping[str, Any]) -> LinerPiece:
    width = (
        piece.get("original_w")
        or piece.get("cut_width_cm")
        or piece.get("w")
        or piece.get("width_cm")
        or 0
    )
    length = (
        piece.get("original_h")
        or piece.get("cut_length_cm")
        or piece.get("h")
        or piece.get("length_cm")
        or 0
    )
    return LinerPiece(
        str(piece.get("piece_type") or "Regular"),
        float(width or 0),
        float(length or 0),
        str(piece.get("clipped_corner_position") or "Top Right"),
        float(piece.get("clipped_corner_width_cm") or 0),
        float(piece.get("clipped_corner_length_cm") or 0),
    )


def _persisted_toolpath(piece: Mapping[str, Any], kind: str) -> bool:
    overlays = piece.get("overlays") or ()
    if not isinstance(overlays, Sequence) or isinstance(overlays, (str, bytes)):
        return False
    for overlay in overlays:
        if not isinstance(overlay, Mapping) or str(overlay.get("kind") or "") != kind:
            continue
        geometry = overlay.get("geometry") or {}
        if not isinstance(geometry, Mapping):
            continue
        path = geometry.get("path") or geometry.get("outer")
        if isinstance(path, Sequence) and len(path) >= 2:
            return True
    return False


def _layer_active(spec: Mapping[str, Any]) -> bool:
    if liner_parameters_active(
        enabled=bool(spec.get("enabled")),
        side=str(spec.get("side") or ""),
        offset_cm=float(spec.get("offset_cm") or 0),
        width_cm=float(spec.get("width_cm") or 0),
    ):
        return True
    return any(
        str(item.get("side") or "").strip() and float(item.get("width_cm") or spec.get("width_cm") or 0) > 0
        for item in (spec.get("liners") or ())
        if isinstance(item, Mapping)
    )


def export_tool_errors(
    piece: Mapping[str, Any],
    diameters: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Refuse a generated toolpath that the current diameter cannot cut safely.

    A path already stored on the piece is a cutter center. It is not offset
    again here. Special outlines keep their uploaded paths and are not passed
    through the rectangular generator.
    """

    if str(piece.get("piece_type") or "") == "Special":
        return []
    values = machining_values(piece)
    host = _piece_from_snapshot(piece)
    errors: list[dict[str, str]] = []
    label = str(piece.get("label") or piece.get("piece_no") or "")
    for kind, _field in LAYER_FIELDS:
        spec = values.get(kind) or {}
        if not _layer_active(spec):
            continue
        if _persisted_toolpath(piece, kind):
            continue
        diameter = diameter_for_kind(kind, diameters)
        if diameter is None:
            errors.append({
                "code": "cutter_diameter_invalid",
                "kind": kind,
                "label": label,
            })
            continue
        try:
            liners = tuple(spec.get("liners") or ())
            if kind == "liner" and len(liners) > 1:
                generate_liner_set_toolpaths(
                    piece=host,
                    specs=liners,
                    width_cm=float(spec.get("width_cm") or 0),
                    cutter_diameter_mm=diameter,
                )
            else:
                generate_toolpath(
                    kind=kind,
                    piece=host,
                    reference_side=str(spec.get("side") or ""),
                    offset_cm=float(spec.get("offset_cm") or 0),
                    width_cm=float(spec.get("width_cm") or 0),
                    start_cm=spec.get("start_cm"),
                    length_cm=spec.get("length_cm"),
                    cutter_diameter_mm=diameter,
                )
        except LinerGeometryError as error:
            errors.append({"code": error.code, "kind": kind, "label": label})
    return errors


def snapshot_tool_errors(
    snapshot: Mapping[str, Any],
    diameters: Mapping[str, Any],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for sheet in snapshot.get("sheets") or ():
        if not isinstance(sheet, Mapping):
            continue
        for piece in sheet.get("pieces") or ():
            if isinstance(piece, Mapping):
                errors.extend(export_tool_errors(piece, diameters))
    return errors


__all__ = [
    "FACTORY_FIELDS",
    "FIELD_BY_KIND",
    "KIND_BY_FIELD",
    "LAYER_FIELDS",
    "TOOL_DIAMETER_FIELDS",
    "ToolDiameterError",
    "assignment_radius_mm",
    "diameter_for_kind",
    "diameters_for_record",
    "explicit_diameter",
    "export_tool_errors",
    "initial_diameters",
    "snapshot_tool_errors",
]
