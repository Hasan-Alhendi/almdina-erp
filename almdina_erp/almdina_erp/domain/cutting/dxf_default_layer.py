from __future__ import annotations

from typing import Sequence

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    EPSILON,
    bbox,
    is_axis_aligned_rectangle,
    polygon_area,
    polygon_segments,
    polygons_overlap,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import polygon_contains_polygon
from almdina_erp.almdina_erp.domain.cutting.extra_overlays import (
    ExtraOverlayCandidate,
    OVERLAY_HOST_MARGIN_MM,
    overlay_path_contained_in_polygon,
)

Point = tuple[float, float]
Polygon = tuple[Point, ...]

DESIGNER_DEFAULT_LAYER = "0"


def matches_board_rectangle(
    polygon: Sequence[Point],
    *,
    expected_width_mm: float,
    expected_height_mm: float,
    geometry_tolerance: float,
    dimension_tolerance: float,
) -> bool:
    """True when a closed contour is the axis-aligned board rectangle."""

    if not is_axis_aligned_rectangle(polygon, geometry_tolerance):
        return False
    min_x, min_y, max_x, max_y = bbox(polygon)
    return (
        abs((max_x - min_x) - expected_width_mm) <= dimension_tolerance
        and abs((max_y - min_y) - expected_height_mm) <= dimension_tolerance
    )


def is_overlay_framing_polygon(
    polygon: Sequence[Point],
    *,
    larger_hosts: Sequence[Sequence[Point]],
    overlays: Sequence[ExtraOverlayCandidate],
    tolerance: float = EPSILON,
    host_margin: float = 0.0,
) -> bool:
    """True when a smaller layer-0 box only frames Extra overlay marks on a real door."""

    if not overlays or len(polygon) < 3:
        return False
    if not any(
        overlay_path_contained_in_polygon(
            polygon,
            overlay.path,
            tolerance=tolerance,
            closed=overlay.closed,
            host_margin=host_margin,
        )
        for overlay in overlays
    ):
        return False
    area = polygon_area(polygon)
    for host in larger_hosts:
        if polygon_area(host) <= area:
            continue
        if polygon_contains_polygon(host, polygon, tolerance=tolerance):
            return True
        if polygons_overlap(polygon, host, tolerance=tolerance):
            return True
    return False


def classify_default_layer_polygons(
    polygons: Sequence[Sequence[Point]],
    *,
    expected_width_mm: float,
    expected_height_mm: float,
    overlays: Sequence[ExtraOverlayCandidate] = (),
    geometry_tolerance: float = EPSILON,
    dimension_tolerance: float = EPSILON,
    infer_sheets: bool = True,
) -> tuple[tuple[Polygon, ...], tuple[Polygon, ...]]:
    """Split layer-0 closed contours into board outlines and cut doors.

    When ``infer_sheets`` is true (no ``SHEET_OUTLINE``), board-sized rectangles
    become sheet outlines and the remaining doors become cut paths. When sheets
    already come from ``SHEET_OUTLINE``, layer 0 is a ``CUT_PATH`` alias: every
    non-framing closed contour is a cut, including a full-board door.

    Overlay visual boxes drawn on layer 0 (liner strip, handle pocket, etc.)
    are not cut paths when they frame Extra overlay marks on a larger door.
    """

    sheets: list[Polygon] = []
    remainder: list[Polygon] = []
    for polygon in polygons:
        closed = tuple((float(x), float(y)) for x, y in polygon)
        if infer_sheets and matches_board_rectangle(
            closed,
            expected_width_mm=expected_width_mm,
            expected_height_mm=expected_height_mm,
            geometry_tolerance=geometry_tolerance,
            dimension_tolerance=dimension_tolerance,
        ):
            sheets.append(closed)
            continue
        remainder.append(closed)
    cuts = tuple(
        polygon
        for polygon in remainder
        if not is_overlay_framing_polygon(
            polygon,
            larger_hosts=remainder,
            overlays=overlays,
            tolerance=geometry_tolerance,
            host_margin=OVERLAY_HOST_MARGIN_MM,
        )
    )
    return tuple(sheets), cuts


def polygon_to_segments(polygon: Sequence[Point]) -> tuple[tuple[Point, Point], ...]:
    return tuple(polygon_segments(polygon))


__all__ = [
    "DESIGNER_DEFAULT_LAYER",
    "classify_default_layer_polygons",
    "is_overlay_framing_polygon",
    "matches_board_rectangle",
    "polygon_to_segments",
]
