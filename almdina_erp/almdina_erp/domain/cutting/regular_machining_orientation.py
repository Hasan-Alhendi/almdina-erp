"""Resolve the one physical orientation shared by rectangular machining add-ons.

All geometry is in millimetres, in the plan's top-left/y-down coordinate frame.
A bounding-box swap proves only the parity of a turn, never its direction.
This module has no Frappe or DXF reader dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerMeasurement,
    LinerPiece,
    canonical_path,
    liner_parameters_active,
    sawn_liner_ends,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    compare_overlay_path,
)

Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class RegularOrientationMatch:
    quarter_turns: int | None
    reason: str
    failed_kind: str = ""
    failure: LinerMeasurement | None = None


def physical_edge_tokens(
    bands: Mapping[str, str], quarter_turns: int
) -> tuple[str, str, str, str]:
    """Physical (left, top, right, bottom) bands after clockwise turns."""
    left = str(bands.get("left", "0"))
    top = str(bands.get("top", "0"))
    right = str(bands.get("right", "0"))
    bottom = str(bands.get("bottom", "0"))
    for _ in range(int(quarter_turns) % 4):
        left, top, right, bottom = bottom, left, top, right
    return left, top, right, bottom


def match_regular_machining_orientation(
    *,
    piece: LinerPiece,
    overlay_paths: Mapping[str, Sequence[Point]],
    settings: Mapping[str, Mapping[str, Any]],
    candidate_turns: Sequence[int],
    edge_bands: Mapping[str, str],
    cutter_diameter_mm: float | None,
    origin_mm: Point = (0.0, 0.0),
    board_mm: tuple[float, float, float, float] | None = None,
) -> RegularOrientationMatch:
    """Validate all selected machining paths under ONE inverse transform.

    The service determines eligible turns from exact persisted cut dimensions.
    Equal-looking bounds cannot distinguish a half turn; geometry of *all*
    enabled machining layers must agree before binding semantic edge bands.
    """
    active = [
        (addon.kind, spec)
        for addon in MACHINING_ADDONS
        if (spec := settings.get(addon.kind) or {})
        and liner_parameters_active(
            enabled=bool(spec.get("enabled")),
            side=str(spec.get("side") or ""),
            offset_cm=float(spec.get("offset_cm") or 0),
            width_cm=float(spec.get("width_cm") or 0),
        )
    ]
    if not active:
        return RegularOrientationMatch(None, "no_machining_evidence")

    width_mm = float(piece.width_cm) * 10.0
    height_mm = float(piece.length_cm) * 10.0
    passed: list[int] = []
    best_failed: tuple[int, int, str, LinerMeasurement | None] | None = None
    for turns in tuple(dict.fromkeys(int(value) % 4 for value in candidate_turns)):
        failures: list[tuple[str, LinerMeasurement | None]] = []
        for kind, spec in active:
            path = overlay_paths.get(kind)
            if not path or len(path) < 2:
                failures.append((kind, None))
                continue
            canonical = canonical_path(
                path,
                mirrored=False,
                quarter_turns=turns,
                width_mm=width_mm,
                height_mm=height_mm,
            )
            side = str(spec["side"])
            start = float(spec.get("start_cm") or 0)
            length = float(spec.get("length_cm") or 0)
            try:
                start_sawn, end_sawn = sawn_liner_ends(
                    piece,
                    side,
                    origin_mm=origin_mm,
                    mirrored=False,
                    quarter_turns=turns,
                    board=board_mm,
                    start_cm=start,
                    length_cm=length,
                )
            except LinerGeometryError:
                start_sawn, end_sawn = None, None
            measurement = compare_overlay_path(
                canonical,
                piece,
                kind,
                side,
                float(spec.get("offset_cm") or 0),
                float(spec.get("width_cm") or 0),
                cutter_diameter_mm,
                start,
                length,
                start_sawn=start_sawn,
                end_sawn=end_sawn,
            )
            if not measurement.ok:
                failures.append((kind, measurement))
        if not failures:
            passed.append(turns)
        elif best_failed is None or len(failures) < best_failed[0]:
            kind, failure = failures[0]
            best_failed = (len(failures), turns, kind, failure)

    if not passed:
        if best_failed is None:
            return RegularOrientationMatch(None, "invalid")
        return RegularOrientationMatch(None, "invalid", best_failed[2], best_failed[3])

    physical_signatures = {physical_edge_tokens(edge_bands, turns) for turns in passed}
    if len(physical_signatures) > 1:
        return RegularOrientationMatch(None, "ambiguous")

    return RegularOrientationMatch(min(passed), "unique")
