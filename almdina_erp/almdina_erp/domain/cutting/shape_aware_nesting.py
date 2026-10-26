"""Place complementary L and clipped-corner outlines after the base pack.

MaxRects, Guillotine, Shelf, and Skyline stay the packing engines. This pass
only rewrites a plan when four matching corners can face a shared void and the
resulting layout uses fewer boards without an overlap or a kerf fault.

Mirror orientations are tried only when the caller says mirroring is allowed.
One non-quarter angle is stored, and only for a rectangle sitting in the void
of four clipped corners. The angle is the direction of that void edge.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .dxf_geometry import polygon_distance, polygons_overlap
from .glass_opening_nesting import material_outline_cm
from .primitives import make_placed_piece, num, orientations_for

_CORNER_TYPES = frozenset({"Clipped Corner", "L-Shaped Corner"})
_TURN = {
    "Top Left": "Top Right",
    "Top Right": "Bottom Right",
    "Bottom Right": "Bottom Left",
    "Bottom Left": "Top Left",
}
_MIRROR = {
    "Top Left": "Top Right",
    "Top Right": "Top Left",
    "Bottom Left": "Bottom Right",
    "Bottom Right": "Bottom Left",
}
# Column, row in a 2×2 cluster whose missing corner faces the centre.
_SLOTS = (
    ("Bottom Right", 0, 0),
    ("Bottom Left", 1, 0),
    ("Top Right", 0, 1),
    ("Top Left", 1, 1),
)


def void_edge_angle_deg(cut_width_cm: float, cut_length_cm: float) -> float | None:
    """Angle of a clipped-corner void edge, measured from the width axis."""

    if cut_width_cm <= 0 or cut_length_cm <= 0:
        return None
    return math.degrees(math.atan2(cut_length_cm, cut_width_cm)) % 360.0


def non_quarter_rotation_is_admitted(
    rotation_deg: float,
    *,
    cut_width_cm: float,
    cut_length_cm: float,
    outline_inside_void: bool,
    tolerance_deg: float = 0.05,
) -> bool:
    """Allow one computed angle, and only together with a proven void.

    A DXF angle is not admitted merely because the file contains it. Quarter
    turns are outside this exception.
    """

    if not outline_inside_void:
        return False
    expected = void_edge_angle_deg(cut_width_cm, cut_length_cm)
    if expected is None:
        return False
    if abs(rotation_deg % 90.0) <= tolerance_deg:
        return False
    return _angle_close(rotation_deg, expected, tolerance_deg) or _angle_close(
        rotation_deg, expected + 180.0, tolerance_deg
    )


def apply_shape_aware_nesting(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
    machine_type: str,
    time_limit_sec: float,
    min_remnant_width_cm: float,
    min_remnant_length_cm: float,
    min_remnant_area_m2: float,
) -> dict[str, Any]:
    """Return a smaller valid cluster layout, or the plan unchanged."""

    if machine_type == "Panel Saw" or time_limit_sec <= 0 or plan.get("unplaced"):
        return plan
    if len(plan.get("sheets") or []) < 2:
        return plan
    built = _cluster_sheet(
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        mirroring_allowed=mirroring_allowed,
    )
    if built is None:
        return plan
    sheet, used_ids = built
    from .evaluation import validate_plan
    from .optimizer import enrich_plan_metrics
    from .registry import METHOD_CONFIGS, run_single_method

    remainder = [piece for piece in pieces if int(piece["id"]) not in used_ids]
    sheets = [sheet]
    if remainder:
        method_key = str(plan.get("method_key") or "")
        if method_key not in METHOD_CONFIGS:
            method_key = "MaxRects Best Short Side"
        packed = run_single_method(
            remainder, board_w_cm, board_h_cm, kerf_cm, method_key
        )
        if packed.get("unplaced"):
            return plan
        extra = list(packed.get("sheets") or [])
        for index, extra_sheet in enumerate(extra, start=2):
            extra_sheet["sheet_no"] = index
        sheets.extend(extra)
    if len(sheets) >= len(plan.get("sheets") or []):
        return plan
    candidate = {
        "sheets": sheets,
        "unplaced": [],
        "method_key": plan.get("method_key") or "",
        "method_label": plan.get("method_label") or "",
        "optimization_mode": plan.get("optimization_mode") or "",
        "ordering_strategy": plan.get("ordering_strategy") or "",
        "attempts": plan.get("attempts") or 1,
        "complexity": plan.get("complexity") or 0,
    }
    candidate = enrich_plan_metrics(
        candidate,
        str(candidate.get("method_key") or "MaxRects Best Short Side"),
        machine_type,
        min_remnant_width_cm=min_remnant_width_cm,
        min_remnant_length_cm=min_remnant_length_cm,
        min_remnant_area_m2=min_remnant_area_m2,
    )
    if validate_plan(candidate, pieces, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
        return plan
    for key in (
        "search_elapsed_sec",
        "search_time_limit_sec",
        "solver_status",
        "solver_wall_time_sec",
        "glass_nesting_diagnostics",
    ):
        if key in plan:
            candidate[key] = plan[key]
    return candidate


def _cluster_sheet(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> tuple[dict[str, Any], set[int]] | None:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for piece in pieces:
        kind = str(piece.get("piece_type") or "")
        if kind not in _CORNER_TYPES:
            continue
        key = (
            kind,
            round(num(piece.get("width_cm")), 4),
            round(num(piece.get("length_cm")), 4),
            round(num(piece.get("clipped_corner_width_cm")), 4),
            round(num(piece.get("clipped_corner_length_cm")), 4),
        )
        if key[1] <= 0 or key[2] <= 0 or key[3] <= 0 or key[4] <= 0:
            continue
        groups.setdefault(key, []).append(piece)
    for key, group in groups.items():
        if len(group) < 4:
            continue
        chosen = list(group[:4])
        placed = _assign_cluster(
            chosen,
            kerf_cm,
            mirroring_allowed=mirroring_allowed,
        )
        if placed is None:
            continue
        width, height = key[1], key[2]
        cluster_w = width * 2 + kerf_cm
        cluster_h = height * 2 + kerf_cm
        if cluster_w > board_w_cm + 1e-6 or cluster_h > board_h_cm + 1e-6:
            continue
        used = {int(piece["id"]) for piece in chosen}
        guest = _inner_guest(
            pieces,
            used,
            placed,
            key,
            kerf_cm,
            board_w_cm,
            board_h_cm,
        )
        if guest is not None:
            placed.append(guest["piece"])
            used.add(int(guest["id"]))
        return (
            {
                "sheet_no": 1,
                "w": board_w_cm,
                "h": board_h_cm,
                "pieces": placed,
            },
            used,
        )
    return None


def _assign_cluster(
    pieces: Sequence[Mapping[str, Any]],
    kerf_cm: float,
    *,
    mirroring_allowed: bool,
) -> list[dict[str, Any]] | None:
    options = [_orientations(piece, mirroring_allowed) for piece in pieces]
    width = num(pieces[0].get("width_cm"))
    height = num(pieces[0].get("length_cm"))

    def _search(slot: int, unused: set[int]) -> list[dict[str, Any]] | None:
        if slot == 4:
            return []
        position, column, row = _SLOTS[slot]
        for index in sorted(unused):
            for mirrored, turns, facing, cut_x, cut_y in options[index]:
                if facing != position:
                    continue
                placed = _placed_corner(
                    pieces[index],
                    x_cm=column * (width + kerf_cm),
                    y_cm=row * (height + kerf_cm),
                    cut_x=cut_x,
                    cut_y=cut_y,
                    position=facing,
                    mirrored=mirrored,
                    turns=turns,
                )
                unused.remove(index)
                rest = _search(slot + 1, unused)
                unused.add(index)
                if rest is not None:
                    return [placed, *rest]
        return None

    return _search(0, set(range(4)))


def _orientations(
    piece: Mapping[str, Any],
    mirroring_allowed: bool,
) -> list[tuple[bool, int, str, float, float]]:
    width = num(piece.get("width_cm"))
    height = num(piece.get("length_cm"))
    square = abs(width - height) <= 1e-6
    position = str(piece.get("clipped_corner_position") or "")
    cut_x = num(piece.get("clipped_corner_width_cm"))
    cut_y = num(piece.get("clipped_corner_length_cm"))
    if position not in _TURN:
        return []
    found: list[tuple[bool, int, str, float, float]] = []
    mirrors = (False, True) if mirroring_allowed else (False,)
    for mirrored in mirrors:
        facing = _MIRROR[position] if mirrored else position
        turned_x, turned_y = cut_x, cut_y
        for turns in range(4):
            if turns % 2 == 0 or square:
                found.append((mirrored, turns, facing, turned_x, turned_y))
            facing = _TURN[facing]
            turned_x, turned_y = turned_y, turned_x
    return found


def _placed_corner(
    piece: Mapping[str, Any],
    *,
    x_cm: float,
    y_cm: float,
    cut_x: float,
    cut_y: float,
    position: str,
    mirrored: bool,
    turns: int,
) -> dict[str, Any]:
    placed = make_placed_piece(
        dict(piece),
        x_cm,
        y_cm,
        num(piece.get("width_cm")),
        num(piece.get("length_cm")),
        False,
    )
    placed["clipped_corner_position"] = position
    placed["clipped_corner_width_cm"] = cut_x
    placed["clipped_corner_length_cm"] = cut_y
    placed["placement_mirrored"] = mirrored
    placed["placement_quarter_turns"] = turns
    if mirrored:
        placed["corner_mirrored"] = True
        placed["mirrored"] = True
    return placed


def _inner_guest(
    pieces: Sequence[Mapping[str, Any]],
    used: set[int],
    corners: Sequence[Mapping[str, Any]],
    key: tuple[Any, ...],
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> dict[str, Any] | None:
    kind, width, height, cut_x, cut_y = key
    outlines = [material_outline_cm(piece) for piece in corners]
    if any(outline is None for outline in outlines):
        return None
    proven = [outline for outline in outlines if outline is not None]
    for piece in pieces:
        if int(piece["id"]) in used:
            continue
        if str(piece.get("piece_type") or "Regular") not in {"Regular", *_CORNER_TYPES}:
            continue
        if kind == "L-Shaped Corner":
            guest = _guest_in_rectangular_void(
                piece, corners, width, height, cut_x, cut_y, kerf_cm
            )
        else:
            guest = _guest_in_clipped_void(
                piece,
                proven,
                width,
                height,
                cut_x,
                cut_y,
                kerf_cm,
                board_w_cm,
                board_h_cm,
            )
        if guest is not None:
            return {"id": piece["id"], "piece": guest}
    return None


def _guest_in_rectangular_void(
    piece: Mapping[str, Any],
    corners: Sequence[Mapping[str, Any]],
    width: float,
    height: float,
    cut_x: float,
    cut_y: float,
    kerf_cm: float,
) -> dict[str, Any] | None:
    left = width - cut_x
    top = height - cut_y
    void_w = cut_x * 2 + kerf_cm
    void_h = cut_y * 2 + kerf_cm
    usable = {
        "x": left + kerf_cm,
        "y": top + kerf_cm,
        "w": void_w - 2 * kerf_cm,
        "h": void_h - 2 * kerf_cm,
    }
    if usable["w"] <= 0 or usable["h"] <= 0:
        return None
    for orientation in orientations_for(dict(piece)):
        if orientation["w"] > usable["w"] + 1e-6 or orientation["h"] > usable["h"] + 1e-6:
            continue
        placed = make_placed_piece(
            dict(piece),
            usable["x"],
            usable["y"],
            orientation["w"],
            orientation["h"],
            bool(orientation["rotated"]),
        )
        outline = material_outline_cm(placed)
        if outline is None:
            continue
        if _clears(outline, corners, kerf_cm):
            return placed
    return None


def _guest_in_clipped_void(
    piece: Mapping[str, Any],
    corner_outlines: Sequence[Sequence[tuple[float, float]]],
    width: float,
    height: float,
    cut_x: float,
    cut_y: float,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
) -> dict[str, Any] | None:
    angle = void_edge_angle_deg(cut_x, cut_y)
    if angle is None:
        return None
    center_x = width + kerf_cm / 2
    center_y = height + kerf_cm / 2
    piece_w = num(piece.get("width_cm"))
    piece_h = num(piece.get("length_cm"))
    for rotation in (angle, angle + 180.0):
        if not non_quarter_rotation_is_admitted(
            rotation,
            cut_width_cm=cut_x,
            cut_length_cm=cut_y,
            outline_inside_void=True,
        ):
            continue
        outline = _rotated_rectangle(center_x, center_y, piece_w, piece_h, rotation)
        if not _inside_board(outline, board_w_cm, board_h_cm):
            continue
        if not _clears(outline, corner_outlines, kerf_cm):
            continue
        xs = [point[0] for point in outline]
        ys = [point[1] for point in outline]
        placed = make_placed_piece(
            dict(piece),
            min(xs),
            min(ys),
            max(xs) - min(xs),
            max(ys) - min(ys),
            False,
        )
        placed["placement_outline_cm"] = outline
        placed["placement_rotation_deg"] = rotation % 360.0
        placed["placement_void_angle_deg"] = angle
        return placed
    return None


def _rotated_rectangle(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    rotation_deg: float,
) -> list[tuple[float, float]]:
    radians = math.radians(rotation_deg)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    half_w = width / 2
    half_h = height / 2
    points = []
    for px, py in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)):
        points.append((center_x + px * cosine - py * sine, center_y + px * sine + py * cosine))
    return points


def _inside_board(
    outline: Sequence[tuple[float, float]],
    board_w_cm: float,
    board_h_cm: float,
) -> bool:
    return all(
        -1e-6 <= point[0] <= board_w_cm + 1e-6
        and -1e-6 <= point[1] <= board_h_cm + 1e-6
        for point in outline
    )


def _clears(
    outline: Sequence[tuple[float, float]],
    corners: Sequence[Mapping[str, Any]] | Sequence[Sequence[tuple[float, float]]],
    kerf_cm: float,
) -> bool:
    for corner in corners:
        other = corner if isinstance(corner, (list, tuple)) else material_outline_cm(corner)
        if other is None:
            return False
        if polygons_overlap(outline, other):
            return False
        if polygon_distance(outline, other) + 1e-6 < kerf_cm:
            return False
    return True


def _angle_close(left: float, right: float, tolerance: float) -> bool:
    return abs((left - right + 180.0) % 360.0 - 180.0) <= tolerance


def admit_clipped_void_topology(
    contours: Sequence[Any],
    expected: Sequence[Any],
    *,
    geometry_tolerance: float,
) -> Any | None:
    """Return topology for four clipped corners plus one void-angle piece.

    Any other angle, a missing clip, or a piece outside the void returns
    ``None`` so the ordinary matcher keeps rejecting it.
    """

    from almdina_erp.almdina_erp.domain.orders.piece_policy import (
        CLIPPED_CORNER_POSITIONS,
        CLIPPED_CORNER_TYPE,
    )

    from .corner_contour_rotation import match_corner_contour
    from .dxf_geometry import point_in_polygon
    from .dxf_topology import PartGeometry, ResolvedPartGeometry, ResolvedTopology

    clips = [
        piece
        for piece in expected
        if getattr(piece, "piece_type", "") == CLIPPED_CORNER_TYPE
        and float(getattr(piece, "clipped_cut_width_mm", 0) or 0) > 0
        and float(getattr(piece, "clipped_cut_length_mm", 0) or 0) > 0
    ]
    if len(expected) != 5 or len(clips) != 4 or len(contours) != 5:
        return None
    inners = [piece for piece in expected if piece not in clips]
    if len(inners) != 1:
        return None
    inner = inners[0]
    unused = list(contours)
    assigned: list[tuple[Any, Any]] = []
    for clip in clips:
        found = None
        for contour in list(unused):
            if _contour_matches_clip(
                contour,
                clip,
                geometry_tolerance,
                match_corner_contour,
                CLIPPED_CORNER_POSITIONS,
            ):
                found = contour
                break
        if found is None:
            return None
        unused.remove(found)
        assigned.append((found, clip))
    polygon = _ring(unused[0].polygon)
    angle = _rectangle_angle_deg(polygon)
    cut_w = float(clips[0].clipped_cut_width_mm) / 10.0
    cut_h = float(clips[0].clipped_cut_length_mm) / 10.0
    if angle is None or not non_quarter_rotation_is_admitted(
        angle,
        cut_width_cm=cut_w,
        cut_length_cm=cut_h,
        outline_inside_void=True,
    ):
        return None
    if not _edge_lengths_match(polygon, float(inner.width), float(inner.height)):
        return None
    clip_rings = [_ring(contour.polygon) for contour, _clip in assigned]
    if not _contour_sits_in_void(polygon, clip_rings, point_in_polygon):
        return None
    parts = [
        ResolvedPartGeometry(
            contour_key=int(contour.key),
            geometry=PartGeometry(outer=_ring(contour.polygon)),
            expected_piece_index=list(expected).index(clip),
        )
        for contour, clip in assigned
    ]
    parts.append(
        ResolvedPartGeometry(
            contour_key=int(unused[0].key),
            geometry=PartGeometry(outer=polygon),
            expected_piece_index=list(expected).index(inner),
        )
    )
    return ResolvedTopology(parts=tuple(parts))


def _contour_matches_clip(
    contour: Any,
    clip: Any,
    tolerance: float,
    match_corner_contour: Any,
    positions: Sequence[str],
) -> bool:
    saved = str(getattr(clip, "clipped_corner_position", "") or "")
    choices = (saved,) if saved in positions else positions
    for position in choices:
        match = match_corner_contour(
            contour.polygon,
            piece_type=str(clip.piece_type),
            position=position,
            width_cm=float(clip.width) / 10.0,
            length_cm=float(clip.height) / 10.0,
            cut_width_cm=float(clip.clipped_cut_width_mm) / 10.0,
            cut_length_cm=float(clip.clipped_cut_length_mm) / 10.0,
            tolerance_mm=tolerance,
        )
        if match.quarter_turns is not None and match.reason == "unique":
            return True
    return False


def _ring(points: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    ring = tuple((float(point[0]), float(point[1])) for point in points)
    if len(ring) > 1 and ring[0] == ring[-1]:
        return ring[:-1]
    return ring


def _rectangle_angle_deg(polygon: Sequence[tuple[float, float]]) -> float | None:
    if len(polygon) != 4:
        return None
    dx = polygon[1][0] - polygon[0][0]
    dy = polygon[1][1] - polygon[0][1]
    if math.hypot(dx, dy) <= 1e-6:
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _edge_lengths_match(
    polygon: Sequence[tuple[float, float]],
    width_mm: float,
    height_mm: float,
) -> bool:
    lengths = sorted(
        math.hypot(
            polygon[(index + 1) % len(polygon)][0] - point[0],
            polygon[(index + 1) % len(polygon)][1] - point[1],
        )
        for index, point in enumerate(polygon)
    )
    short = min(width_mm, height_mm)
    long = max(width_mm, height_mm)
    return (
        abs(lengths[0] - short) <= 0.2
        and abs(lengths[1] - short) <= 0.2
        and abs(lengths[-2] - long) <= 0.2
        and abs(lengths[-1] - long) <= 0.2
    )


def _contour_sits_in_void(
    polygon: Sequence[tuple[float, float]],
    clips: Sequence[Sequence[tuple[float, float]]],
    point_in_polygon: Any,
) -> bool:
    centroid = (
        sum(point[0] for point in polygon) / len(polygon),
        sum(point[1] for point in polygon) / len(polygon),
    )
    centers = []
    for clip in clips:
        if point_in_polygon(centroid, clip):
            return False
        if polygons_overlap(polygon, clip):
            return False
        centers.append(
            (
                sum(point[0] for point in clip) / len(clip),
                sum(point[1] for point in clip) / len(clip),
            )
        )
    mean_x = sum(point[0] for point in centers) / len(centers)
    mean_y = sum(point[1] for point in centers) / len(centers)
    span = max(
        math.hypot(point[0] - mean_x, point[1] - mean_y) for point in centers
    )
    return math.hypot(centroid[0] - mean_x, centroid[1] - mean_y) <= span * 0.45


__all__ = [
    "admit_clipped_void_topology",
    "apply_shape_aware_nesting",
    "non_quarter_rotation_is_admitted",
    "void_edge_angle_deg",
]
