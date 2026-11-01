"""Session-local Board Editor free rotation (framework-free).

Transform contract for one session piece
----------------------------------------
- ``base_outline_mm`` / ``base_hole_mm``: local manufacturing geometry at
  ``rotation_deg == 0`` for this session (absolute usable-sheet millimetres).
  Built from the entry projection as loaded. Never re-applies historical DXF
  ``rotated`` to points that are already oriented.
- ``pivot_mm``: fixed reference = centre of the base outline AABB (or placement
  rect). Moves with translation; does not drift under angle changes.
- ``rotation_deg``: session edit angle in degrees. Positive matches SVG
  ``rotate()`` (clockwise on screen because usable Y grows downward). Displayed
  to the user as this edit angle from the as-loaded pose; it is **not** a claim
  about original grain / source DXF orientation.
- ``outline_mm`` / ``glass_hole_local_mm``: always re-derived from base via
  rotation about ``pivot_mm`` (no cumulative point re-rotation).
- Hosting: ``glass_host_key`` / hole stay identity-stable; guests share one
  rigid host transform when the host rotates.

Board origin, Applied Trim, and camera are separate from this local transform.
``placement_cm.rotated`` / ``source_rotated_dims`` remain dimensions-only metadata.
``apply_rotated_to_geometry`` stays False — never rotate entry DXF twice.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    DROP_KERF,
    DROP_NOT_EDITABLE,
    DROP_OK,
    DROP_OUTSIDE_USABLE,
    DROP_OVERLAP,
    DROP_PARTIAL_BOARD,
    _footprint_inside_usable,
    _guest_keys,
    _mark_sheet_artifacts_stale,
    _pair_conflict,
    _world_footprint,
    piece_footprint_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    polygon_strictly_contains_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import is_contained, num

ROTATE_BLOCK_NOT_ALLOWED = "rotation_not_allowed"
ROTATE_BLOCK_GUEST_FORBIDDEN = "guest_rotation_forbidden"
ROTATE_BLOCK_SPECIAL = "special_geometry_unavailable"
ROTATE_BLOCK_INCOMPLETE = "incomplete_geometry"
ROTATE_BLOCK_NOT_EDITABLE = "not_editable"
ROTATE_BLOCK_HOSTING = "guest_outside_host_hole"
ROTATE_OK = DROP_OK

ANGLE_EPS = 1e-9


def normalize_angle_deg(value: Any) -> float:
    """Map any finite angle to ``[0, 360)``. Non-finite → 0."""

    try:
        angle = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(angle):
        return 0.0
    angle %= 360.0
    if angle < 0:
        angle += 360.0
    if abs(angle - 360.0) < ANGLE_EPS or abs(angle) < ANGLE_EPS:
        return 0.0
    return angle


def angles_equivalent(a: Any, b: Any, *, eps: float = 1e-6) -> bool:
    first = normalize_angle_deg(a)
    second = normalize_angle_deg(b)
    delta = abs(first - second)
    return min(delta, 360.0 - delta) <= eps


def rotate_point(
    point: Sequence[float],
    pivot: Mapping[str, float] | Sequence[float],
    angle_deg: float,
) -> list[float]:
    px, py = _pivot_xy(pivot)
    x = num(point[0]) - px
    y = num(point[1]) - py
    rad = math.radians(normalize_angle_deg(angle_deg))
    # SVG-compatible: positive angle is clockwise when Y grows downward.
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    return [px + x * cos_a + y * sin_a, py - x * sin_a + y * cos_a]


def rotate_points(
    points: Sequence[Sequence[float]] | None,
    pivot: Mapping[str, float] | Sequence[float],
    angle_deg: float,
) -> list[list[float]] | None:
    if not isinstance(points, list):
        return None
    return [rotate_point(point, pivot, angle_deg) for point in points]


def _pivot_xy(pivot: Mapping[str, float] | Sequence[float]) -> tuple[float, float]:
    if isinstance(pivot, Mapping):
        return num(pivot.get("x")), num(pivot.get("y"))
    return num(pivot[0]), num(pivot[1])


def aabb_center(points: Sequence[Sequence[float]]) -> dict[str, float]:
    xs = [num(point[0]) for point in points]
    ys = [num(point[1]) for point in points]
    return {"x": (min(xs) + max(xs)) * 0.5, "y": (min(ys) + max(ys)) * 0.5}


def pivot_from_piece(piece: Mapping[str, Any]) -> dict[str, float]:
    existing = piece.get("pivot_mm")
    if isinstance(existing, Mapping) and existing.get("x") is not None:
        return {"x": num(existing["x"]), "y": num(existing["y"])}
    base = piece.get("base_outline_mm")
    if isinstance(base, list) and len(base) >= 3:
        return aabb_center(base)
    outline = piece.get("outline_mm")
    if isinstance(outline, list) and len(outline) >= 3:
        return aabb_center(outline)
    placement = piece.get("placement_cm") or {}
    w = num(placement.get("w")) * 10.0
    h = num(placement.get("h")) * 10.0
    if piece.get("source_rotated_dims") and placement.get("rotated"):
        w, h = h, w
    x = num(piece.get("local_x_mm")) if piece.get("local_x_mm") is not None else num(placement.get("x")) * 10.0
    y = num(piece.get("local_y_mm")) if piece.get("local_y_mm") is not None else num(placement.get("y")) * 10.0
    return {"x": x + w * 0.5, "y": y + h * 0.5}


def ensure_base_geometry(piece: dict[str, Any]) -> None:
    """Populate base/pivot once from the current as-loaded outline."""

    if not isinstance(piece.get("base_outline_mm"), list) or len(piece["base_outline_mm"]) < 3:
        outline = piece.get("outline_mm")
        if isinstance(outline, list) and len(outline) >= 3:
            piece["base_outline_mm"] = [[num(p[0]), num(p[1])] for p in outline]
        else:
            placement = piece.get("placement_cm") or {}
            w = num(placement.get("w")) * 10.0
            h = num(placement.get("h")) * 10.0
            if piece.get("source_rotated_dims") and placement.get("rotated"):
                w, h = h, w
            x = (
                num(piece.get("local_x_mm"))
                if piece.get("local_x_mm") is not None
                else num(placement.get("x")) * 10.0
            )
            y = (
                num(piece.get("local_y_mm"))
                if piece.get("local_y_mm") is not None
                else num(placement.get("y")) * 10.0
            )
            piece["base_outline_mm"] = [
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h],
            ]
    if piece.get("base_hole_mm") is None and isinstance(piece.get("glass_hole_local_mm"), list):
        hole = piece["glass_hole_local_mm"]
        piece["base_hole_mm"] = [[num(p[0]), num(p[1])] for p in hole]
    if not isinstance(piece.get("pivot_mm"), Mapping):
        piece["pivot_mm"] = pivot_from_piece(piece)
    if piece.get("entry_pivot_mm") is None:
        piece["entry_pivot_mm"] = {
            "x": num(piece["pivot_mm"]["x"]),
            "y": num(piece["pivot_mm"]["y"]),
        }
    piece["rotation_deg"] = normalize_angle_deg(piece.get("rotation_deg"))


def rederive_outline(piece: dict[str, Any]) -> None:
    ensure_base_geometry(piece)
    angle = normalize_angle_deg(piece.get("rotation_deg"))
    pivot = piece["pivot_mm"]
    base = piece["base_outline_mm"]
    piece["outline_mm"] = rotate_points(base, pivot, angle)
    base_hole = piece.get("base_hole_mm")
    if isinstance(base_hole, list) and len(base_hole) >= 3:
        piece["glass_hole_local_mm"] = rotate_points(base_hole, pivot, angle)
    bounds = piece_footprint_mm(piece)["bounds"]
    piece["local_x_mm"] = bounds["x"]
    piece["local_y_mm"] = bounds["y"]


def translate_piece_geometry(piece: dict[str, Any], dx: float, dy: float) -> None:
    """Translate base, pivot, and derived outlines together (no angle change)."""

    ensure_base_geometry(piece)
    dx = num(dx)
    dy = num(dy)
    if abs(dx) < ANGLE_EPS and abs(dy) < ANGLE_EPS:
        return

    def _shift(points: list[list[float]] | None) -> list[list[float]] | None:
        if not isinstance(points, list):
            return points
        return [[num(p[0]) + dx, num(p[1]) + dy] for p in points]

    piece["base_outline_mm"] = _shift(piece.get("base_outline_mm"))
    if isinstance(piece.get("base_hole_mm"), list):
        piece["base_hole_mm"] = _shift(piece["base_hole_mm"])
    pivot = piece.get("pivot_mm") or {}
    piece["pivot_mm"] = {"x": num(pivot.get("x")) + dx, "y": num(pivot.get("y")) + dy}
    rederive_outline(piece)


def explicit_allow_rotation(piece: Mapping[str, Any]) -> bool:
    """Fail closed: only an explicit truthy order flag permits rotation."""

    if "allow_rotation" not in piece and "allow_rotation_proven" not in piece:
        return False
    # Proven=false means the source never established a flag — deny.
    if piece.get("allow_rotation_proven") is False:
        return False
    flag = piece.get("allow_rotation")
    if flag is True or flag == 1 or flag == "1":
        return True
    return False


def piece_rotation_eligibility(
    piece: Mapping[str, Any],
    *,
    pieces: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not piece.get("editable"):
        return {
            "rotatable": False,
            "reason": piece.get("block_reason") or ROTATE_BLOCK_NOT_EDITABLE,
            "affected_keys": [],
        }
    if piece.get("block_reason") == "special_geometry_unavailable":
        return {
            "rotatable": False,
            "reason": ROTATE_BLOCK_SPECIAL,
            "affected_keys": [],
        }
    ensure_probe = dict(piece)
    ensure_base_geometry(ensure_probe)
    if not isinstance(ensure_probe.get("base_outline_mm"), list) or len(ensure_probe["base_outline_mm"]) < 3:
        return {
            "rotatable": False,
            "reason": ROTATE_BLOCK_INCOMPLETE,
            "affected_keys": [],
        }
    if not explicit_allow_rotation(piece):
        return {
            "rotatable": False,
            "reason": ROTATE_BLOCK_NOT_ALLOWED,
            "affected_keys": [],
        }

    key = str(piece.get("piece_key") or "")
    affected = [key] if key else []
    if pieces and key:
        affected.extend(_guest_keys(pieces, key))
        for guest_key in _guest_keys(pieces, key):
            guest = pieces[guest_key]
            if not explicit_allow_rotation(guest):
                return {
                    "rotatable": False,
                    "reason": ROTATE_BLOCK_GUEST_FORBIDDEN,
                    "blocking_guest_key": guest_key,
                    "affected_keys": affected,
                }
            if not guest.get("editable"):
                return {
                    "rotatable": False,
                    "reason": guest.get("block_reason") or ROTATE_BLOCK_NOT_EDITABLE,
                    "blocking_guest_key": guest_key,
                    "affected_keys": affected,
                }
    return {"rotatable": True, "reason": None, "affected_keys": affected}


def _descendant_guest_keys(
    pieces: Mapping[str, Mapping[str, Any]], host_key: str
) -> list[str]:
    """All nested guests under host (forest walk)."""

    ordered: list[str] = []
    stack = list(_guest_keys(pieces, host_key))
    seen = set()
    while stack:
        key = stack.pop(0)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        stack.extend(_guest_keys(pieces, key))
    return ordered


def _apply_angle_to_piece(piece: dict[str, Any], angle_deg: float) -> None:
    ensure_base_geometry(piece)
    piece["rotation_deg"] = normalize_angle_deg(angle_deg)
    rederive_outline(piece)


def _rigid_rotate_piece_about(
    piece: dict[str, Any],
    host_pivot: Mapping[str, float],
    delta_deg: float,
) -> None:
    """Rotate a guest's base+pivot about the host pivot, then keep own angle."""

    ensure_base_geometry(piece)
    delta = normalize_angle_deg(delta_deg)
    if angles_equivalent(delta, 0):
        return
    piece["base_outline_mm"] = rotate_points(piece["base_outline_mm"], host_pivot, delta)
    if isinstance(piece.get("base_hole_mm"), list):
        piece["base_hole_mm"] = rotate_points(piece["base_hole_mm"], host_pivot, delta)
    old_pivot = [num(piece["pivot_mm"]["x"]), num(piece["pivot_mm"]["y"])]
    rotated_pivot = rotate_point(old_pivot, host_pivot, delta)
    piece["pivot_mm"] = {"x": rotated_pivot[0], "y": rotated_pivot[1]}
    # Own edit angle advances by the same rigid delta (single transform — guests
    # are not nested again under an SVG rotate of the host).
    piece["rotation_deg"] = normalize_angle_deg(num(piece.get("rotation_deg")) + delta)
    rederive_outline(piece)


def preview_piece_rotation(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    rotation_deg: float,
) -> dict[str, Any]:
    """Return a deep-copied session with the proposed rotation applied (no commit)."""

    next_session = deepcopy(dict(session))
    pieces = next_session.get("pieces") or {}
    piece = pieces.get(piece_key)
    if not piece:
        raise KeyError(piece_key)
    ensure_base_geometry(piece)
    target = normalize_angle_deg(rotation_deg)
    current = normalize_angle_deg(piece.get("rotation_deg"))
    delta = normalize_angle_deg(target - current)
    # Signed shortest? For rigid guest update we need exact delta along the
    # chosen target path: target = current + delta (mod 360).
    raw_delta = target - current
    if raw_delta > 180:
        raw_delta -= 360
    elif raw_delta <= -180:
        raw_delta += 360
    host_pivot = dict(piece["pivot_mm"])
    _apply_angle_to_piece(piece, target)
    for guest_key in _descendant_guest_keys(pieces, piece_key):
        _rigid_rotate_piece_about(pieces[guest_key], host_pivot, raw_delta)
    return next_session


def validate_piece_rotation(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    rotation_deg: float,
) -> dict[str, Any]:
    pieces = session.get("pieces") or {}
    piece = pieces.get(piece_key)
    if not piece:
        return {"ok": False, "code": DROP_NOT_EDITABLE, "message": "missing_piece"}

    eligibility = piece_rotation_eligibility(piece, pieces=pieces)
    if not eligibility["rotatable"]:
        return {
            "ok": False,
            "code": eligibility["reason"] or ROTATE_BLOCK_NOT_ALLOWED,
            "message": eligibility["reason"],
            "blocking_guest_key": eligibility.get("blocking_guest_key"),
        }

    target = normalize_angle_deg(rotation_deg)
    if angles_equivalent(target, piece.get("rotation_deg")):
        return {
            "ok": True,
            "code": ROTATE_OK,
            "noop": True,
            "rotation_deg": target,
            "affected_keys": eligibility["affected_keys"],
        }

    trial = preview_piece_rotation(session, piece_key=piece_key, rotation_deg=target)
    trial_pieces = trial["pieces"]
    kerf_mm = num(session.get("kerf_mm"))
    boards = session.get("boards") or {}
    affected = set(eligibility["affected_keys"] or [piece_key])
    affected.update(_descendant_guest_keys(pieces, piece_key))

    for key in affected:
        moved = trial_pieces[key]
        sheet_no = moved.get("sheet_no")
        local_fp = piece_footprint_mm(moved)
        if sheet_no is not None and sheet_no != "":
            board = boards.get(str(sheet_no)) or {}
            if not _footprint_inside_usable(local_fp, board):
                # Distinguish partial overlap of usable from fully outside.
                world = _world_footprint(moved, boards)
                ox = num(board.get("origin_x_mm")) + num(board.get("trim_x_mm"))
                oy = num(board.get("origin_y_mm")) + num(board.get("trim_y_mm"))
                usable = {
                    "x": ox,
                    "y": oy,
                    "w": num(board.get("usable_width_mm")) or num(board.get("width_mm")),
                    "h": num(board.get("usable_length_mm")) or num(board.get("height_mm")),
                }
                code = (
                    DROP_PARTIAL_BOARD
                    if _bounds_intersect(world["bounds"], usable)
                    else DROP_OUTSIDE_USABLE
                )
                return {"ok": False, "code": code, "message": code, "piece_key": key}

        host_key = moved.get("glass_host_key")
        if host_key and host_key in trial_pieces and key == piece_key:
            # Solo guest rotation: must remain inside host hole.
            if not _guest_remains(moved, trial_pieces[host_key]):
                return {
                    "ok": False,
                    "code": ROTATE_BLOCK_HOSTING,
                    "message": ROTATE_BLOCK_HOSTING,
                }

    for key in affected:
        moved = trial_pieces[key]
        sheet_no = moved.get("sheet_no")
        if sheet_no is None or sheet_no == "":
            continue
        moved_local = piece_footprint_mm(moved)
        for other_key, other in trial_pieces.items():
            if other_key in affected:
                continue
            if other.get("sheet_no") != sheet_no:
                continue
            if (
                other.get("glass_host_key") == key
                or moved.get("glass_host_key") == other_key
            ):
                continue
            # Nested guest under a rotating host is in ``affected``.
            if other.get("glass_host_key") in affected:
                continue
            conflict = _pair_conflict(moved_local, piece_footprint_mm(other), kerf_mm=kerf_mm)
            if conflict:
                return {"ok": False, "code": conflict, "message": conflict, "piece_key": key}

    return {
        "ok": True,
        "code": ROTATE_OK,
        "noop": False,
        "rotation_deg": target,
        "affected_keys": list(affected),
    }


def apply_piece_rotation(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    rotation_deg: float,
) -> dict[str, Any]:
    decision = validate_piece_rotation(
        session, piece_key=piece_key, rotation_deg=rotation_deg
    )
    if not decision.get("ok"):
        raise ValueError(decision.get("code") or "rotation_rejected")
    if decision.get("noop"):
        return deepcopy(dict(session))
    next_session = preview_piece_rotation(
        session, piece_key=piece_key, rotation_deg=decision["rotation_deg"]
    )
    piece = next_session["pieces"][piece_key]
    _mark_sheet_artifacts_stale(next_session, piece.get("sheet_no"))
    return next_session


def _bounds_intersect(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
    return not (
        num(a["x"]) + num(a["w"]) <= num(b["x"])
        or num(b["x"]) + num(b["w"]) <= num(a["x"])
        or num(a["y"]) + num(a["h"]) <= num(b["y"])
        or num(b["y"]) + num(b["h"]) <= num(a["y"])
    )


def _guest_remains(guest: Mapping[str, Any], host: Mapping[str, Any]) -> bool:
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
    return guest.get("sheet_no") == host.get("sheet_no")


__all__ = [
    "ROTATE_BLOCK_NOT_ALLOWED",
    "ROTATE_BLOCK_GUEST_FORBIDDEN",
    "ROTATE_BLOCK_SPECIAL",
    "ROTATE_BLOCK_INCOMPLETE",
    "ROTATE_BLOCK_NOT_EDITABLE",
    "ROTATE_BLOCK_HOSTING",
    "ROTATE_OK",
    "normalize_angle_deg",
    "angles_equivalent",
    "rotate_point",
    "rotate_points",
    "aabb_center",
    "pivot_from_piece",
    "ensure_base_geometry",
    "rederive_outline",
    "translate_piece_geometry",
    "explicit_allow_rotation",
    "piece_rotation_eligibility",
    "preview_piece_rotation",
    "validate_piece_rotation",
    "apply_piece_rotation",
]
