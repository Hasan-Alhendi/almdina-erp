"""Material-space measurements at the completed System candidate boundary.

Shapely is confined to the infrastructure geometry port. Unknown Special
contours exclude their whole sheet and identify that exact sheet in the scope.
They can only be compared against plans preserving the excluded geometry.
"""

from __future__ import annotations

from functools import lru_cache
from copy import deepcopy
import math

from almdina_erp.almdina_erp.domain.cutting.fragmentation import analysis_scales_cm
from almdina_erp.almdina_erp.domain.cutting.finished_piece_geometry import (
    resolve_finished_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature


@lru_cache(maxsize=256)
def _sheet_profile(width, height, contours, kerf, scales, rectangles):
    from shapely.geometry import Polygon, LineString, box
    from shapely.ops import unary_union
    from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
        cutter_center_paths,
    )

    polygons = [Polygon(outer, holes) for outer, holes in contours]
    if any(not p.is_valid or p.is_empty for p in polygons):
        return None
    board = box(0, 0, width, height)
    material = unary_union(polygons)
    # Remove the actual cutter-center network swept by the tool disk. Shared
    # paths are unioned once. This also preserves real opening/contour geometry.
    shapes_mm = [
        (
            [(x * 10, y * 10) for x, y in outer],
            [[(x * 10, y * 10) for x, y in ring] for ring in holes],
        )
        for outer, holes in contours
    ]
    paths = cutter_center_paths(shapes_mm, kerf * 5)
    swept = []
    if kerf > 0:
        for path in paths:
            points = [(x / 10, y / 10) for x, y in path.points]
            if path.closed:
                points.append(points[0])
            swept.append(LineString(points).buffer(kerf / 2))
    free = board.difference(unary_union([material, *swept]))

    def parts(geometry):
        if geometry.is_empty:
            return []
        if geometry.geom_type == "Polygon":
            return [geometry] if geometry.area > max(1e-8, kerf * kerf) else []
        return [p for g in getattr(geometry, "geoms", ()) for p in parts(g)]

    levels = []
    for scale in scales:
        radius = scale / 2
        opened = (
            free
            if radius == 0
            else free.buffer(-radius).buffer(radius).intersection(free)
        )
        regions = parts(opened)
        areas = [p.area for p in regions]
        accessible = [p.area for p in regions if p.distance(board.boundary) < 1e-6]
        levels.append(
            dict(
                scale_cm=scale,
                free_area_cm2=sum(areas),
                primary_area_cm2=max(areas, default=0.0),
                secondary_area_cm2=sum(areas) - max(areas, default=0.0),
                regions=len(areas),
                boundary_accessible_area_cm2=sum(accessible),
            )
        )
    # Shape compactness is diagnostic, separate from the alternative comparator.
    compactness = material.area / material.convex_hull.area if material.area else 1.0
    reusable = []
    accessible_regions = [p for p in parts(free) if p.distance(board.boundary) < 1e-6]
    for x, y, w, h in rectangles:
        # Inset the native empty rectangle on every side, then prove coverage
        # against actual material and swept kerf. This is a conservative
        # extractable rectangle lower bound, not a stock allocation.
        if w <= 2 * kerf or h <= 2 * kerf:
            continue
        rectangle = box(x + kerf, y + kerf, x + w - kerf, y + h - kerf)
        if any(region.covers(rectangle) for region in accessible_regions):
            reusable.append((rectangle.area, w - 2 * kerf, h - 2 * kerf))
    best_rectangle = max(reusable, default=(0.0, 0.0, 0.0))
    return dict(
        levels=levels,
        material_compactness=compactness,
        free_area_cm2=free.area,
        material_area_cm2=material.area,
        reusable_rectangle_lower_bound_cm2=best_rectangle[0],
        reusable_rectangle_size_cm=list(best_rectangle[1:]),
    )


def measure_fragmentation(plan, kerf):
    from almdina_erp.almdina_erp.domain.cutting.optimizer import (
        _free_rectangles_for_sheet,
    )

    if (
        not plan.get("sheets")
        or plan.get("unplaced")
        or not math.isfinite(kerf)
        or kerf < 0
    ):
        return None
    if len(plan["sheets"]) > 32:
        return None
    scales = analysis_scales_cm(plan, kerf)
    profiles, excluded = [], []
    for sheet in plan["sheets"]:
        if (
            (sheet.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
            or len(sheet.get("pieces") or ()) > 64
            or any(
                (p.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
                for p in sheet["pieces"]
            )
        ):
            return None
        contours = []
        for piece in sheet["pieces"]:
            geometry = resolve_finished_geometry_mm(
                stored_geometry=piece.get("geometry"), stored_piece=piece
            )
            if geometry is None:
                break
            outer = tuple((x / 10, y / 10) for x, y in geometry["outer"])
            holes = tuple(
                tuple((x / 10, y / 10) for x, y in ring)
                for ring in geometry.get("holes") or ()
            )
            contours.append((outer, holes))
        else:
            rectangles = tuple(
                sorted(
                    (r["x"], r["y"], r["w"], r["h"])
                    for r in _free_rectangles_for_sheet(sheet)
                )
            )
            result = _sheet_profile(
                float(sheet["w"]),
                float(sheet["h"]),
                tuple(sorted(contours)),
                kerf,
                scales,
                rectangles,
            )
            if result is None:
                return None
            profiles.append(deepcopy(result))
            continue
        excluded.append(geometry_signature(dict(sheets=[sheet])))
    if not profiles:
        return None
    levels = []
    for i, scale in enumerate(scales):
        fields = (
            "free_area_cm2",
            "primary_area_cm2",
            "secondary_area_cm2",
            "regions",
            "boundary_accessible_area_cm2",
        )
        levels.append(
            dict(
                scale_cm=scale,
                **{k: sum(p["levels"][i][k] for p in profiles) for k in fields},
            )
        )
    return dict(
        version=1,
        tier="material_opening",
        kerf_cm=kerf,
        levels=levels,
        scope=sorted(excluded),
        measured_sheets=len(profiles),
        total_sheets=len(plan["sheets"]),
        material_compactness=sum(p["material_compactness"] for p in profiles)
        / len(profiles),
        board_profiles=profiles,
    )
