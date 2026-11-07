"""Session-local snap suggestions for Board Editor piece moves.

Screen-pixel thresholds are converted by the caller (8px enter / 12px exit).
Final placement authority remains validate_piece_drop / apply_piece_move.
AABB is used only to pre-filter nearby targets; acceptance uses real footprints.
"""

from __future__ import annotations

from math import atan2, hypot
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    _world_footprint,
    validate_piece_drop,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import num

SNAP_ENTER_PX = 8.0
SNAP_EXIT_PX = 12.0

_EPS = 1e-6
_AXIS_RATIO = 25.0


def _bounds_corners(bounds: Mapping[str, float]) -> list[list[float]]:
    x = num(bounds["x"])
    y = num(bounds["y"])
    w = num(bounds["w"])
    h = num(bounds["h"])
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def footprint_edges(footprint: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return edge descriptors; ``side`` is min/max along the snap axis."""

    bounds = footprint["bounds"]
    points = footprint.get("points")
    if not (isinstance(points, list) and len(points) >= 3):
        points = _bounds_corners(bounds)
    edges: list[dict[str, Any]] = []
    count = len(points)
    min_x, max_x = num(bounds["x"]), num(bounds["x"]) + num(bounds["w"])
    min_y, max_y = num(bounds["y"]), num(bounds["y"]) + num(bounds["h"])
    for index in range(count):
        a = [num(points[index][0]), num(points[index][1])]
        b = [num(points[(index + 1) % count][0]), num(points[(index + 1) % count][1])]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        length = hypot(dx, dy)
        if length <= _EPS:
            continue
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        if abs(dx) >= abs(dy) * _AXIS_RATIO:
            kind = "h"
            coord = (a[1] + b[1]) * 0.5
            side = "min" if abs(coord - min_y) <= abs(coord - max_y) else "max"
        elif abs(dy) >= abs(dx) * _AXIS_RATIO:
            kind = "v"
            coord = (a[0] + b[0]) * 0.5
            side = "min" if abs(coord - min_x) <= abs(coord - max_x) else "max"
        else:
            kind = "d"
            coord = 0.0
            side = "n"
        edges.append(
            {
                "a": a,
                "b": b,
                "kind": kind,
                "side": side,
                "ux": ux,
                "uy": uy,
                "nx": nx,
                "ny": ny,
                "length": length,
                "angle": atan2(dy, dx),
                "coord": coord,
                "mid": [(a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5],
            }
        )
    return edges


def usable_edges_world(board: Mapping[str, Any]) -> list[dict[str, Any]]:
    ox = num(board.get("origin_x_mm")) + num(board.get("trim_x_mm"))
    oy = num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))
    w = num(board.get("usable_width_mm")) or num(board.get("width_mm"))
    h = num(board.get("usable_length_mm")) or num(board.get("height_mm"))
    return footprint_edges(
        {
            "kind": "rect",
            "bounds": {"x": ox, "y": oy, "w": w, "h": h},
            "points": None,
        }
    )


def _parallel(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if a["kind"] in {"h", "v"} and b["kind"] in {"h", "v"}:
        return a["kind"] == b["kind"]
    ang = abs(a["angle"] - b["angle"]) % 3.141592653589793
    if ang > 1.5707963267948966:
        ang = 3.141592653589793 - ang
    return ang < 0.07


def _edge_delta(moving: Mapping[str, Any], target: Mapping[str, Any], gap: float) -> tuple[float, float] | None:
    """Translation applied to the already-raw-shifted moving edges."""

    if moving["kind"] == "v" and target["kind"] == "v":
        if gap <= _EPS:
            # Usable flush: min↔min (left), max↔max (right).
            if moving["side"] != target["side"]:
                return None
            return (num(target["coord"]) - num(moving["coord"]), 0.0)
        # Piece facing: moving min against target max (+kerf), or max against min.
        if moving["side"] == "min" and target["side"] == "max":
            return (num(target["coord"]) + gap - num(moving["coord"]), 0.0)
        if moving["side"] == "max" and target["side"] == "min":
            return (num(target["coord"]) - gap - num(moving["coord"]), 0.0)
        return None
    if moving["kind"] == "h" and target["kind"] == "h":
        if gap <= _EPS:
            if moving["side"] != target["side"]:
                return None
            return (0.0, num(target["coord"]) - num(moving["coord"]))
        if moving["side"] == "min" and target["side"] == "max":
            return (0.0, num(target["coord"]) + gap - num(moving["coord"]))
        if moving["side"] == "max" and target["side"] == "min":
            return (0.0, num(target["coord"]) - gap - num(moving["coord"]))
        return None
    if moving["kind"] == "d" and target["kind"] == "d" and _parallel(moving, target):
        nx, ny = num(target["nx"]), num(target["ny"])
        residual = (
            (num(moving["mid"][0]) - num(target["mid"][0])) * nx
            + (num(moving["mid"][1]) - num(target["mid"][1])) * ny
        )
        desired = gap if residual >= 0 else -gap
        delta = desired - residual
        return (nx * delta, ny * delta)
    return None


_ALIGN_MODE_RANK = {
    "top": 1.0,
    "left": 1.0,
    "bottom": 1.25,
    "right": 1.25,
    "centerX": 2.0,
    "centerY": 2.0,
}


def _candidate_key(
    dx: float,
    dy: float,
    source: str,
    side: str,
    rank: float = 0.0,
) -> tuple:
    return (
        abs(dx) + abs(dy),
        float(rank),
        abs(dx),
        abs(dy),
        source,
        side,
        round(dx, 6),
        round(dy, 6),
    )


def _guide(moving: Mapping[str, Any], target: Mapping[str, Any], dx: float, dy: float) -> dict[str, Any]:
    return {
        "kind": "edge",
        "x1": num(target["a"][0]),
        "y1": num(target["a"][1]),
        "x2": num(target["b"][0]),
        "y2": num(target["b"][1]),
        "mx1": num(moving["a"][0]) + dx,
        "my1": num(moving["a"][1]) + dy,
        "mx2": num(moving["b"][0]) + dx,
        "my2": num(moving["b"][1]) + dy,
    }


def _aabb_metrics(bounds: Mapping[str, float]) -> dict[str, float]:
    min_x = num(bounds["x"])
    min_y = num(bounds["y"])
    max_x = min_x + num(bounds["w"])
    max_y = min_y + num(bounds["h"])
    return {
        "minX": min_x,
        "minY": min_y,
        "maxX": max_x,
        "maxY": max_y,
        "centerX": (min_x + max_x) * 0.5,
        "centerY": (min_y + max_y) * 0.5,
    }


def _same_sheet_scope(a: Any, b: Any) -> bool:
    left = None if a is None or a == "" else str(a)
    right = None if b is None or b == "" else str(b)
    return left == right


def _alignment_guide(
    mode: str,
    moving_bounds: Mapping[str, float],
    target_bounds: Mapping[str, float],
    dx: float,
    dy: float,
    source_piece_key: Any,
    target_piece_key: Any,
) -> dict[str, Any]:
    moving = _aabb_metrics(
        {
            "x": num(moving_bounds["x"]) + dx,
            "y": num(moving_bounds["y"]) + dy,
            "w": moving_bounds["w"],
            "h": moving_bounds["h"],
        }
    )
    target = _aabb_metrics(target_bounds)
    if mode in {"top", "bottom", "centerY"}:
        y = target["minY"] if mode == "top" else (
            target["maxY"] if mode == "bottom" else target["centerY"]
        )
        x1 = min(moving["minX"], target["minX"])
        x2 = max(moving["maxX"], target["maxX"])
        return {
            "kind": "alignment",
            "mode": mode,
            "sourcePieceKey": source_piece_key,
            "targetPieceKey": target_piece_key,
            "x1": x1,
            "y1": y,
            "x2": x2,
            "y2": y,
        }
    x = target["minX"] if mode == "left" else (
        target["maxX"] if mode == "right" else target["centerX"]
    )
    y1 = min(moving["minY"], target["minY"])
    y2 = max(moving["maxY"], target["maxY"])
    return {
        "kind": "alignment",
        "mode": mode,
        "sourcePieceKey": source_piece_key,
        "targetPieceKey": target_piece_key,
        "x1": x,
        "y1": y1,
        "x2": x,
        "y2": y2,
    }


def _alignment_deltas(
    moving_bounds: Mapping[str, float],
    target_bounds: Mapping[str, float],
) -> list[dict[str, Any]]:
    moving = _aabb_metrics(moving_bounds)
    target = _aabb_metrics(target_bounds)
    return [
        {"mode": "top", "axis": "y", "dx": 0.0, "dy": target["minY"] - moving["minY"]},
        {"mode": "bottom", "axis": "y", "dx": 0.0, "dy": target["maxY"] - moving["maxY"]},
        {"mode": "left", "axis": "x", "dx": target["minX"] - moving["minX"], "dy": 0.0},
        {"mode": "right", "axis": "x", "dx": target["maxX"] - moving["maxX"], "dy": 0.0},
        {"mode": "centerX", "axis": "x", "dx": target["centerX"] - moving["centerX"], "dy": 0.0},
        {"mode": "centerY", "axis": "y", "dx": 0.0, "dy": target["centerY"] - moving["centerY"]},
    ]


def _aabb_near(a: Mapping[str, float], b: Mapping[str, float], pad: float) -> bool:
    return not (
        b["x"] - pad >= a["x"] + a["w"] + pad
        or b["x"] + b["w"] + pad <= a["x"] - pad
        or b["y"] - pad >= a["y"] + a["h"] + pad
        or b["y"] + b["h"] + pad <= a["y"] - pad
    )


def suggest_piece_snap(
    *,
    piece: Mapping[str, Any],
    pieces: Mapping[str, Mapping[str, Any]],
    boards: Mapping[str, Mapping[str, Any]],
    world_x_mm: float,
    world_y_mm: float,
    kerf_mm: float = 0.0,
    threshold_mm: float = 8.0,
    exit_threshold_mm: float | None = None,
    active_snap: Mapping[str, Any] | None = None,
    magnet_enabled: bool = True,
) -> dict[str, Any]:
    if not magnet_enabled or not piece.get("editable"):
        return {"ok": False, "dx": 0.0, "dy": 0.0, "guides": [], "source": None}

    exit_mm = num(exit_threshold_mm) if exit_threshold_mm is not None else num(threshold_mm) * 1.5
    current = _world_footprint(piece, boards)
    raw_dx = num(world_x_mm) - current["bounds"]["x"]
    raw_dy = num(world_y_mm) - current["bounds"]["y"]

    if active_snap and active_snap.get("ok"):
        adx = num(active_snap.get("dx"))
        ady = num(active_snap.get("dy"))
        if hypot(raw_dx - adx, raw_dy - ady) <= exit_mm:
            check = validate_piece_drop(
                piece=piece,
                pieces=pieces,
                boards=boards,
                world_x_mm=current["bounds"]["x"] + adx,
                world_y_mm=current["bounds"]["y"] + ady,
                kerf_mm=kerf_mm,
            )
            if check.get("ok"):
                return {
                    "ok": True,
                    "dx": adx,
                    "dy": ady,
                    "guides": list(active_snap.get("guides") or []),
                    "source": active_snap.get("source") or "sticky",
                }

    proposed = {
        "kind": current["kind"],
        "bounds": {
            "x": current["bounds"]["x"] + raw_dx,
            "y": current["bounds"]["y"] + raw_dy,
            "w": current["bounds"]["w"],
            "h": current["bounds"]["h"],
        },
        "points": (
            [[p[0] + raw_dx, p[1] + raw_dy] for p in current["points"]]
            if current.get("points")
            else None
        ),
    }

    near_boards: list[str] = []
    for sheet_no, board in boards.items():
        ox = num(board.get("origin_x_mm")) + num(board.get("trim_x_mm"))
        oy = num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))
        uw = num(board.get("usable_width_mm")) or num(board.get("width_mm"))
        uh = num(board.get("usable_length_mm")) or num(board.get("height_mm"))
        usable = {"x": ox, "y": oy, "w": uw, "h": uh}
        if _aabb_near(proposed["bounds"], usable, num(threshold_mm)):
            near_boards.append(str(sheet_no))

    unique_board = near_boards[0] if len(near_boards) == 1 else None
    piece_sheet = piece.get("sheet_no")
    sheet_scope = (
        str(unique_board)
        if unique_board is not None
        else (None if piece_sheet is None or piece_sheet == "" else str(piece_sheet))
    )

    moving_edges = footprint_edges(proposed) if unique_board is not None else []
    targets: list[tuple[str, dict[str, Any], float]] = []
    if unique_board is not None:
        targets.extend(
            ("usable", edge, 0.0) for edge in usable_edges_world(boards[unique_board])
        )

    piece_key = piece.get("piece_key")
    moving_keys = {piece_key}
    moving_keys.update(
        key for key, other in pieces.items() if other.get("glass_host_key") == piece_key
    )
    pad = num(threshold_mm) + max(proposed["bounds"]["w"], proposed["bounds"]["h"])
    nearby_pieces: list[tuple[str, Mapping[str, Any]]] = []
    for other_key, other in pieces.items():
        if other_key in moving_keys:
            continue
        if other.get("distribution") == "excluded":
            continue
        if not _same_sheet_scope(other.get("sheet_no"), sheet_scope):
            continue
        if other.get("glass_host_key") == piece_key or piece.get("glass_host_key") == other_key:
            continue
        other_fp = _world_footprint(other, boards)
        if not _aabb_near(proposed["bounds"], other_fp["bounds"], pad):
            continue
        nearby_pieces.append((other_key, other_fp))
        if unique_board is not None:
            for edge in footprint_edges(other_fp):
                targets.append((f"piece:{other_key}", edge, num(kerf_mm)))

    axis_candidates: dict[str, list[dict[str, Any]]] = {"x": [], "y": [], "n": []}
    for source, target_edge, gap in targets:
        for moving_edge in moving_edges:
            if not _parallel(moving_edge, target_edge):
                continue
            delta = _edge_delta(moving_edge, target_edge, gap)
            if delta is None:
                continue
            dx, dy = delta
            if hypot(dx, dy) > num(threshold_mm) + _EPS:
                continue
            abs_dx = raw_dx + dx
            abs_dy = raw_dy + dy
            axis = "x" if abs(dy) <= _EPS and abs(dx) > _EPS else (
                "y" if abs(dx) <= _EPS and abs(dy) > _EPS else "n"
            )
            axis_candidates[axis].append(
                {
                    "dx": abs_dx,
                    "dy": abs_dy,
                    "source": source,
                    "guide": _guide(moving_edge, target_edge, dx, dy),
                    "key": _candidate_key(abs_dx, abs_dy, source, axis, 0.0),
                }
            )

    for other_key, other_fp in nearby_pieces:
        for row in _alignment_deltas(proposed["bounds"], other_fp["bounds"]):
            rel = hypot(row["dx"], row["dy"])
            if rel <= _EPS or rel > num(threshold_mm) + _EPS:
                continue
            abs_dx = raw_dx + row["dx"]
            abs_dy = raw_dy + row["dy"]
            source = f"align:{row['mode']}:{other_key}"
            guide_row = _alignment_guide(
                row["mode"],
                proposed["bounds"],
                other_fp["bounds"],
                row["dx"],
                row["dy"],
                piece_key,
                other_key,
            )
            rank = _ALIGN_MODE_RANK.get(row["mode"], 1.0)
            axis_candidates[row["axis"]].append(
                {
                    "dx": abs_dx,
                    "dy": abs_dy,
                    "source": source,
                    "guide": guide_row,
                    "key": _candidate_key(abs_dx, abs_dy, source, row["axis"], rank),
                }
            )

    def first_valid(cands: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
        for row in sorted(cands, key=lambda item: item["key"]):
            check = validate_piece_drop(
                piece=piece,
                pieces=pieces,
                boards=boards,
                world_x_mm=current["bounds"]["x"] + row["dx"],
                world_y_mm=current["bounds"]["y"] + row["dy"],
                kerf_mm=kerf_mm,
            )
            if not check.get("ok"):
                continue
            guides = row.get("guides") or [row["guide"]]
            return {
                "ok": True,
                "dx": row["dx"],
                "dy": row["dy"],
                "guides": guides,
                "source": row["source"],
            }
        return None

    combined: list[dict[str, Any]] = []
    for x_row in sorted(axis_candidates["x"], key=lambda row: row["key"])[:4]:
        for y_row in sorted(axis_candidates["y"], key=lambda row: row["key"])[:4]:
            dx = x_row["dx"]
            dy = y_row["dy"]
            if hypot(dx - raw_dx, dy - raw_dy) > num(threshold_mm) * 1.5 + _EPS:
                continue
            combined.append(
                {
                    "dx": dx,
                    "dy": dy,
                    "source": f"{x_row['source']}+{y_row['source']}",
                    "guide": x_row["guide"],
                    "guides": [x_row["guide"], y_row["guide"]],
                    "key": _candidate_key(dx, dy, "combined", "xy"),
                }
            )
    found = first_valid(combined)
    if found:
        return found
    for axis in ("x", "y", "n"):
        found = first_valid(axis_candidates[axis])
        if found:
            return found
    return {"ok": False, "dx": raw_dx, "dy": raw_dy, "guides": [], "source": None}


__all__ = [
    "SNAP_ENTER_PX",
    "SNAP_EXIT_PX",
    "footprint_edges",
    "usable_edges_world",
    "suggest_piece_snap",
]
