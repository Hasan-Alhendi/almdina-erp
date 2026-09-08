from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    EPSILON,
    point_near_polygon,
    points_close,
    polygon_segments,
    segments_intersect,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_OVERLAY_LAYER_BY_KIND,
    EXTRA_PIECE_TYPE,
    extra_overlay_layer_for_kind,
)

Point = tuple[float, float]
Polygon = tuple[Point, ...]
Path = tuple[Point, ...]

OVERLAY_HOST_MARGIN_MM = 3.0


class ExtraOverlayError(ValueError):
    """Raised when an Extra manufacturing overlay violates the DXF contract."""

    def __init__(
        self,
        code: str,
        *,
        layer: str = "",
        host_key: str | int | None = None,
        kind: str = "",
        label: str = "",
    ) -> None:
        super().__init__(code)
        self.code = code
        self.layer = layer
        self.host_key = host_key
        self.kind = kind
        self.label = label


@dataclass(frozen=True, slots=True)
class ExtraOverlayCandidate:
    key: int
    kind: str
    layer: str
    path: Path
    closed: bool = False


@dataclass(frozen=True, slots=True)
class ExtraOverlayHost:
    key: str | int
    piece_type: str
    polygon: Polygon
    selected_codes: tuple[str, ...] = ()
    label: str = ""


@dataclass(frozen=True, slots=True)
class AssignedExtraOverlay:
    host_key: str | int
    kind: str
    layer: str
    path: Path
    closed: bool = False


def dedupe_overlay_points(
    points: Sequence[Point],
    *,
    tolerance: float,
    closed: bool = False,
) -> tuple[Point, ...]:
    """Drop consecutive duplicates without forcing the mark into a closed ring."""

    clean: list[Point] = []
    for point in points:
        current = (float(point[0]), float(point[1]))
        if not clean or not points_close(clean[-1], current, tolerance):
            clean.append(current)
    if closed and len(clean) > 2 and points_close(clean[0], clean[-1], tolerance):
        clean.pop()
    return tuple(clean)


def overlay_path_segments(path: Sequence[Point], *, closed: bool) -> tuple[tuple[Point, Point], ...]:
    points = tuple(path)
    if len(points) < 2:
        return ()
    segments = list(zip(points, points[1:]))
    if closed and len(points) >= 3:
        segments.append((points[-1], points[0]))
    return tuple(segments)


def overlay_path_contained_in_polygon(
    container: Sequence[Point],
    path: Sequence[Point],
    *,
    tolerance: float = EPSILON,
    closed: bool = False,
    host_margin: float = 0.0,
) -> bool:
    """True when every overlay vertex lies inside the Extra outline, including a small outside margin."""

    points = tuple(path)
    if len(container) < 3 or len(points) < 2:
        return False
    if not all(
        point_near_polygon(
            point,
            container,
            tolerance=tolerance,
            margin=host_margin,
        )
        for point in points
    ):
        return False
    if not closed:
        return True
    closing = (points[-1], points[0])
    return not _segment_escapes_polygon(
        closing,
        container,
        tolerance=tolerance,
        host_margin=host_margin,
    )


def overlay_path_hits_polygon(
    path: Sequence[Point],
    polygon: Sequence[Point],
    *,
    tolerance: float = EPSILON,
    closed: bool = False,
    host_margin: float = 0.0,
) -> bool:
    """True when the mark touches or crosses the polygon interior or boundary."""

    points = tuple(path)
    if len(polygon) < 3 or len(points) < 2:
        return False
    if any(
        point_near_polygon(
            point,
            polygon,
            tolerance=tolerance,
            margin=host_margin,
        )
        for point in points
    ):
        return True
    poly_segments = polygon_segments(polygon)
    for segment in overlay_path_segments(points, closed=closed):
        for edge in poly_segments:
            if segments_intersect(segment, edge, tolerance):
                return True
    return False


def _segment_escapes_polygon(
    segment: tuple[Point, Point],
    polygon: Sequence[Point],
    *,
    tolerance: float,
    host_margin: float = 0.0,
) -> bool:
    start, end = segment
    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    return not point_near_polygon(
        midpoint,
        polygon,
        tolerance=tolerance,
        margin=host_margin,
    )


def assign_extra_overlays(
    overlays: Sequence[ExtraOverlayCandidate],
    hosts: Sequence[ExtraOverlayHost],
    *,
    tolerance: float = EPSILON,
    host_margin: float = 0.0,
) -> tuple[AssignedExtraOverlay, ...]:
    """Bind overlay marks to Extra hosts without treating them as cut pieces."""

    assigned: list[AssignedExtraOverlay] = []
    for overlay in overlays:
        path = overlay.path
        if len(path) < 2:
            raise ExtraOverlayError("extra_overlay_invalid_path", layer=overlay.layer)
        contained = tuple(
            host
            for host in hosts
            if overlay_path_contained_in_polygon(
                host.polygon,
                path,
                tolerance=tolerance,
                closed=overlay.closed,
                host_margin=host_margin,
            )
        )
        contained_extras = tuple(
            host for host in contained if host.piece_type == EXTRA_PIECE_TYPE
        )
        intersecting = tuple(
            host
            for host in hosts
            if overlay_path_hits_polygon(
                path,
                host.polygon,
                tolerance=tolerance,
                closed=overlay.closed,
                host_margin=host_margin,
            )
        )
        intersecting_extras = tuple(
            host for host in intersecting if host.piece_type == EXTRA_PIECE_TYPE
        )
        intersecting_others = tuple(
            host for host in intersecting if host.piece_type != EXTRA_PIECE_TYPE
        )

        if len(contained_extras) > 1 or len(intersecting_extras) > 1:
            raise ExtraOverlayError(
                "extra_overlay_spans_hosts",
                layer=overlay.layer,
            )
        if len(contained_extras) == 1:
            host = contained_extras[0]
            if overlay.kind not in host.selected_codes:
                raise ExtraOverlayError(
                    "extra_overlay_addon_not_selected",
                    layer=overlay.layer,
                    host_key=host.key,
                    kind=overlay.kind,
                    label=host.label,
                )
            assigned.append(
                AssignedExtraOverlay(
                    host_key=host.key,
                    kind=overlay.kind,
                    layer=overlay.layer,
                    path=path,
                    closed=overlay.closed,
                )
            )
            continue
        if intersecting_others:
            raise ExtraOverlayError(
                "extra_overlay_on_non_extra",
                layer=overlay.layer,
                host_key=intersecting_others[0].key,
            )
        raise ExtraOverlayError(
            "extra_overlay_floating",
            layer=overlay.layer,
        )

    mismatches = extra_overlay_selection_mismatches(hosts, assigned)
    if mismatches:
        raise mismatches[0]
    return tuple(assigned)


def extra_overlay_selection_mismatches(
    hosts: Sequence[ExtraOverlayHost],
    assigned: Sequence[AssignedExtraOverlay],
) -> tuple[ExtraOverlayError, ...]:
    """Return Extra overlay kinds that do not match the order checkboxes.

    Each Extra host must have exactly one mark for every selected overlay kind
    (liner, back groove, recessed handle) and none for unselected overlay kinds.
    Double / full-door-double are commercial addons, not DXF overlay layers.
    """

    found_by_host: dict[str | int, list[str]] = {}
    for item in assigned:
        found_by_host.setdefault(item.host_key, []).append(item.kind)

    errors: list[ExtraOverlayError] = []
    for host in hosts:
        if host.piece_type != EXTRA_PIECE_TYPE:
            continue
        found = found_by_host.get(host.key, [])
        selected = {
            code for code in host.selected_codes if code in EXTRA_OVERLAY_LAYER_BY_KIND
        }
        for kind in EXTRA_OVERLAY_LAYER_BY_KIND:
            count = found.count(kind)
            selected_kind = kind in selected
            if selected_kind and count == 0:
                errors.append(
                    ExtraOverlayError(
                        "extra_overlay_addon_missing",
                        layer=extra_overlay_layer_for_kind(kind),
                        host_key=host.key,
                        kind=kind,
                        label=host.label,
                    )
                )
            elif selected_kind and count > 1:
                errors.append(
                    ExtraOverlayError(
                        "extra_overlay_addon_duplicate",
                        layer=extra_overlay_layer_for_kind(kind),
                        host_key=host.key,
                        kind=kind,
                        label=host.label,
                    )
                )
            elif not selected_kind and count:
                errors.append(
                    ExtraOverlayError(
                        "extra_overlay_addon_not_selected",
                        layer=extra_overlay_layer_for_kind(kind),
                        host_key=host.key,
                        kind=kind,
                        label=host.label,
                    )
                )
    return tuple(errors)


__all__ = [
    "AssignedExtraOverlay",
    "ExtraOverlayCandidate",
    "ExtraOverlayError",
    "ExtraOverlayHost",
    "assign_extra_overlays",
    "dedupe_overlay_points",
    "extra_overlay_selection_mismatches",
    "overlay_path_contained_in_polygon",
    "overlay_path_hits_polygon",
    "overlay_path_segments",
    "OVERLAY_HOST_MARGIN_MM",
]
