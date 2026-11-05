"""Read-only, fail-closed rectangle evidence for the supplied ALNS study.

DXF text is data only. No machining, rotation permissions or original DCO
identities are inferred. Only SYSTEM dimensions feed search; designer poses
are retained exclusively for independent reference measurement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
from pathlib import Path

import ezdxf


def rectangle(edges):
    points = {tuple(round(float(v), 5) for v in p) for edge in edges for p in edge}
    if len(points) != 4 or len(edges) != 4:
        raise ValueError("Expected four rectangle edges")
    xs, ys = sorted({p[0] for p in points}), sorted({p[1] for p in points})
    if len(xs) != 2 or len(ys) != 2:
        raise ValueError("Only axis-aligned rectangles supported")
    expected = {frozenset(edge) for edge in [
        ((xs[0], ys[0]), (xs[1], ys[0])), ((xs[0], ys[1]), (xs[1], ys[1])),
        ((xs[0], ys[0]), (xs[0], ys[1])), ((xs[1], ys[0]), (xs[1], ys[1]))]}
    observed = {frozenset(tuple(round(float(v), 5) for v in p) for p in edge) for edge in edges}
    if observed != expected:
        raise ValueError("Invalid rectangle topology")
    return xs[0], ys[0], xs[1], ys[1]


def layer_rectangles(model, layer):
    result, lines = [], []
    for entity in model:
        if entity.dxf.layer != layer:
            continue
        if entity.dxftype() == "LWPOLYLINE":
            if not entity.closed or any(abs(p[4]) > 1e-10 for p in entity.get_points()):
                raise ValueError("Open/curved contour")
            points = [(p[0], p[1]) for p in entity.get_points()]
            # CAD may split a straight edge into several collinear segments.
            # Remove only interior collinear points, never a corner/notch.
            while len(points) > 4:
                for i, b in enumerate(points):
                    a, c = points[i-1], points[(i+1) % len(points)]
                    cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                    if abs(cross) < 1e-7 and all(min(a[j], c[j])-1e-8 <= b[j] <= max(a[j], c[j])+1e-8 for j in (0, 1)):
                        points.pop(i)
                        break
                else:
                    raise ValueError("Nonrectangular contour")
            result.append(rectangle(list(zip(points, points[1:] + points[:1]))))
        elif entity.dxftype() == "LINE":
            if abs(entity.dxf.start.z) > 1e-8 or abs(entity.dxf.end.z) > 1e-8:
                raise ValueError("Nonplanar LINE")
            lines.append((tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]))
        else:
            raise ValueError(f"Unsupported {entity.dxftype()} on {layer}")
    # Group by connected endpoints, independent of entity serialization order.
    by_point = defaultdict(set)
    for i, edge in enumerate(lines):
        for point in edge:
            by_point[tuple(round(v, 5) for v in point)].add(i)
    remaining = set(range(len(lines)))
    while remaining:
        component, pending = set(), [min(remaining)]
        while pending:
            i = pending.pop()
            if i in component:
                continue
            component.add(i)
            for point in lines[i]:
                pending.extend(by_point[tuple(round(v, 5) for v in point)] - component)
        remaining -= component
        result.append(rectangle([lines[i] for i in sorted(component)]))
    return result


def family(rect):
    return tuple(sorted((round(rect[2]-rect[0], 3), round(rect[3]-rect[1], 3))))


def read_layout(path):
    doc = ezdxf.readfile(path)
    if doc.units != 4:
        raise ValueError(f"Expected millimetres, INSUNITS={doc.units}")
    model = doc.modelspace()
    if any(e.dxf.layer == "OFFCUT" for e in model):
        raise ValueError("OFFCUT requires an explicit source contract")
    boards = layer_rectangles(model, "SHEET_OUTLINE")
    pieces = layer_rectangles(model, "GEOMETRY")
    if not boards or not pieces:
        raise ValueError("Missing boards/pieces")
    assigned = [[] for _ in boards]
    for piece in pieces:
        matches = [i for i, b in enumerate(boards) if b[0]-1e-4 <= piece[0]
                   and b[1]-1e-4 <= piece[1] and piece[2] <= b[2]+1e-4 and piece[3] <= b[3]+1e-4]
        if len(matches) != 1:
            raise ValueError("Piece lacks unique containing board")
        assigned[matches[0]].append(piece)
    if any(not group for group in assigned):
        raise ValueError("Empty outline in input")
    gaps, overlaps, edge_gaps = [], 0, []
    normalized = []
    for board, group in zip(boards, assigned):
        located = []
        for i, p in enumerate(group):
            edge_gaps.append(min(p[0]-board[0], p[1]-board[1], board[2]-p[2], board[3]-p[3]))
            located.append(dict(x=(p[0]-board[0])/10, y=(p[1]-board[1])/10,
                                w=(p[2]-p[0])/10, h=(p[3]-p[1])/10))
            for q in group[i+1:]:
                dx, dy = max(p[0]-q[2], q[0]-p[2]), max(p[1]-q[3], q[1]-p[3])
                overlaps += dx < -1e-4 and dy < -1e-4
                gaps.append(math.hypot(max(0, dx), max(0, dy)))
        normalized.append(dict(w=(board[2]-board[0])/10, h=(board[3]-board[1])/10, pieces=located))
    inventory = Counter(family(p) for p in pieces)
    area = sum((p[2]-p[0])*(p[3]-p[1]) for p in pieces)/1e6
    board_sizes = sorted({family(b) for b in boards})
    stock = sum((b[2]-b[0])*(b[3]-b[1]) for b in boards)/1e6
    return dict(sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        filename=Path(path).name, pieces=len(pieces), boards=len(boards),
        board_sizes_mm=board_sizes, area_m2=area, stock_m2=stock,
        area_lower_bound=math.ceil(area/(board_sizes[0][0]*board_sizes[0][1]/1e6)-1e-10)
            if len(board_sizes) == 1 else None,
        inventory=[[*size, count] for size, count in sorted(inventory.items())],
        board_counts=[len(g) for g in assigned], overlap_pairs=overlaps,
        min_pair_gap_mm=min(gaps, default=None), min_edge_gap_mm=min(edge_gaps),
        layout=dict(sheets=normalized, unplaced=[]))


def paired_inputs(system, designer):
    system, designer = read_layout(system), read_layout(designer)
    if system["inventory"] != designer["inventory"] or system["board_sizes_mm"] != designer["board_sizes_mm"]:
        raise ValueError("Reference inventories/stock differ")
    if system["overlap_pairs"] or designer["overlap_pairs"]:
        raise ValueError("Overlapping reference pieces")
    width, height = system["board_sizes_mm"][0]
    rows = [dict(width_cm=w/10, length_cm=h/10, qty=q, allow_rotation=1,
                 piece_type="Regular", piece_instance_id=f"smart:{i}")
            for i, (w, h, q) in enumerate(system["inventory"], 1)]
    return dict(system=system, designer=designer, width=width/10, height=height/10, rows=rows,
                provenance="SYSTEM DXF dimension multiset; synthetic IDs, canonical source axes/order; all rotations ASSUMED; no original DCO machining/settings")
