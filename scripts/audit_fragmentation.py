"""Independent material/DXF audit at explicit analytical scales, without search."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
from itertools import combinations
import json
from pathlib import Path
import sys

import ezdxf
from shapely import affinity
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import polygonize, unary_union


def polygons(entities, layer):
    closed, edges = [], []
    for e in entities:
        if e.dxf.layer.upper() != layer:
            continue
        if e.dxftype() == "LWPOLYLINE":
            assert e.closed and all(abs(b) < 1e-8 for x, y, b in e.get_points("xyb"))
            closed.append(Polygon(e.get_points("xy")))
        elif e.dxftype() == "LINE":
            edges.append(LineString([tuple(e.dxf.start)[:2], tuple(e.dxf.end)[:2]]))
        else:
            raise ValueError((layer, e.dxftype()))
    return closed + list(polygonize(edges))


def read_dxf(path):
    doc = ezdxf.readfile(path)
    assert doc.units == 4
    entities = list(doc.modelspace())
    boards = polygons(entities, "SHEET_OUTLINE")
    boards.sort(key=lambda b: (round(b.bounds[1] / 2640), b.bounds[0]))
    shapes = polygons(entities, "GEOMETRY")
    labels = [
        (Point(tuple(e.dxf.insert)[:2]), int(e.dxf.text))
        for e in entities
        if e.dxftype() == "TEXT"
    ]
    result = []
    for board in boards:
        x, y = board.bounds[:2]
        parts = []
        for shape in shapes:
            if not board.buffer(0.02).covers(shape):
                continue
            matched = [n for point, n in labels if shape.covers(point)]
            if not matched:
                # polygonize also yields the inner face of closed machining
                # holes. Only the labelled material face is a manufactured part.
                continue
            assert len(matched) == 1, (path, shape.bounds, matched)
            parts.append((matched[0], affinity.translate(shape, -x, -y)))
        result.append((board.bounds[2] - x, board.bounds[3] - y, parts))
    assert sum(len(parts) for _, _, parts in result) == len(labels)
    return result


def snapshot_geometry(snapshot):
    from almdina_erp.almdina_erp.domain.cutting.finished_piece_geometry import (
        resolve_finished_geometry_mm,
    )

    result = []
    for sheet in snapshot["sheets"]:
        tx = sheet.get("applied_trim_width_cm", snapshot.get("trim_cm", 0)) * 10
        ty = sheet.get("applied_trim_length_cm", snapshot.get("trim_cm", 0)) * 10
        parts = []
        for p in sheet["pieces"]:
            geometry = resolve_finished_geometry_mm(
                stored_geometry=p.get("geometry"), stored_piece=p
            )
            if geometry is None:
                shape = box(
                    p["x"] * 10,
                    p["y"] * 10,
                    (p["x"] + p["w"]) * 10,
                    (p["y"] + p["h"]) * 10,
                )
            else:
                shape = Polygon(geometry["outer"], geometry.get("holes") or ())
            parts.append((p["source_piece_no"], affinity.translate(shape, tx, ty)))
        result.append(
            (
                snapshot["full_board_width_cm"] * 10,
                snapshot["full_board_length_cm"] * 10,
                parts,
            )
        )
    return result


def parts(geometry, min_area):
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > min_area else []
    return [p for g in getattr(geometry, "geoms", ()) for p in parts(g, min_area)]


def measure(layout, rows, trim, kerf, envelopes=False, reference_proxy=False):
    levels = {
        str(scale): dict(
            regions=0, secondary_m2=0.0, primary_m2=0.0, largest_m2=0.0, free_m2=0.0
        )
        for scale in (0, 25, 50, 100)
    }
    minimum = float("inf")
    overlap = 0
    minimum_margin = float("inf")
    inventory = Counter()
    dimensions = []
    for width, height, placed in layout:
        polygons = []
        for number, shape in placed:
            inventory[number] += 1
            row = rows[number]
            a, b, c, d = shape.bounds
            minimum_margin = min(minimum_margin, a, b, width - c, height - d)
            expected = sorted((row["cut_width_cm"] * 10, row["cut_length_cm"] * 10))
            if max(abs(v - e) for v, e in zip(sorted((c - a, d - b)), expected)) > 0.02:
                dimensions.append(number)
            polygons.append(
                box(*shape.bounds)
                if envelopes and row["piece_type"] == "Special"
                else shape
            )
        for a, b in combinations(polygons, 2):
            minimum = min(minimum, a.distance(b))
            overlap += a.intersection(b).area > 0.01
        inset = 0 if reference_proxy else trim
        radius = kerf / 2 if reference_proxy else kerf
        free = box(inset, inset, width - inset, height - inset).difference(
            unary_union([p.buffer(radius, join_style=2) for p in polygons])
        )
        for scale in (0, 25, 50, 100):
            join_style = 2 if reference_proxy else 1
            g = (
                free
                if scale == 0
                else free.buffer(-scale / 2, join_style=join_style)
                .buffer(scale / 2, join_style=join_style)
                .intersection(free)
            )
            areas = [
                p.area / 1e6 for p in parts(g, 2500 if reference_proxy else kerf * kerf)
            ]
            level = levels[str(scale)]
            level["regions"] += len(areas)
            level["free_m2"] += sum(areas)
            level["primary_m2"] += max(areas, default=0)
            level["secondary_m2"] += sum(areas) - max(areas, default=0)
            level["largest_m2"] = max(level["largest_m2"], max(areas, default=0))
    expected = Counter({n: r["qty"] for n, r in rows.items()})
    return dict(
        boards=len(layout),
        pieces=sum(inventory.values()),
        inventory_matches=inventory == expected,
        min_piece_gap_mm=minimum,
        min_trim_mm=minimum_margin,
        overlap_pairs=overlap,
        dimension_mismatches=dimensions,
        special_envelopes=envelopes,
        scales=levels,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=Path, nargs="*", default=[])
    parser.add_argument("--reference-proxy", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo))
    definition = (
        "physical board minus half-kerf envelope; area specks <=2500 mm2 excluded"
        if args.reference_proxy
        else "usable board minus full-kerf envelope; area specks <=kerf squared excluded"
    )
    result = dict(
        definition=definition,
        reference_proxy=args.reference_proxy,
        references={},
        runs={},
    )
    for case in ("488", "489", "499"):
        dco = json.loads(
            next(args.evidence.glob(f"DCO-26-00{case}*.json")).read_bytes()
        )
        rows = {r["piece_no"]: r for r in dco["pieces"]}
        diagnostic = json.loads(
            (args.evidence / f"SEARCH-DIAGNOSTICS-26-00{case}.json").read_bytes()
        )["plans"][0]
        trim = diagnostic["settings"]["trim_margin_mm"]
        kerf = diagnostic["settings"]["kerf_mm"]
        designer = (
            next(args.evidence.glob("488 *.dxf"))
            if case == "488"
            else args.evidence / f"{case}.dxf"
        )
        pair = {}
        for label, path in (
            (
                "system",
                args.evidence / f"cutting_plan_26-00{case}_AutoCAD2011_2026.dxf",
            ),
            ("designer", designer),
        ):
            layout = read_dxf(path)
            pair[label] = measure(
                layout,
                rows,
                trim,
                kerf,
                envelopes=True,
                reference_proxy=args.reference_proxy,
            )
            if case == "489":
                pair[label]["actual_contours"] = measure(
                    layout, rows, trim, kerf, reference_proxy=args.reference_proxy
                )
        result["references"][case] = pair
        for path in args.runs:
            run = json.loads(path.read_bytes())
            if run["case"] != dco["name"]:
                continue
            measured = [
                measure(
                    snapshot_geometry(snapshot),
                    rows,
                    trim,
                    kerf,
                    envelopes=True,
                    reference_proxy=args.reference_proxy,
                )
                for snapshot in run["gallery"]
            ]
            result["runs"][path.name] = dict(
                wall_sec=run["wall_sec"],
                gallery=measured,
                search=run["winner"].get("smart_search"),
            )
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(args.output, flush=True)


if __name__ == "__main__":
    main()
