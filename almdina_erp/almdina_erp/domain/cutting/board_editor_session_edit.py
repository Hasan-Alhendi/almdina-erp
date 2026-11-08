"""Session-local Board Editor move rules (framework-free).

The entry projection stays immutable. Session boards/pieces are pure data.
Authority for drop acceptance lives here; UI previews may mirror these checks.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.board_editor_hosting import (
    _would_create_cycle,
    declared_host_piece_id,
    piece_placement_id,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    EPSILON,
    polygon_distance,
    polygon_inside_rect,
    polygons_overlap,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    polygon_strictly_contains_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    is_contained,
    num,
    rect_intersects,
    rects_have_clearance,
)

EDIT_BLOCK_MISSING_INSTANCE = "missing_piece_instance_id"
EDIT_BLOCK_SPECIAL_GEOMETRY = "special_geometry_unavailable"
EDIT_BLOCK_INCOMPLETE_GEOMETRY = "incomplete_geometry"

DROP_OK = "ok"
DROP_PARTIAL_BOARD = "partial_board_overlap"
DROP_AMBIGUOUS_BOARD = "ambiguous_board_target"
DROP_OVERLAP = "piece_overlap"
DROP_KERF = "kerf_clearance"
DROP_OUTSIDE_USABLE = "outside_usable_sheet"
DROP_BOARD_OVERLAP = "board_overlap"
DROP_NOT_EDITABLE = "not_editable"

CUT_PATH_STALE = "cut_path_stale_after_session_move"
TEXT_STALE = "unbound_text_stale_after_session_move"


def _num_or(value: Any, fallback: Any) -> float:
    if value is None or value == "":
        return num(fallback)
    return num(value)


def piece_session_key(piece: Mapping[str, Any]) -> str | None:
    instance = str(piece.get("piece_instance_id") or "").strip()
    if instance:
        return f"instance:{instance}"
    return None


def piece_edit_eligibility(
    piece: Mapping[str, Any],
    *,
    elements: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return whether a projected piece may be moved in the session."""

    key = piece_session_key(piece)
    if not key:
        return {
            "editable": False,
            "piece_key": None,
            "reason": EDIT_BLOCK_MISSING_INSTANCE,
        }

    piece_id = piece_placement_id(piece)
    if piece_id is None and piece.get("piece_id") not in (None, ""):
        try:
            piece_id = int(piece["piece_id"])
        except (TypeError, ValueError):
            piece_id = None
    instance_id = str(piece.get("piece_instance_id") or "").strip()
    related = [
        element
        for element in (elements or [])
        if (
            (piece_id is not None and element.get("piece_id") == piece_id)
            or (
                instance_id
                and str(element.get("piece_instance_id") or "").strip() == instance_id
            )
        )
    ]
    if any(
        element.get("kind") == "unresolved"
        and (element.get("payload") or {}).get("reason") == EDIT_BLOCK_SPECIAL_GEOMETRY
        for element in related
    ):
        return {
            "editable": False,
            "piece_key": key,
            "reason": EDIT_BLOCK_SPECIAL_GEOMETRY,
        }

    has_outline = any(
        element.get("kind") in {"finished_outline", "placement_rect"}
        and (element.get("geometry") or element.get("payload"))
        for element in related
    )
    placement = piece.get("placement_cm") or {}
    has_placement = num(placement.get("w")) > 0 and num(placement.get("h")) > 0
    if not has_outline and not has_placement and not piece.get("has_geometry"):
        return {
            "editable": False,
            "piece_key": key,
            "reason": EDIT_BLOCK_INCOMPLETE_GEOMETRY,
        }
    return {"editable": True, "piece_key": key, "reason": None}


def _placement_rect_mm(piece: Mapping[str, Any]) -> dict[str, float]:
    placement = piece.get("placement_cm") or {}
    w = num(placement.get("w")) * 10.0
    h = num(placement.get("h")) * 10.0
    if piece.get("apply_rotated_to_dimensions") and placement.get("rotated"):
        w, h = h, w
    local_x = piece.get("local_x_mm")
    local_y = piece.get("local_y_mm")
    return {
        "x": num(local_x) if local_x is not None else num(placement.get("x")) * 10.0,
        "y": num(local_y) if local_y is not None else num(placement.get("y")) * 10.0,
        "w": w,
        "h": h,
    }


def piece_footprint_mm(piece: Mapping[str, Any]) -> dict[str, Any]:
    """Footprint in usable-sheet millimetres (or world mm when outside boards)."""

    outline = piece.get("outline_mm")
    if isinstance(outline, list) and len(outline) >= 3:
        xs = [num(point[0]) for point in outline]
        ys = [num(point[1]) for point in outline]
        return {
            "kind": "polygon",
            "points": [[num(p[0]), num(p[1])] for p in outline],
            "bounds": {
                "x": min(xs),
                "y": min(ys),
                "w": max(xs) - min(xs),
                "h": max(ys) - min(ys),
            },
        }
    rect = _placement_rect_mm(piece)
    return {"kind": "rect", "bounds": rect, "points": None}


def _rect_corners(rect: Mapping[str, float]) -> list[list[float]]:
    x = num(rect["x"])
    y = num(rect["y"])
    w = num(rect["w"])
    h = num(rect["h"])
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _footprint_inside_usable(footprint: Mapping[str, Any], board: Mapping[str, Any]) -> bool:
    usable = {
        "x": 0.0,
        "y": 0.0,
        "w": _num_or(board.get("usable_width_mm"), board.get("width_mm")),
        "h": _num_or(board.get("usable_length_mm"), board.get("height_mm")),
    }
    bounds = footprint["bounds"]
    if footprint.get("kind") == "polygon" and footprint.get("points"):
        return polygon_inside_rect(
            footprint["points"],
            min_x=usable["x"],
            min_y=usable["y"],
            max_x=usable["x"] + usable["w"],
            max_y=usable["y"] + usable["h"],
            tolerance=1e-6,
        )
    return is_contained(bounds, usable)


def _footprint_intersects_usable(footprint: Mapping[str, Any], board: Mapping[str, Any]) -> bool:
    usable = {
        "x": 0.0,
        "y": 0.0,
        "w": _num_or(board.get("usable_width_mm"), board.get("width_mm")),
        "h": _num_or(board.get("usable_length_mm"), board.get("height_mm")),
    }
    return rect_intersects(footprint["bounds"], usable)


def _world_footprint(piece: Mapping[str, Any], boards: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    local = piece_footprint_mm(piece)
    sheet_no = piece.get("sheet_no")
    if sheet_no is None or sheet_no == "":
        return local
    board = boards.get(str(sheet_no)) or {}
    ox = num(board.get("origin_x_mm")) + num(board.get("trim_x_mm"))
    oy = num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))
    bounds = local["bounds"]
    shifted = {
        "x": bounds["x"] + ox,
        "y": bounds["y"] + oy,
        "w": bounds["w"],
        "h": bounds["h"],
    }
    points = None
    if local.get("points"):
        points = [[p[0] + ox, p[1] + oy] for p in local["points"]]
    return {"kind": local["kind"], "bounds": shifted, "points": points}


def boards_overlap(a: Mapping[str, Any], b: Mapping[str, Any], *, gap_mm: float = 8.0) -> bool:
    ra = {
        "x": num(a.get("origin_x_mm")),
        "y": num(a.get("origin_y_mm")),
        "w": num(a.get("width_mm")),
        "h": num(a.get("height_mm")) + _num_or(a.get("title_band_mm"), 36.0),
    }
    rb = {
        "x": num(b.get("origin_x_mm")),
        "y": num(b.get("origin_y_mm")),
        "w": num(b.get("width_mm")),
        "h": num(b.get("height_mm")) + _num_or(b.get("title_band_mm"), 36.0),
    }
    # Expand slightly so near-touching boards remain unambiguous drop targets.
    pad = max(0.0, num(gap_mm))
    ra = {"x": ra["x"] - pad, "y": ra["y"] - pad, "w": ra["w"] + 2 * pad, "h": ra["h"] + 2 * pad}
    rb = {"x": rb["x"] - pad, "y": rb["y"] - pad, "w": rb["w"] + 2 * pad, "h": rb["h"] + 2 * pad}
    return rect_intersects(ra, rb)


def validate_board_placement(
    boards: Mapping[str, Mapping[str, Any]],
    *,
    sheet_no: int | str,
    origin_x_mm: float,
    origin_y_mm: float,
) -> dict[str, Any]:
    moving = dict(boards.get(str(sheet_no)) or {})
    moving["origin_x_mm"] = num(origin_x_mm)
    moving["origin_y_mm"] = num(origin_y_mm)
    for other_no, other in boards.items():
        if str(other_no) == str(sheet_no):
            continue
        if boards_overlap(moving, other):
            return {"ok": False, "code": DROP_BOARD_OVERLAP, "message": DROP_BOARD_OVERLAP}
    return {"ok": True, "code": DROP_OK, "message": None}


def _pair_conflict(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    kerf_mm: float,
) -> str | None:
    """Material overlap + true edge kerf. AABB is only an early-accept filter."""

    gap = max(0.0, num(kerf_mm))
    if first.get("kind") == "polygon" and second.get("kind") == "polygon":
        if polygons_overlap(first["points"], second["points"]):
            return DROP_OVERLAP
        # Far AABB ⇒ kerf is already satisfied; skip segment distance.
        if rects_have_clearance(first["bounds"], second["bounds"], gap):
            return None
        # Close/overlapping AABB with no material overlap (e.g. L cutout): real edge distance.
        if polygon_distance(first["points"], second["points"]) + EPSILON < gap:
            return DROP_KERF
        return None
    if rect_intersects(first["bounds"], second["bounds"]):
        return DROP_OVERLAP
    if not rects_have_clearance(first["bounds"], second["bounds"], gap):
        return DROP_KERF
    return None


def _nested_in_hole(guest_fp: Mapping[str, Any], host: Mapping[str, Any]) -> bool:
    hole = host.get("glass_hole_local_mm")
    guest_points = guest_fp.get("points")
    if isinstance(hole, list) and len(hole) >= 3 and guest_points:
        return polygon_strictly_contains_polygon(hole, guest_points)
    return False


def _hole_kerf_conflict(
    guest_fp: Mapping[str, Any],
    host: Mapping[str, Any],
    kerf_mm: float,
) -> str | None:
    hole = host.get("glass_hole_local_mm")
    guest_points = guest_fp.get("points")
    gap = max(0.0, num(kerf_mm))
    if not isinstance(hole, list) or len(hole) < 3 or not guest_points or gap <= 0:
        return None
    if polygon_distance(hole, guest_points) + EPSILON < gap:
        return DROP_KERF
    return None


def _material_pair_conflict(
    piece_a: Mapping[str, Any],
    fp_a: Mapping[str, Any],
    piece_b: Mapping[str, Any],
    fp_b: Mapping[str, Any],
    *,
    kerf_mm: float,
) -> str | None:
    """Outer-minus-holes material rule for session drops."""

    if _nested_in_hole(fp_a, piece_b):
        return _hole_kerf_conflict(fp_a, piece_b, kerf_mm)
    if _nested_in_hole(fp_b, piece_a):
        return _hole_kerf_conflict(fp_b, piece_a, kerf_mm)
    return _pair_conflict(fp_a, fp_b, kerf_mm=kerf_mm)


def resolve_drop_sheet(
    *,
    footprint_world: Mapping[str, Any],
    boards: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify a world-space footprint as one sheet, outside, or invalid."""

    inside: list[str] = []
    partial: list[str] = []
    for sheet_no, board in boards.items():
        ox = num(board.get("origin_x_mm")) + num(board.get("trim_x_mm"))
        oy = num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))
        local_bounds = {
            "x": footprint_world["bounds"]["x"] - ox,
            "y": footprint_world["bounds"]["y"] - oy,
            "w": footprint_world["bounds"]["w"],
            "h": footprint_world["bounds"]["h"],
        }
        local = {
            "kind": footprint_world.get("kind") or "rect",
            "bounds": local_bounds,
            "points": (
                [[p[0] - ox, p[1] - oy] for p in footprint_world["points"]]
                if footprint_world.get("points")
                else None
            ),
        }
        if _footprint_inside_usable(local, board):
            inside.append(str(sheet_no))
        elif _footprint_intersects_usable(local, board):
            partial.append(str(sheet_no))

    if partial:
        return {"ok": False, "code": DROP_PARTIAL_BOARD, "sheet_no": None, "local": None}
    if len(inside) > 1:
        return {"ok": False, "code": DROP_AMBIGUOUS_BOARD, "sheet_no": None, "local": None}
    if len(inside) == 1:
        sheet_no = inside[0]
        board = boards[sheet_no]
        ox = num(board.get("origin_x_mm")) + num(board.get("trim_x_mm"))
        oy = num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))
        return {
            "ok": True,
            "code": DROP_OK,
            "sheet_no": int(sheet_no) if str(sheet_no).isdigit() else sheet_no,
            "local_x_mm": footprint_world["bounds"]["x"] - ox,
            "local_y_mm": footprint_world["bounds"]["y"] - oy,
        }
    return {
        "ok": True,
        "code": DROP_OK,
        "sheet_no": None,
        "local_x_mm": footprint_world["bounds"]["x"],
        "local_y_mm": footprint_world["bounds"]["y"],
    }


def validate_piece_drop(
    *,
    piece: Mapping[str, Any],
    pieces: Mapping[str, Mapping[str, Any]],
    boards: Mapping[str, Mapping[str, Any]],
    world_x_mm: float,
    world_y_mm: float,
    kerf_mm: float = 0.0,
) -> dict[str, Any]:
    if not piece.get("editable"):
        return {"ok": False, "code": DROP_NOT_EDITABLE, "message": piece.get("block_reason")}

    moved = deepcopy(dict(piece))
    # Anchor translation uses the footprint top-left in world space.
    current_world = _world_footprint(piece, boards)
    dx = num(world_x_mm) - current_world["bounds"]["x"]
    dy = num(world_y_mm) - current_world["bounds"]["y"]
    proposed_world = {
        "kind": current_world["kind"],
        "bounds": {
            "x": current_world["bounds"]["x"] + dx,
            "y": current_world["bounds"]["y"] + dy,
            "w": current_world["bounds"]["w"],
            "h": current_world["bounds"]["h"],
        },
        "points": (
            [[p[0] + dx, p[1] + dy] for p in current_world["points"]]
            if current_world.get("points")
            else None
        ),
    }
    target = resolve_drop_sheet(footprint_world=proposed_world, boards=boards)
    if not target["ok"]:
        return {"ok": False, "code": target["code"], "message": target["code"]}

    moved["sheet_no"] = target["sheet_no"]
    moved["local_x_mm"] = target["local_x_mm"]
    moved["local_y_mm"] = target["local_y_mm"]
    _reframe_piece_geometry(
        moved,
        boards,
        from_sheet=piece.get("sheet_no"),
        to_sheet=target["sheet_no"],
        world_dx=dx,
        world_dy=dy,
    )
    moved_local = piece_footprint_mm(moved)
    moving_keys = {piece.get("piece_key")}
    moving_keys.update(
        key for key, other in pieces.items() if other.get("glass_host_key") == piece.get("piece_key")
    )

    if target["sheet_no"] is not None:
        for other_key, other in pieces.items():
            if other_key in moving_keys:
                continue
            if other.get("sheet_no") != target["sheet_no"]:
                continue
            # Relationship alone never skips material checks; openings use outer-holes.
            conflict = _material_pair_conflict(
                moved,
                moved_local,
                other,
                piece_footprint_mm(other),
                kerf_mm=kerf_mm,
            )
            if conflict:
                return {"ok": False, "code": conflict, "message": conflict}

    attach_host_key = None
    attach_host_piece_id = None
    detach_host = False
    active_key = piece.get("glass_host_key")
    source_key = piece.get("source_glass_host_key")
    if active_key and active_key in pieces:
        host = pieces[active_key]
        if target["sheet_no"] != host.get("sheet_no") or not _guest_remains_in_host(moved, host):
            detach_host = True
    elif source_key and source_key in pieces:
        host = pieces[source_key]
        if (
            target["sheet_no"] == host.get("sheet_no")
            and _guest_remains_in_host(moved, host)
            and _hole_kerf_conflict(moved_local, host, kerf_mm) is None
        ):
            attach_host_key = source_key
            attach_host_piece_id = host.get("piece_id")

    return {
        "ok": True,
        "code": DROP_OK,
        "sheet_no": target["sheet_no"],
        "local_x_mm": target["local_x_mm"],
        "local_y_mm": target["local_y_mm"],
        "delta_x_mm": dx,
        "delta_y_mm": dy,
        "detach_host": detach_host,
        "attach_host_key": attach_host_key,
        "attach_host_piece_id": attach_host_piece_id,
    }


def _guest_keys(pieces: Mapping[str, Mapping[str, Any]], host_key: str) -> list[str]:
    return [
        key
        for key, piece in pieces.items()
        if piece.get("glass_host_key") == host_key
    ]


def _sheet_origin_mm(
    boards: Mapping[str, Mapping[str, Any]], sheet_no: int | str | None
) -> tuple[float, float]:
    if sheet_no is None or sheet_no == "":
        return 0.0, 0.0
    board = boards.get(str(sheet_no)) or {}
    return (
        num(board.get("origin_x_mm")) + num(board.get("trim_x_mm")),
        num(board.get("origin_y_mm")) + num(board.get("trim_y_mm")),
    )


def _reframe_points(
    points: Any,
    boards: Mapping[str, Mapping[str, Any]],
    *,
    from_sheet: int | str | None,
    to_sheet: int | str | None,
    world_dx: float,
    world_dy: float,
) -> Any:
    if not isinstance(points, list):
        return points
    from_x, from_y = _sheet_origin_mm(boards, from_sheet)
    to_x, to_y = _sheet_origin_mm(boards, to_sheet)
    return [
        [
            num(point[0]) + from_x + num(world_dx) - to_x,
            num(point[1]) + from_y + num(world_dy) - to_y,
        ]
        for point in points
    ]


def _reframe_piece_geometry(
    piece: dict[str, Any],
    boards: Mapping[str, Mapping[str, Any]],
    *,
    from_sheet: int | str | None,
    to_sheet: int | str | None,
    world_dx: float,
    world_dy: float,
) -> None:
    piece["outline_mm"] = _reframe_points(
        piece.get("outline_mm"),
        boards,
        from_sheet=from_sheet,
        to_sheet=to_sheet,
        world_dx=world_dx,
        world_dy=world_dy,
    )
    piece["base_outline_mm"] = _reframe_points(
        piece.get("base_outline_mm"),
        boards,
        from_sheet=from_sheet,
        to_sheet=to_sheet,
        world_dx=world_dx,
        world_dy=world_dy,
    )
    piece["glass_hole_local_mm"] = _reframe_points(
        piece.get("glass_hole_local_mm"),
        boards,
        from_sheet=from_sheet,
        to_sheet=to_sheet,
        world_dx=world_dx,
        world_dy=world_dy,
    )
    piece["base_hole_mm"] = _reframe_points(
        piece.get("base_hole_mm"),
        boards,
        from_sheet=from_sheet,
        to_sheet=to_sheet,
        world_dx=world_dx,
        world_dy=world_dy,
    )
    pivot = piece.get("pivot_mm")
    if isinstance(pivot, Mapping):
        from_x, from_y = _sheet_origin_mm(boards, from_sheet)
        to_x, to_y = _sheet_origin_mm(boards, to_sheet)
        piece["pivot_mm"] = {
            "x": num(pivot.get("x")) + from_x + num(world_dx) - to_x,
            "y": num(pivot.get("y")) + from_y + num(world_dy) - to_y,
        }


def apply_piece_move(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    sheet_no: int | str | None,
    local_x_mm: float,
    local_y_mm: float,
    delta_x_mm: float,
    delta_y_mm: float,
    detach_host: bool = False,
    attach_host_key: str | None = None,
    attach_host_piece_id: Any = None,
) -> dict[str, Any]:
    """Apply one accepted piece move, including hosted guests once."""

    next_session = deepcopy(dict(session))
    pieces = next_session.setdefault("pieces", {})
    boards = next_session.get("boards") or {}
    piece = pieces.get(piece_key)
    if not piece:
        raise KeyError(piece_key)

    previous_sheet = piece.get("sheet_no")
    _reframe_piece_geometry(
        piece,
        boards,
        from_sheet=previous_sheet,
        to_sheet=sheet_no,
        world_dx=delta_x_mm,
        world_dy=delta_y_mm,
    )
    piece["sheet_no"] = sheet_no
    piece["local_x_mm"] = num(local_x_mm)
    piece["local_y_mm"] = num(local_y_mm)
    piece["rotation_deg"] = num(piece.get("rotation_deg"))

    for guest_key in _guest_keys(pieces, piece_key):
        guest = pieces[guest_key]
        guest_from = guest.get("sheet_no")
        # Apply the host world delta once; guests are not moved again as independent drops.
        _reframe_piece_geometry(
            guest,
            boards,
            from_sheet=guest_from,
            to_sheet=sheet_no,
            world_dx=delta_x_mm,
            world_dy=delta_y_mm,
        )
        guest["sheet_no"] = sheet_no
        guest_fp = piece_footprint_mm(guest)
        guest["local_x_mm"] = guest_fp["bounds"]["x"]
        guest["local_y_mm"] = guest_fp["bounds"]["y"]

    trusted = piece.get("source_glass_host_key")
    if attach_host_key and attach_host_key in pieces and trusted == attach_host_key:
        host = pieces[attach_host_key]
        piece["glass_host_key"] = attach_host_key
        piece["glass_host_piece_id"] = (
            attach_host_piece_id
            if attach_host_piece_id not in (None, "")
            else host.get("piece_id")
        )
    else:
        host_key = piece.get("glass_host_key")
        if detach_host or (host_key and host_key in pieces):
            host = pieces.get(host_key) if host_key else None
            if (
                detach_host
                or host is None
                or sheet_no != host.get("sheet_no")
                or not _guest_remains_in_host(piece, host)
            ):
                # Clear live hosting only; source_glass_host_* remains for re-entry.
                piece["glass_host_key"] = None
                piece["glass_host_piece_id"] = None

    _mark_sheet_artifacts_stale(next_session, previous_sheet)
    _mark_sheet_artifacts_stale(next_session, sheet_no)
    return next_session


def _guest_remains_in_host(guest: Mapping[str, Any], host: Mapping[str, Any]) -> bool:
    hole = host.get("glass_hole_local_mm")
    guest_fp = piece_footprint_mm(guest)
    if isinstance(hole, list) and len(hole) >= 3 and guest_fp.get("points"):
        return polygon_strictly_contains_polygon(hole, guest_fp["points"])
    if isinstance(hole, list) and len(hole) >= 3:
        xs = [num(p[0]) for p in hole]
        ys = [num(p[1]) for p in hole]
        hole_rect = {
            "x": min(xs),
            "y": min(ys),
            "w": max(xs) - min(xs),
            "h": max(ys) - min(ys),
        }
        return is_contained(guest_fp["bounds"], hole_rect)
    # Without a proven hole outline, keep hosting only when still on the same sheet.
    return guest.get("sheet_no") == host.get("sheet_no")


def apply_board_move(
    session: Mapping[str, Any],
    *,
    sheet_no: int | str,
    origin_x_mm: float,
    origin_y_mm: float,
) -> dict[str, Any]:
    next_session = deepcopy(dict(session))
    board = next_session.setdefault("boards", {}).get(str(sheet_no))
    if not board:
        raise KeyError(sheet_no)
    board["origin_x_mm"] = num(origin_x_mm)
    board["origin_y_mm"] = num(origin_y_mm)
    board["rotation_deg"] = num(board.get("rotation_deg"))
    board["user_moved"] = True
    # Local piece coordinates unchanged.
    return next_session


def _translate_outline(piece: dict[str, Any], dx: float, dy: float) -> None:
    """Same-sheet translation helper (world delta == usable-local delta)."""

    outline = piece.get("outline_mm")
    if isinstance(outline, list):
        piece["outline_mm"] = [[num(p[0]) + num(dx), num(p[1]) + num(dy)] for p in outline]
    base = piece.get("base_outline_mm")
    if isinstance(base, list):
        piece["base_outline_mm"] = [[num(p[0]) + num(dx), num(p[1]) + num(dy)] for p in base]
    pivot = piece.get("pivot_mm")
    if isinstance(pivot, Mapping):
        piece["pivot_mm"] = {
            "x": num(pivot.get("x")) + num(dx),
            "y": num(pivot.get("y")) + num(dy),
        }


def _translate_hole(piece: dict[str, Any], dx: float, dy: float) -> None:
    hole = piece.get("glass_hole_local_mm")
    if isinstance(hole, list):
        piece["glass_hole_local_mm"] = [[num(p[0]) + num(dx), num(p[1]) + num(dy)] for p in hole]
    base_hole = piece.get("base_hole_mm")
    if isinstance(base_hole, list):
        piece["base_hole_mm"] = [
            [num(p[0]) + num(dx), num(p[1]) + num(dy)] for p in base_hole
        ]


def _mark_sheet_artifacts_stale(session: dict[str, Any], sheet_no: int | str | None) -> None:
    if sheet_no is None or sheet_no == "":
        return
    key = str(sheet_no)
    session.setdefault("stale_cut_path_sheets", [])
    session.setdefault("stale_unbound_text_sheets", [])
    if key not in session["stale_cut_path_sheets"]:
        session["stale_cut_path_sheets"].append(key)
    if key not in session["stale_unbound_text_sheets"]:
        session["stale_unbound_text_sheets"].append(key)


def hosting_would_cycle(pieces: Mapping[str, Mapping[str, Any]], guest_key: str, host_key: str) -> bool:
    proposed = {
        key: (piece.get("glass_host_piece_id") if key != guest_key else pieces[host_key].get("piece_id"))
        for key, piece in pieces.items()
    }
    guest_id = pieces[guest_key].get("piece_id")
    host_id = pieces[host_key].get("piece_id")
    if guest_id is None or host_id is None:
        return False
    by_id = {
        piece.get("piece_id"): piece.get("glass_host_piece_id")
        for piece in pieces.values()
        if piece.get("piece_id") is not None
    }
    by_id[guest_id] = host_id
    return _would_create_cycle(by_id, guest_id=guest_id, host_id=host_id)


__all__ = [
    "EDIT_BLOCK_INCOMPLETE_GEOMETRY",
    "EDIT_BLOCK_MISSING_INSTANCE",
    "EDIT_BLOCK_SPECIAL_GEOMETRY",
    "CUT_PATH_STALE",
    "TEXT_STALE",
    "DROP_OK",
    "DROP_PARTIAL_BOARD",
    "DROP_AMBIGUOUS_BOARD",
    "DROP_OVERLAP",
    "DROP_KERF",
    "DROP_BOARD_OVERLAP",
    "DROP_NOT_EDITABLE",
    "piece_session_key",
    "piece_edit_eligibility",
    "piece_footprint_mm",
    "boards_overlap",
    "validate_board_placement",
    "resolve_drop_sheet",
    "validate_piece_drop",
    "apply_piece_move",
    "apply_board_move",
    "hosting_would_cycle",
]
