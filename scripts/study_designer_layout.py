"""Read-only polygon audit of designer/system DXFs; never seed from a designer.

Layer names are an explicit comparison convention, not a production importer
change. Only system contours supply search dimensions. Text is ignored.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import LinerPiece, piece_polygon_mm
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygon_area, has_self_intersection
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import plan_cut_line_quality


def contours(model, layer):
    polygons, adjacent = [], defaultdict(list)
    for entity in model:
        if entity.dxf.layer != layer:
            continue
        if entity.dxftype() == "LWPOLYLINE":
            if not entity.closed or any(abs(p[4]) > 1e-8 for p in entity.get_points()):
                raise ValueError("Open or curved contour")
            polygons.append([(float(p[0]), float(p[1])) for p in entity.get_points()])
        elif entity.dxftype() == "LINE":
            if any(abs(p.z) > 1e-8 for p in (entity.dxf.start, entity.dxf.end)):
                raise ValueError("Nonplanar contour")
            a, b = [tuple(round(c, 5) for c in tuple(p)[:2])
                    for p in (entity.dxf.start, entity.dxf.end)]
            adjacent[a].append(b)
            adjacent[b].append(a)
        else:
            raise ValueError("Unsupported contour entity")
    if any(len(neighbors) != 2 for neighbors in adjacent.values()):
        raise ValueError("Open, shared or branched contour")
    remaining = set(adjacent)
    while remaining:
        start = min(remaining)
        previous, current, polygon = None, start, []
        while current not in polygon:
            polygon.append(current)
            following = next(v for v in adjacent[current] if v != previous)
            previous, current = current, following
        if current != start:
            raise ValueError("Contour does not close")
        remaining.difference_update(polygon)
        polygons.append(polygon)
    for polygon in polygons:
        if len(polygon) not in (4, 5, 6) or has_self_intersection(polygon):
            raise ValueError("Unsupported/self-intersecting polygon")
    return polygons


def bounds(polygon):
    xs, ys = zip(*polygon)
    return min(xs), min(ys), max(xs), max(ys)


def normalized(polygon):
    x, y, _, _ = bounds(polygon)
    return tuple(sorted((round(a-x, 3), round(b-y, 3)) for a, b in polygon))


def canonical(polygon, *, mirror):
    variants = []
    for flip in ((1, -1) if mirror else (1,)):
        points = [(flip*x, y) for x, y in polygon]
        for _ in range(4):
            variants.append(normalized(points))
            points = [(-y, x) for x, y in points]
    return min(variants, key=lambda p: (bounds(p)[2:], p))


def row_for_polygon(polygon):
    points = normalized(polygon)
    _, _, w, h = bounds(points)
    row = dict(width_cm=w/10, length_cm=h/10, piece_type="Regular", qty=1, allow_rotation=1)
    if len(points) == 4:
        if set(points) != {(0, 0), (w, 0), (w, h), (0, h)}:
            raise ValueError("Nonrectangular four-vertex contour")
        return row
    kind = "Clipped Corner" if len(points) == 5 else "L-Shaped Corner"
    xs = {round(v, 3) for x, _ in points for v in (x, w-x) if 0 < v < w}
    ys = {round(v, 3) for _, y in points for v in (y, h-y) if 0 < v < h}
    for position in ("Top Right", "Top Left", "Bottom Right", "Bottom Left"):
        for cx in sorted(xs):
            for cy in sorted(ys):
                shape = LinerPiece(kind, w/10, h/10, position, cx/10, cy/10)
                if normalized(piece_polygon_mm(shape)) == points:
                    return dict(row, piece_type=kind, clipped_corner_position=position,
                                clipped_corner_width_cm=cx/10, clipped_corner_length_cm=cy/10)
    raise ValueError("Polygon is not a supported parametric corner")


def read_layout(path, layer):
    document = ezdxf.readfile(path)
    if document.units != 4:
        raise ValueError("Expected millimetres")
    model = document.modelspace()
    outlines, pieces = contours(model, "SHEET_OUTLINE"), contours(model, layer)
    if not outlines or not pieces:
        raise ValueError("Missing sheets or material contours")
    sheets = []
    for outline in outlines:
        row_for_polygon(outline)
        x0, y0, x1, y1 = bounds(outline)
        sheets.append(dict(w=round((x1-x0)/10, 5), h=round((y1-y0)/10, 5), pieces=[]))
    for index, polygon in enumerate(pieces, 1):
        x0, y0, x1, y1 = bounds(polygon)
        matches = [i for i, b in enumerate(map(bounds, outlines))
                   if b[0]-.01 <= x0 and b[1]-.01 <= y0 and x1 <= b[2]+.01 and y1 <= b[3]+.01]
        if len(matches) != 1:
            raise ValueError("Material contour lacks a unique containing sheet")
        i = matches[0]
        bx, by, _, _ = bounds(outlines[i])
        row = row_for_polygon(polygon)
        sheets[i]["pieces"].append(dict(row, id=index, x=(x0-bx)/10, y=(y0-by)/10,
            w=(x1-x0)/10, h=(y1-y0)/10, rotated=False,
            placement_outline_cm=[[(x-bx)/10, (y-by)/10] for x, y in polygon]))
    if any(not sheet["pieces"] for sheet in sheets):
        raise ValueError("Empty reference sheet")
    plan = enrich_plan_metrics(dict(sheets=sheets, unplaced=[]), "DXF reference", "CNC Router",
        min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09)
    plan.update(kerf_cm=.5, machine_type="CNC Router")
    return dict(sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), layer=layer,
        pieces=len(pieces), boards=len(sheets), kinds=dict(Counter(p["piece_type"] for s in sheets for p in s["pieces"])),
        area_m2=sum(abs(polygon_area(p)) for p in pieces)/1e6,
        inventory_bounds=dict(Counter(str((len(p), *sorted((round(bounds(p)[2]-bounds(p)[0], 3),
            round(bounds(p)[3]-bounds(p)[1], 3))))) for p in pieces)),
        cut_profile=plan_cut_line_quality(plan, .5),
        largest_remnant_m2=plan["industrial_metrics"]["largest_reusable_free_area_m2"],
        polygons=pieces, plan=plan)


def paired_inputs(system_path, designer_path):
    system, designer = read_layout(system_path, "GEOMETRY"), read_layout(designer_path, "CUT_PATH")
    if system["inventory_bounds"] != designer["inventory_bounds"]:
        raise ValueError("Material bounding-size inventories differ")
    sizes = {(s["w"], s["h"]) for s in system["plan"]["sheets"] + designer["plan"]["sheets"]}
    if len(sizes) != 1:
        raise ValueError("Stock dimensions differ")
    inventory = Counter(canonical(p, mirror=True) for p in system["polygons"])
    rows = [dict(row_for_polygon(polygon), qty=count, piece_instance_id=f"smart:{i}")
            for i, (polygon, count) in enumerate(sorted(inventory.items()), 1)]
    return dict(width=next(iter(sizes))[0], height=next(iter(sizes))[1], rows=rows,
        system=system, designer=designer,
        exact_shape_inventory_equal=(inventory == Counter(canonical(p, mirror=True) for p in designer["polygons"])),
        assumptions=dict(kerf_mm=5, trim_mm=0, machine="CNC Router", allow_rotation=True,
            allow_mirroring=True, no_original_DCO_ids_or_machining=True,
            reference_layer="CUT_PATH treated as material GEOMETRY at user request; layer 0 excluded"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True)
    parser.add_argument("--designer", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError("Use fresh evidence output")
    result = paired_inputs(args.system, args.designer)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: {m: v for m, v in result[k].items() if m not in {"polygons", "plan"}}
                     for k in ("system", "designer")}, indent=2))
    print("exact_shape_inventory_equal", result["exact_shape_inventory_equal"])


if __name__ == "__main__":
    main()
