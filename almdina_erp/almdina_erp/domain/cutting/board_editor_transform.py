"""Board-editor flip / angle-mirror transforms (framework-free).

Draft fields store transform *parity* only. Geometry is always re-derived from
the trusted entry outline on the server:

1. entry base (source ``corner_mirrored`` already baked in)
2. extra local horizontal ``mirrored`` about the pivot
3. ``flip_h`` / ``flip_v`` as board-axis reflections of the base (rot 0)
4. ``rotation_deg`` about the pivot

A board-axis flip applied while the piece is already rotated uses the
conjugation ``F_board R(θ) = R(-θ) F_local`` so the stored flags stay
canonical. Angle-mirror is only for Clipped Corner / L-Shaped Corner.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import (
    ROTATE_BLOCK_HOSTING,
    ROTATE_BLOCK_INCOMPLETE,
    ROTATE_BLOCK_NOT_ALLOWED,
    ROTATE_BLOCK_NOT_EDITABLE,
    ROTATE_BLOCK_SPECIAL,
    ROTATE_OK,
    _bounds_intersect,
    _descendant_guest_keys,
    _guest_remains,
    ensure_base_geometry,
    machine_accepts_rotation,
    normalize_angle_deg,
    piece_rotation_eligibility,
    rederive_outline,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    DROP_NOT_EDITABLE,
    DROP_OUTSIDE_USABLE,
    DROP_PARTIAL_BOARD,
    _footprint_inside_usable,
    _mark_sheet_artifacts_stale,
    _pair_conflict,
    _world_footprint,
    piece_footprint_mm,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import num
from almdina_erp.almdina_erp.domain.orders.piece_policy import is_corner_cut

TRANSFORM_OK = ROTATE_OK
TRANSFORM_BLOCK_MIRROR = "angle_mirror_unavailable"
TRANSFORM_BLOCK_UNPROVEN = "transform_geometry_unproven"
TRANSFORM_BLOCK_HOSTING = "host_guest_transform_unproven"


def _truthy_flag(value: Any) -> bool:
    return value is True or value == 1 or value == "1"


def draft_flip_h(row: Mapping[str, Any] | None) -> bool:
    return _truthy_flag((row or {}).get("flip_h"))


def draft_flip_v(row: Mapping[str, Any] | None) -> bool:
    return _truthy_flag((row or {}).get("flip_v"))


def draft_mirrored(row: Mapping[str, Any] | None) -> bool:
    return _truthy_flag((row or {}).get("mirrored"))


def angle_mirror_eligibility(piece: Mapping[str, Any]) -> dict[str, Any]:
    """Angle-mirror is corner-cut only and requires the same rotation gate."""

    base = piece_rotation_eligibility(piece, pieces=None)
    if not base.get("rotatable"):
        return {
            "allowed": False,
            "reason": base.get("reason") or ROTATE_BLOCK_NOT_ALLOWED,
        }
    if not is_corner_cut(str(piece.get("piece_type") or "")):
        return {"allowed": False, "reason": TRANSFORM_BLOCK_MIRROR}
    return {"allowed": True, "reason": None}


def board_flip_eligibility(
    piece: Mapping[str, Any],
    *,
    pieces: Mapping[str, Mapping[str, Any]] | None = None,
    piece_key: str | None = None,
) -> dict[str, Any]:
    """Board flips share rotation eligibility for one editable rotatable piece.

    Host/guest trees fail closed until a proven rigid board-axis contract exists.
    """

    eligibility = piece_rotation_eligibility(piece, pieces=pieces)
    if not eligibility.get("rotatable"):
        return {
            "allowed": False,
            "reason": eligibility.get("reason") or ROTATE_BLOCK_NOT_ALLOWED,
            "affected_keys": eligibility.get("affected_keys") or [],
        }
    key = str(piece_key or piece.get("piece_key") or "")
    if piece.get("glass_host_key") or (
        pieces and key and _descendant_guest_keys(pieces, key)
    ):
        return {
            "allowed": False,
            "reason": TRANSFORM_BLOCK_HOSTING,
            "affected_keys": eligibility.get("affected_keys") or [],
        }
    return {
        "allowed": True,
        "reason": None,
        "affected_keys": [key] if key else eligibility.get("affected_keys") or [],
    }


def _reflect_points_horizontal(
    points: Sequence[Sequence[float]] | None,
    *,
    center_x: float,
) -> list[list[float]] | None:
    if not isinstance(points, list):
        return points  # type: ignore[return-value]
    return [[(2.0 * center_x) - num(point[0]), num(point[1])] for point in points]


def _reflect_points_vertical(
    points: Sequence[Sequence[float]] | None,
    *,
    center_y: float,
) -> list[list[float]] | None:
    if not isinstance(points, list):
        return points  # type: ignore[return-value]
    return [[num(point[0]), (2.0 * center_y) - num(point[1])] for point in points]


def apply_local_horizontal_mirror(piece: dict[str, Any]) -> None:
    """Reflect base geometry about the pivot in local X (corner_contour convention)."""

    ensure_base_geometry(piece)
    center_x = num((piece.get("pivot_mm") or {}).get("x"))
    piece["base_outline_mm"] = _reflect_points_horizontal(
        piece.get("base_outline_mm"),
        center_x=center_x,
    )
    if isinstance(piece.get("base_hole_mm"), list):
        piece["base_hole_mm"] = _reflect_points_horizontal(
            piece["base_hole_mm"],
            center_x=center_x,
        )
    _reflect_machining_paths(piece, axis="h")
    piece["mirrored"] = not _truthy_flag(piece.get("mirrored"))
    rederive_outline(piece)


def _reflect_machining_paths(
    piece: dict[str, Any],
    *,
    axis: str,
) -> None:
    paths = piece.get("machining_paths")
    if not isinstance(paths, list):
        return
    center_x = num((piece.get("pivot_mm") or {}).get("x"))
    center_y = num((piece.get("pivot_mm") or {}).get("y"))
    next_paths = []
    for item in paths:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        if axis == "v":
            row["path_mm"] = _reflect_points_vertical(
                item.get("path_mm"),
                center_y=center_y,
            ) or []
        else:
            row["path_mm"] = _reflect_points_horizontal(
                item.get("path_mm"),
                center_x=center_x,
            ) or []
        next_paths.append(row)
    piece["machining_paths"] = next_paths


def apply_local_flip_h(piece: dict[str, Any]) -> None:
    ensure_base_geometry(piece)
    center_x = num((piece.get("pivot_mm") or {}).get("x"))
    piece["base_outline_mm"] = _reflect_points_horizontal(
        piece.get("base_outline_mm"),
        center_x=center_x,
    )
    if isinstance(piece.get("base_hole_mm"), list):
        piece["base_hole_mm"] = _reflect_points_horizontal(
            piece["base_hole_mm"],
            center_x=center_x,
        )
    _reflect_machining_paths(piece, axis="h")
    piece["flip_h"] = not _truthy_flag(piece.get("flip_h"))
    rederive_outline(piece)


def apply_local_flip_v(piece: dict[str, Any]) -> None:
    ensure_base_geometry(piece)
    center_y = num((piece.get("pivot_mm") or {}).get("y"))
    piece["base_outline_mm"] = _reflect_points_vertical(
        piece.get("base_outline_mm"),
        center_y=center_y,
    )
    if isinstance(piece.get("base_hole_mm"), list):
        piece["base_hole_mm"] = _reflect_points_vertical(
            piece["base_hole_mm"],
            center_y=center_y,
        )
    _reflect_machining_paths(piece, axis="v")
    piece["flip_v"] = not _truthy_flag(piece.get("flip_v"))
    rederive_outline(piece)


def apply_board_axis_flip_h(piece: dict[str, Any]) -> None:
    """Board-axis horizontal flip via ``F_x R(θ) = R(-θ) F_x``."""

    ensure_base_geometry(piece)
    apply_local_flip_h(piece)
    piece["rotation_deg"] = normalize_angle_deg(-num(piece.get("rotation_deg")))
    rederive_outline(piece)


def apply_board_axis_flip_v(piece: dict[str, Any]) -> None:
    """Board-axis vertical flip via ``F_y R(θ) = R(-θ) F_y``."""

    ensure_base_geometry(piece)
    apply_local_flip_v(piece)
    piece["rotation_deg"] = normalize_angle_deg(-num(piece.get("rotation_deg")))
    rederive_outline(piece)


def apply_draft_parity_to_entry(piece: dict[str, Any], row: Mapping[str, Any]) -> None:
    """Apply stored draft transform parity onto an entry piece at rotation 0."""

    ensure_base_geometry(piece)
    piece["flip_h"] = False
    piece["flip_v"] = False
    piece["mirrored"] = False
    if draft_mirrored(row):
        apply_local_horizontal_mirror(piece)
    if draft_flip_h(row):
        apply_local_flip_h(piece)
    if draft_flip_v(row):
        apply_local_flip_v(piece)
    piece["flip_h"] = draft_flip_h(row)
    piece["flip_v"] = draft_flip_v(row)
    piece["mirrored"] = draft_mirrored(row)


def preview_piece_board_flip(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    axis: str,
) -> dict[str, Any]:
    next_session = deepcopy(dict(session))
    pieces = next_session.get("pieces") or {}
    piece = pieces.get(piece_key)
    if not piece:
        raise KeyError(piece_key)
    if axis == "v":
        apply_board_axis_flip_v(piece)
    else:
        apply_board_axis_flip_h(piece)
    return next_session


def preview_piece_angle_mirror(
    session: Mapping[str, Any],
    *,
    piece_key: str,
) -> dict[str, Any]:
    next_session = deepcopy(dict(session))
    pieces = next_session.get("pieces") or {}
    piece = pieces.get(piece_key)
    if not piece:
        raise KeyError(piece_key)
    apply_local_horizontal_mirror(piece)
    return next_session


def _validate_trial_pose(
    session: Mapping[str, Any],
    trial: Mapping[str, Any],
    *,
    piece_key: str,
    affected_keys: Sequence[str],
) -> dict[str, Any]:
    """Containment / collision / machine checks for an already-posed trial."""

    trial_pieces = trial.get("pieces") or {}
    boards = session.get("boards") or {}
    kerf_mm = num(session.get("kerf_mm"))
    machine_type = str(session.get("machine_type") or "").strip()
    affected = set(affected_keys or [piece_key])

    for key in affected:
        moved = trial_pieces.get(key)
        if not moved:
            return {"ok": False, "code": DROP_NOT_EDITABLE, "message": "missing_piece"}
        if machine_type and not machine_accepts_rotation(machine_type, moved.get("rotation_deg")):
            return {
                "ok": False,
                "code": "machine_rotation_forbidden",
                "message": "machine_rotation_forbidden",
                "piece_key": key,
            }
        sheet_no = moved.get("sheet_no")
        local_fp = piece_footprint_mm(moved)
        if sheet_no is not None and sheet_no != "":
            board = boards.get(str(sheet_no)) or {}
            if not _footprint_inside_usable(local_fp, board):
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
            if other.get("glass_host_key") in affected:
                continue
            conflict = _pair_conflict(moved_local, piece_footprint_mm(other), kerf_mm=kerf_mm)
            if conflict:
                return {"ok": False, "code": conflict, "message": conflict, "piece_key": key}
    return {"ok": True, "code": TRANSFORM_OK}


def validate_piece_board_flip(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    axis: str,
) -> dict[str, Any]:
    pieces = session.get("pieces") or {}
    piece = pieces.get(piece_key)
    if not piece:
        return {"ok": False, "code": DROP_NOT_EDITABLE, "message": "missing_piece"}
    eligibility = board_flip_eligibility(piece, pieces=pieces, piece_key=piece_key)
    if not eligibility["allowed"]:
        return {
            "ok": False,
            "code": eligibility["reason"] or ROTATE_BLOCK_NOT_ALLOWED,
            "message": eligibility["reason"],
        }
    if not isinstance(piece.get("outline_mm"), list) and not isinstance(
        piece.get("base_outline_mm"), list
    ):
        return {
            "ok": False,
            "code": TRANSFORM_BLOCK_UNPROVEN,
            "message": TRANSFORM_BLOCK_UNPROVEN,
        }
    trial = preview_piece_board_flip(session, piece_key=piece_key, axis=axis)
    pose = _validate_trial_pose(
        session,
        trial,
        piece_key=piece_key,
        affected_keys=eligibility["affected_keys"],
    )
    if not pose.get("ok"):
        return pose
    return {
        "ok": True,
        "code": TRANSFORM_OK,
        "noop": False,
        "axis": "v" if axis == "v" else "h",
        "affected_keys": eligibility["affected_keys"],
        "trial": trial,
    }


def validate_piece_angle_mirror(
    session: Mapping[str, Any],
    *,
    piece_key: str,
) -> dict[str, Any]:
    pieces = session.get("pieces") or {}
    piece = pieces.get(piece_key)
    if not piece:
        return {"ok": False, "code": DROP_NOT_EDITABLE, "message": "missing_piece"}
    eligibility = angle_mirror_eligibility(piece)
    if not eligibility["allowed"]:
        return {
            "ok": False,
            "code": eligibility["reason"] or TRANSFORM_BLOCK_MIRROR,
            "message": eligibility["reason"],
        }
    rot = piece_rotation_eligibility(piece, pieces=pieces)
    if not rot.get("rotatable"):
        return {
            "ok": False,
            "code": rot.get("reason") or ROTATE_BLOCK_NOT_ALLOWED,
            "message": rot.get("reason"),
        }
    if piece.get("glass_host_key") or _descendant_guest_keys(pieces, piece_key):
        # Host/guest trees do not have a trusted local-mirror contract yet.
        return {
            "ok": False,
            "code": TRANSFORM_BLOCK_HOSTING,
            "message": TRANSFORM_BLOCK_HOSTING,
        }
    trial = preview_piece_angle_mirror(session, piece_key=piece_key)
    pose = _validate_trial_pose(
        session,
        trial,
        piece_key=piece_key,
        affected_keys=[piece_key],
    )
    if not pose.get("ok"):
        return pose
    return {
        "ok": True,
        "code": TRANSFORM_OK,
        "noop": False,
        "affected_keys": [piece_key],
        "trial": trial,
    }


def apply_piece_board_flip(
    session: Mapping[str, Any],
    *,
    piece_key: str,
    axis: str,
) -> dict[str, Any]:
    decision = validate_piece_board_flip(session, piece_key=piece_key, axis=axis)
    if not decision.get("ok"):
        return dict(session)
    next_session = decision["trial"]
    _mark_sheet_artifacts_stale(
        next_session,
        next_session["pieces"][piece_key].get("sheet_no"),
    )
    return next_session


def apply_piece_angle_mirror(
    session: Mapping[str, Any],
    *,
    piece_key: str,
) -> dict[str, Any]:
    decision = validate_piece_angle_mirror(session, piece_key=piece_key)
    if not decision.get("ok"):
        return dict(session)
    next_session = decision["trial"]
    _mark_sheet_artifacts_stale(
        next_session,
        next_session["pieces"][piece_key].get("sheet_no"),
    )
    return next_session


def reason_message(code: str | None) -> str:
    mapping = {
        ROTATE_BLOCK_NOT_ALLOWED: "Rotation is not allowed for this piece.",
        ROTATE_BLOCK_SPECIAL: "Special geometry unavailable — not rotatable.",
        ROTATE_BLOCK_INCOMPLETE: "Incomplete geometry — not rotatable.",
        ROTATE_BLOCK_NOT_EDITABLE: "This piece cannot be edited.",
        TRANSFORM_BLOCK_MIRROR: "Angle mirror is only available for corner-break and L pieces.",
        TRANSFORM_BLOCK_UNPROVEN: "This piece cannot be flipped reliably with the available geometry.",
        TRANSFORM_BLOCK_HOSTING: "Host and guest pieces cannot use this transform yet.",
        "multi_selection": "Select one piece to transform it.",
        "no_selection": "Select a piece to transform it.",
    }
    return mapping.get(str(code or ""), str(code or "Transform rejected."))


__all__ = [
    "TRANSFORM_BLOCK_HOSTING",
    "TRANSFORM_BLOCK_MIRROR",
    "TRANSFORM_BLOCK_UNPROVEN",
    "TRANSFORM_OK",
    "angle_mirror_eligibility",
    "apply_draft_parity_to_entry",
    "apply_local_horizontal_mirror",
    "apply_piece_angle_mirror",
    "apply_piece_board_flip",
    "board_flip_eligibility",
    "draft_flip_h",
    "draft_flip_v",
    "draft_mirrored",
    "preview_piece_angle_mirror",
    "preview_piece_board_flip",
    "reason_message",
    "validate_piece_angle_mirror",
    "validate_piece_board_flip",
]
