"""Widen a facing gap when a machining tool actually extends into it.

The cutting kerf stays the default gap and the single CUT_PATH offset. A liner,
back groove, or handle recess keeps its existing centerline extension. When
that centerline leaves the door toward a neighbour, the tool body reaches one
full diameter past the door. The facing gap becomes the larger of the cutting
diameter and that machining diameter. Several tools on the same gap contribute
their maximum, not a sum. A side with no extension does not move its neighbour.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_TOLERANCE_MM,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    liner_parameters_active,
    piece_quarter_turns,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    generate_liner_set_toolpaths,
    generate_toolpath,
    machining_values,
)
from almdina_erp.almdina_erp.domain.cutting.placement_orientation import (
    recorded_mirror,
)
from almdina_erp.almdina_erp.domain.cutting.tool_diameters import LAYER_FIELDS

Point = tuple[float, float]
PathRecord = tuple[list[Point], float]
CM_TO_MM = 10.0
_GAP_TOLERANCE_CM = 0.001


def _num(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def _diameter_mm(kind: str, diameters: Mapping[str, Any], kerf_mm: float) -> float | None:
    raw = diameters.get(kind)
    if raw in (None, ""):
        for kind_name, field in LAYER_FIELDS:
            if kind_name == kind:
                raw = diameters.get(field)
                break
    try:
        number = float(raw) if raw not in (None, "") else kerf_mm
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= GEOMETRY_TOLERANCE_MM:
        return None
    return number


def _active(spec: Mapping[str, Any]) -> bool:
    if liner_parameters_active(
        enabled=bool(spec.get("enabled")),
        side=str(spec.get("side") or ""),
        offset_cm=_num(spec.get("offset_cm")),
        width_cm=_num(spec.get("width_cm")),
    ):
        return True
    return any(
        str(item.get("side") or "").strip()
        and _num(item.get("width_cm") or spec.get("width_cm")) > 0
        for item in (spec.get("liners") or ())
        if isinstance(item, Mapping)
    )


def _host_piece(piece: Mapping[str, Any]) -> LinerPiece | None:
    if str(piece.get("piece_type") or "Regular") == "Special":
        return None
    width = (
        piece.get("original_w")
        or piece.get("width_cm")
        or piece.get("cut_width_cm")
        or 0
    )
    length = (
        piece.get("original_h")
        or piece.get("length_cm")
        or piece.get("cut_length_cm")
        or 0
    )
    width_cm = _num(width)
    length_cm = _num(length)
    if width_cm <= 0 or length_cm <= 0:
        return None
    return LinerPiece(
        str(piece.get("piece_type") or "Regular"),
        width_cm,
        length_cm,
        str(piece.get("clipped_corner_position") or "Top Right"),
        _num(piece.get("clipped_corner_width_cm")),
        _num(piece.get("clipped_corner_length_cm")),
    )


def _toolpaths(
    piece: Mapping[str, Any],
    diameters: Mapping[str, Any],
    kerf_mm: float,
) -> tuple[list[PathRecord], list[str]]:
    """Return world-ready local paths and any generation failures."""

    host = _host_piece(piece)
    if host is None:
        return [], []
    values = machining_values(piece)
    paths: list[PathRecord] = []
    failures: list[str] = []
    label = str(piece.get("label") or piece.get("piece_no") or piece.get("id") or "")
    for kind, _field in LAYER_FIELDS:
        spec = values.get(kind) or {}
        if not isinstance(spec, Mapping) or not _active(spec):
            continue
        diameter = _diameter_mm(kind, diameters, kerf_mm)
        if diameter is None:
            failures.append(
                f"Piece {label} has no usable {kind} tool diameter for machining clearance."
            )
            continue
        try:
            liners = tuple(spec.get("liners") or ())
            if kind == "liner" and len(liners) > 1:
                generated = generate_liner_set_toolpaths(
                    piece=host,
                    specs=liners,
                    width_cm=_num(spec.get("width_cm")),
                    cutter_diameter_mm=diameter,
                )
            else:
                generated = [
                    generate_toolpath(
                        kind=kind,
                        piece=host,
                        reference_side=str(spec.get("side") or ""),
                        offset_cm=_num(spec.get("offset_cm")),
                        width_cm=_num(spec.get("width_cm")),
                        start_cm=spec.get("start_cm"),
                        length_cm=spec.get("length_cm"),
                        cutter_diameter_mm=diameter,
                    )
                ]
        except LinerGeometryError as error:
            failures.append(
                f"Piece {label} machining clearance could not be calculated ({error.code})."
            )
            continue
        for path in generated:
            if len(path) >= 2:
                paths.append(([(float(point[0]), float(point[1])) for point in path], diameter))
    return paths, failures


def _world_paths(
    piece: Mapping[str, Any],
    paths: Sequence[PathRecord],
) -> list[PathRecord]:
    host = _host_piece(piece)
    if host is None:
        return []
    width = host.width_cm * CM_TO_MM
    height = host.length_cm * CM_TO_MM
    origin_x = _num(piece.get("x")) * CM_TO_MM
    origin_y = _num(piece.get("y")) * CM_TO_MM
    turns = piece_quarter_turns(piece)
    mirrored = recorded_mirror(piece)
    world: list[PathRecord] = []
    for path, diameter in paths:
        transformed = []
        for point in path:
            x, y = transform_point(
                point,
                mirrored=mirrored,
                quarter_turns=turns,
                width=width,
                height=height,
            )
            transformed.append((x + origin_x, y + origin_y))
        world.append((transformed, diameter))
    return world


def _bounds_mm(piece: Mapping[str, Any]) -> tuple[float, float, float, float]:
    left = _num(piece.get("x")) * CM_TO_MM
    top = _num(piece.get("y")) * CM_TO_MM
    return (
        left,
        left + _num(piece.get("w")) * CM_TO_MM,
        top,
        top + _num(piece.get("h")) * CM_TO_MM,
    )


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return min(end_a, end_b) - max(start_a, start_b)


def extension_diameter_toward_mm(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    side: str,
    paths: Sequence[PathRecord],
) -> float:
    """Largest tool whose extended body actually reaches toward ``target``.

    ``side`` is the placed edge of ``source`` that faces ``target``:
    ``left``, ``right``, ``top``, or ``bottom`` in the sheet frame (y downward).
    """

    left, right, top, bottom = _bounds_mm(source)
    target_left, target_right, target_top, target_bottom = _bounds_mm(target)
    best = 0.0
    for path, diameter in _world_paths(source, paths):
        radius = diameter / 2.0
        for x, y in path:
            if side == "right" and x <= right + GEOMETRY_TOLERANCE_MM:
                continue
            if side == "left" and x >= left - GEOMETRY_TOLERANCE_MM:
                continue
            if side == "bottom" and y <= bottom + GEOMETRY_TOLERANCE_MM:
                continue
            if side == "top" and y >= top - GEOMETRY_TOLERANCE_MM:
                continue
            if side in {"left", "right"}:
                span = _overlap(y - radius, y + radius, target_top, target_bottom)
            else:
                span = _overlap(x - radius, x + radius, target_left, target_right)
            if span > GEOMETRY_TOLERANCE_MM:
                best = max(best, diameter)
    return best


def _hosted(piece: Mapping[str, Any]) -> bool:
    return piece.get("glass_host_piece_id") not in (None, "")


def _piece_id(piece: Mapping[str, Any]) -> int | None:
    try:
        return int(piece.get("id"))
    except (TypeError, ValueError):
        return None


def required_gap_cm(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    axis: str,
    paths_by_id: Mapping[int, Sequence[PathRecord]],
    *,
    kerf_cm: float,
) -> float | None:
    """Return the machining gap, or None when kerf already covers the pair."""

    kerf_mm = max(0.0, kerf_cm) * CM_TO_MM
    if axis == "horizontal":
        left, right = (first, second) if _num(first.get("x")) <= _num(second.get("x")) else (second, first)
        left_id = _piece_id(left)
        right_id = _piece_id(right)
        diameters = (
            extension_diameter_toward_mm(left, right, "right", paths_by_id.get(left_id, ())),
            extension_diameter_toward_mm(right, left, "left", paths_by_id.get(right_id, ())),
        )
    else:
        top, bottom = (first, second) if _num(first.get("y")) <= _num(second.get("y")) else (second, first)
        top_id = _piece_id(top)
        bottom_id = _piece_id(bottom)
        diameters = (
            extension_diameter_toward_mm(top, bottom, "bottom", paths_by_id.get(top_id, ())),
            extension_diameter_toward_mm(bottom, top, "top", paths_by_id.get(bottom_id, ())),
        )
    largest = max(diameters)
    if largest <= kerf_mm + GEOMETRY_TOLERANCE_MM:
        return None
    return largest / CM_TO_MM


def _paths_by_piece(
    pieces: Sequence[Mapping[str, Any]],
    diameters: Mapping[str, Any],
    kerf_mm: float,
) -> tuple[dict[int, list[PathRecord]], list[str]]:
    paths: dict[int, list[PathRecord]] = {}
    failures: list[str] = []
    for piece in pieces:
        piece_id = _piece_id(piece)
        if piece_id is None or _hosted(piece):
            continue
        local, errors = _toolpaths(piece, diameters, kerf_mm)
        failures.extend(errors)
        paths[piece_id] = local
    return paths, failures


def _shift_group(
    pieces: Sequence[dict[str, Any]],
    selected: set[int],
    axis: str,
    delta: float,
    guests: Mapping[int, Sequence[dict[str, Any]]],
) -> None:
    for piece in pieces:
        piece_id = _piece_id(piece)
        if piece_id not in selected:
            continue
        piece[axis] = _num(piece.get(axis)) + delta
        for guest in guests.get(piece_id, ()):
            guest[axis] = _num(guest.get(axis)) + delta


def _inside_board(
    pieces: Sequence[Mapping[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
) -> bool:
    for piece in pieces:
        x = _num(piece.get("x"))
        y = _num(piece.get("y"))
        if (
            x < -_GAP_TOLERANCE_CM
            or y < -_GAP_TOLERANCE_CM
            or x + _num(piece.get("w")) > board_w_cm + _GAP_TOLERANCE_CM
            or y + _num(piece.get("h")) > board_h_cm + _GAP_TOLERANCE_CM
        ):
            return False
    return True


def _separate_sheet(
    pieces: list[dict[str, Any]],
    paths_by_id: Mapping[int, Sequence[PathRecord]],
    *,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    sheet_no: Any,
) -> list[str]:
    """Push facing doors apart. Return messages when the board cannot hold them."""

    free = [piece for piece in pieces if not _hosted(piece)]
    guests: dict[int, list[dict[str, Any]]] = {}
    for piece in pieces:
        if not _hosted(piece):
            continue
        try:
            host_id = int(piece.get("glass_host_piece_id"))
        except (TypeError, ValueError):
            continue
        guests.setdefault(host_id, []).append(piece)
    if len(free) < 2:
        return []

    def demand(first: Mapping[str, Any], second: Mapping[str, Any], axis: str) -> float | None:
        return required_gap_cm(first, second, axis, paths_by_id, kerf_cm=kerf_cm)

    unresolved: list[str] = []
    for _ in range(len(free) * len(free) + 2):
        moved = False
        for index, first in enumerate(free):
            for second in free[index + 1 :]:
                y_overlap = _overlap(
                    _num(first.get("y")),
                    _num(first.get("y")) + _num(first.get("h")),
                    _num(second.get("y")),
                    _num(second.get("y")) + _num(second.get("h")),
                )
                x_overlap = _overlap(
                    _num(first.get("x")),
                    _num(first.get("x")) + _num(first.get("w")),
                    _num(second.get("x")),
                    _num(second.get("x")) + _num(second.get("w")),
                )
                pair = None
                if y_overlap > _GAP_TOLERANCE_CM and x_overlap <= _GAP_TOLERANCE_CM:
                    pair = ("x", "horizontal")
                elif x_overlap > _GAP_TOLERANCE_CM and y_overlap <= _GAP_TOLERANCE_CM:
                    pair = ("y", "vertical")
                if pair is None:
                    continue
                axis, name = pair
                need = demand(first, second, name)
                if need is None:
                    continue
                if axis == "x":
                    left, right = (first, second) if _num(first.get("x")) <= _num(second.get("x")) else (second, first)
                    gap = _num(right.get("x")) - (_num(left.get("x")) + _num(left.get("w")))
                    anchor = left
                    follower = right
                    follow_test = lambda piece, edge=_num(right.get("x")): _num(piece.get("x")) >= edge - _GAP_TOLERANCE_CM
                    lead_test = lambda piece, edge=_num(left.get("x")) + _num(left.get("w")): (
                        _num(piece.get("x")) + _num(piece.get("w")) <= edge + _GAP_TOLERANCE_CM
                    )
                else:
                    top, bottom = (first, second) if _num(first.get("y")) <= _num(second.get("y")) else (second, first)
                    gap = _num(bottom.get("y")) - (_num(top.get("y")) + _num(top.get("h")))
                    anchor = top
                    follower = bottom
                    follow_test = lambda piece, edge=_num(bottom.get("y")): _num(piece.get("y")) >= edge - _GAP_TOLERANCE_CM
                    lead_test = lambda piece, edge=_num(top.get("y")) + _num(top.get("h")): (
                        _num(piece.get("y")) + _num(piece.get("h")) <= edge + _GAP_TOLERANCE_CM
                    )
                if gap + _GAP_TOLERANCE_CM >= need:
                    continue
                deficit = need - gap
                size_key = "w" if axis == "x" else "h"
                board = board_w_cm if axis == "x" else board_h_cm
                high_ids = {
                    piece_id
                    for piece in free
                    if (piece_id := _piece_id(piece)) is not None and follow_test(piece)
                }
                low_ids = {
                    piece_id
                    for piece in free
                    if (piece_id := _piece_id(piece)) is not None and lead_test(piece)
                }
                high_edges = [
                    _num(piece.get(axis)) + _num(piece.get(size_key))
                    for piece in free
                    if _piece_id(piece) in high_ids
                ]
                low_edges = [
                    _num(piece.get(axis))
                    for piece in free
                    if _piece_id(piece) in low_ids
                ]
                slack_high = board - max(high_edges) if high_edges else -1.0
                slack_low = min(low_edges) if low_edges else -1.0
                if slack_high >= deficit - _GAP_TOLERANCE_CM:
                    _shift_group(free, high_ids, axis, deficit, guests)
                elif slack_low >= deficit - _GAP_TOLERANCE_CM:
                    _shift_group(free, low_ids, axis, -deficit, guests)
                elif slack_high + slack_low >= deficit - _GAP_TOLERANCE_CM:
                    _shift_group(free, high_ids, axis, slack_high, guests)
                    _shift_group(free, low_ids, axis, -(deficit - slack_high), guests)
                else:
                    unresolved.append(
                        "Pieces "
                        f"{anchor.get('label')} and {follower.get('label')} need {need:.2f} cm "
                        "between them for machining clearance on sheet "
                        f"{sheet_no}; the layout leaves {gap:.2f} cm and the board cannot absorb it."
                    )
                    return unresolved
                moved = True
        if not moved:
            break
    else:
        unresolved.append(
            f"Machining clearance on sheet {sheet_no} did not settle inside the board."
        )
        return unresolved
    if not _inside_board(pieces, board_w_cm, board_h_cm):
        unresolved.append(
            f"Machining clearance pushes a door outside sheet {sheet_no}."
        )
    return unresolved


def machining_clearance_problems(
    plan: Mapping[str, Any],
    *,
    kerf_cm: float | None = None,
) -> list[str]:
    """Describe facing gaps that are still shorter than an extended machining tool."""

    diameters = plan.get("machining_diameters_mm")
    if not isinstance(diameters, Mapping):
        return []
    kerf = _num(kerf_cm if kerf_cm is not None else plan.get("kerf_cm"))
    messages: list[str] = []
    for sheet in plan.get("sheets") or ():
        if not isinstance(sheet, Mapping):
            continue
        placed = [dict(piece) for piece in sheet.get("pieces") or () if isinstance(piece, Mapping)]
        paths, failures = _paths_by_piece(placed, diameters, kerf * CM_TO_MM)
        messages.extend(failures)
        free = [piece for piece in placed if not _hosted(piece)]
        for index, first in enumerate(free):
            for second in free[index + 1 :]:
                y_overlap = _overlap(
                    _num(first.get("y")),
                    _num(first.get("y")) + _num(first.get("h")),
                    _num(second.get("y")),
                    _num(second.get("y")) + _num(second.get("h")),
                )
                x_overlap = _overlap(
                    _num(first.get("x")),
                    _num(first.get("x")) + _num(first.get("w")),
                    _num(second.get("x")),
                    _num(second.get("x")) + _num(second.get("w")),
                )
                if y_overlap > _GAP_TOLERANCE_CM and x_overlap <= _GAP_TOLERANCE_CM:
                    axis = "horizontal"
                    left, right = (first, second) if _num(first.get("x")) <= _num(second.get("x")) else (second, first)
                    gap = _num(right.get("x")) - (_num(left.get("x")) + _num(left.get("w")))
                    pair = (left, right)
                elif x_overlap > _GAP_TOLERANCE_CM and y_overlap <= _GAP_TOLERANCE_CM:
                    axis = "vertical"
                    top, bottom = (first, second) if _num(first.get("y")) <= _num(second.get("y")) else (second, first)
                    gap = _num(bottom.get("y")) - (_num(top.get("y")) + _num(top.get("h")))
                    pair = (top, bottom)
                else:
                    continue
                need = required_gap_cm(pair[0], pair[1], axis, paths, kerf_cm=kerf)
                if need is not None and gap + _GAP_TOLERANCE_CM < need:
                    messages.append(
                        "Pieces "
                        f"{pair[0].get('label')} and {pair[1].get('label')} need {need:.2f} cm "
                        "between them for machining clearance on sheet "
                        f"{sheet.get('sheet_no')}; the layout leaves {gap:.2f} cm."
                    )
    return messages


def apply_machining_clearance(
    plan: dict[str, Any],
    *,
    kerf_cm: float,
    board_w_cm: float,
    board_h_cm: float,
    diameters: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Separate facing doors on a copy. None means the board cannot hold the gap.

    Positions change on a copy. None means the board cannot hold the gap and
    the input positions stay as they were. A plan that needs no extra gap is
    returned as the same object, with the diameters published on it, so
    nesting identity stays stable.
    """

    if not isinstance(diameters, Mapping) or not diameters:
        return plan
    from copy import deepcopy

    trial = deepcopy(plan)
    trial.pop("machining_clearance_unresolved", None)
    trial["machining_diameters_mm"] = _published_diameters(diameters)
    trial["kerf_cm"] = kerf_cm
    kerf_mm = kerf_cm * CM_TO_MM
    moved = False
    for sheet in trial.get("sheets") or ():
        placed = [piece for piece in sheet.get("pieces") or () if isinstance(piece, dict)]
        paths, failures = _paths_by_piece(placed, diameters, kerf_mm)
        if failures:
            return None
        snapshot = [(piece.get("x"), piece.get("y")) for piece in placed]
        problems = _separate_sheet(
            placed,
            paths,
            kerf_cm=kerf_cm,
            board_w_cm=_num(sheet.get("w")) or board_w_cm,
            board_h_cm=_num(sheet.get("h")) or board_h_cm,
            sheet_no=sheet.get("sheet_no"),
        )
        if problems:
            return None
        if [(piece.get("x"), piece.get("y")) for piece in placed] != snapshot:
            moved = True
    if not moved:
        plan.pop("machining_clearance_unresolved", None)
        plan["machining_diameters_mm"] = trial["machining_diameters_mm"]
        plan["kerf_cm"] = kerf_cm
        return plan
    return trial


def mark_unresolved_clearance(
    plan: Mapping[str, Any],
    *,
    kerf_cm: float,
    diameters: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish the failed clearance check without moving the supplied layout."""

    marked = dict(plan)
    marked["machining_diameters_mm"] = _published_diameters(diameters)
    marked["machining_clearance_unresolved"] = True
    marked["kerf_cm"] = kerf_cm
    return marked


def _published_diameters(diameters: Mapping[str, Any]) -> dict[str, float]:
    return {
        str(key): _num(value)
        for key, value in diameters.items()
        if _num(value) > 0 or key == "kerf_mm"
    }


__all__ = [
    "apply_machining_clearance",
    "extension_diameter_toward_mm",
    "machining_clearance_problems",
    "mark_unresolved_clearance",
    "required_gap_cm",
]
