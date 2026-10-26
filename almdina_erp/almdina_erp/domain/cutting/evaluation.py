from __future__ import annotations

import math
import time
from typing import Any

from .glass_opening_nesting import host_link_errors, layout_pair_fault
from .primitives import num, present_shop_floor_packing

# Returned alone when an optional validation deadline elapses mid-check.
VALIDATION_DEADLINE_EXCEEDED = "__validation_deadline_exceeded__"


def _placement_outline_bounds(
    placed: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    outline = placed.get("placement_outline_cm")
    if not isinstance(outline, (list, tuple)) or len(outline) < 3:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in outline:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        xs.append(float(point[0]))
        ys.append(float(point[1]))
    min_x = min(xs)
    min_y = min(ys)
    return min_x, min_y, max(xs) - min_x, max(ys) - min_y


def _angle_matches(left: float, right: float) -> bool:
    return abs((left - right + 180.0) % 360.0 - 180.0) <= 0.05


def _void_rotation_matches_piece(
    placed: dict[str, Any],
    source: dict[str, Any],
    tolerance: float,
) -> bool:
    """Accept one stored angle only when it is the proven void-edge angle.

    Quarter-turns stay on the historical ``rotated`` flag. An outline whose
    angle disagrees with the void edge keeps the ordinary dimension check.
    """

    outline = placed.get("placement_outline_cm")
    if not isinstance(outline, (list, tuple)) or len(outline) < 4:
        return False
    try:
        rotation = float(placed.get("placement_rotation_deg"))
        void_angle = float(placed.get("placement_void_angle_deg"))
    except (TypeError, ValueError):
        return False
    if abs(rotation % 90.0) <= 0.05:
        return False
    if not (
        _angle_matches(rotation, void_angle)
        or _angle_matches(rotation, void_angle + 180.0)
    ):
        return False
    points = [(float(point[0]), float(point[1])) for point in outline]
    edge_x = points[1][0] - points[0][0]
    edge_y = points[1][1] - points[0][1]
    if math.hypot(edge_x, edge_y) <= 1e-6:
        return False
    edge_angle = math.degrees(math.atan2(edge_y, edge_x))
    if not any(
        _angle_matches(edge_angle, rotation + turn) for turn in (0.0, 90.0, 180.0, 270.0)
    ):
        return False
    lengths = sorted(
        math.hypot(points[(index + 1) % len(points)][0] - point[0], points[(index + 1) % len(points)][1] - point[1])
        for index, point in enumerate(points)
    )
    width = num(source.get("width_cm"))
    height = num(source.get("length_cm"))
    short = min(width, height)
    long = max(width, height)
    slack = max(tolerance, 0.02)
    return (
        abs(lengths[0] - short) <= slack
        and abs(lengths[1] - short) <= slack
        and abs(lengths[-1] - long) <= slack
        and abs(lengths[-2] - long) <= slack
    )


def placement_permission_errors(
    plan: dict[str, Any],
    requested_pieces: list[dict[str, Any]],
    *,
    mirroring_allowed: bool,
) -> list[str]:
    """Reject a recorded quarter-turn or mirror the piece is not allowed to use.

    The clipped-void outline is the one non-quarter exception and is not a
    quarter-turn. Pieces without an explicit turn record stay on the
    historical ``rotated`` check inside ``validate_plan``.
    """

    from .placement_orientation import (
        PlacementOrientation,
        PlacementOrientationError,
        assert_orientation_allowed,
    )

    expected = {int(piece["id"]): piece for piece in requested_pieces}
    errors: list[str] = []
    for sheet in plan.get("sheets") or []:
        for placed in sheet.get("pieces") or []:
            if placed.get("placement_outline_cm"):
                continue
            turns = placed.get("corner_rotation_quarter_turns")
            if not isinstance(turns, int):
                recorded = placed.get("placement_quarter_turns")
                turns = recorded if isinstance(recorded, int) else None
            if not isinstance(turns, int):
                continue
            try:
                piece_id = int(placed["id"])
            except (TypeError, ValueError):
                continue
            source = expected.get(piece_id)
            if source is None:
                continue
            mirrored = bool(
                placed.get("mirrored")
                or placed.get("corner_mirrored")
                or placed.get("placement_mirrored")
            )
            try:
                assert_orientation_allowed(
                    PlacementOrientation(mirrored, int(turns) % 4),
                    mirroring_allowed=mirroring_allowed,
                    allow_rotation=source.get("allow_rotation"),
                )
            except PlacementOrientationError as exc:
                errors.append(
                    f"Piece {placed.get('label')} orientation is not allowed ({exc.code})."
                )
    return errors


def evaluate_plan(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    method_label: str,
    method_key: str,
    complexity: int = 1,
) -> dict[str, Any]:
    used_area = sum(num(piece.get("area_m2")) for piece in pieces)
    total_board_area = len(plan["sheets"]) * (board_w_cm * board_h_cm / 10000)
    waste_area = max(0.0, total_board_area - used_area)
    score = (
        len(plan["unplaced"]) * 1_000_000_000
        + len(plan["sheets"]) * 1_000_000
        + waste_area * 1000
        + complexity
    )
    present_shop_floor_packing(plan, board_h_cm=board_h_cm)
    return {
        "method_key": method_key,
        "method_label": method_label,
        "sheets": plan["sheets"],
        "unplaced": plan["unplaced"],
        "used_area_m2": used_area,
        "total_board_area_m2": total_board_area,
        "waste_area_m2": waste_area,
        "score": score,
        "complexity": complexity,
    }


def validate_plan(
    plan: dict[str, Any],
    requested_pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    tolerance: float = 1e-7,
    *,
    kerf_cm: float = 0.0,
    deadline_monotonic: float | None = None,
) -> list[str]:
    """Independent geometry validator required before a plan can be approved.

    ``deadline_monotonic`` is optional. Nesting uses it so a candidate check
    cannot ignore the post-pass time budget during O(n²) pair scans. Callers
    that omit it keep the historical unbounded validation path.
    """

    errors: list[str] = []
    expected = {int(piece["id"]): piece for piece in requested_pieces}
    seen: dict[int, int] = {}
    required_kerf_cm = max(0.0, num(kerf_cm))

    for sheet in plan.get("sheets", []):
        pieces = sheet.get("pieces", [])
        for placed in pieces:
            piece_id = int(placed["id"])
            seen[piece_id] = seen.get(piece_id, 0) + 1
            x, y, w, h = map(
                num,
                (
                    placed.get("x"),
                    placed.get("y"),
                    placed.get("w"),
                    placed.get("h"),
                ),
            )
            stored_w, stored_h = w, h
            outline_box = _placement_outline_bounds(placed)
            if outline_box is not None:
                x, y, w, h = outline_box
            if (
                x < -tolerance
                or y < -tolerance
                or x + w > board_w_cm + tolerance
                or y + h > board_h_cm + tolerance
            ):
                errors.append(
                    f"Piece {placed.get('label')} exceeds usable board bounds "
                    f"on sheet {sheet.get('sheet_no')}."
                )
            source = expected.get(piece_id)
            if not source:
                errors.append(f"Unknown piece id {piece_id} exists in plan.")
                continue
            allowed = {
                (
                    num(source["width_cm"]),
                    num(source["length_cm"]),
                    False,
                )
            }
            if source.get("allow_rotation") and num(source["width_cm"]) != num(
                source["length_cm"]
            ):
                allowed.add(
                    (
                        num(source["length_cm"]),
                        num(source["width_cm"]),
                        True,
                    )
                )
            if _void_rotation_matches_piece(placed, source, tolerance):
                continue
            actual = (stored_w, stored_h, bool(placed.get("rotated")))
            if not any(
                abs(actual[0] - allowed_value[0]) <= tolerance
                and abs(actual[1] - allowed_value[1]) <= tolerance
                and actual[2] == allowed_value[2]
                for allowed_value in allowed
            ):
                errors.append(
                    f"Piece {placed.get('label')} has invalid dimensions or rotation state."
                )

        linked = []
        for placed in pieces:
            row = dict(placed)
            row["_sheet_no"] = sheet.get("sheet_no")
            linked.append(row)
        errors.extend(host_link_errors(linked))
        for index, first in enumerate(pieces):
            if (
                deadline_monotonic is not None
                and time.monotonic() > deadline_monotonic
            ):
                return [VALIDATION_DEADLINE_EXCEEDED]
            first_rect = {
                "x": num(first["x"]),
                "y": num(first["y"]),
                "w": num(first["w"]),
                "h": num(first["h"]),
            }
            for second in pieces[index + 1 :]:
                if (
                    deadline_monotonic is not None
                    and time.monotonic() > deadline_monotonic
                ):
                    return [VALIDATION_DEADLINE_EXCEEDED]
                second_rect = {
                    "x": num(second["x"]),
                    "y": num(second["y"]),
                    "w": num(second["w"]),
                    "h": num(second["h"]),
                }
                hosted = first.get("glass_host_piece_id") not in (None, "") or second.get(
                    "glass_host_piece_id"
                ) not in (None, "")
                fault = layout_pair_fault(
                    first,
                    second,
                    kerf_cm=required_kerf_cm,
                    tolerance=tolerance,
                    sheet_pieces=pieces,
                    first_rect=first_rect,
                    second_rect=second_rect,
                )
                if fault is None:
                    continue
                if fault == "overlap":
                    errors.append(
                        f"Pieces {first.get('label')} and {second.get('label')} overlap "
                        f"on sheet {sheet.get('sheet_no')}."
                    )
                elif fault in {"invalid", "unproven"} or (fault == "kerf" and hosted):
                    errors.append(
                        f"Pieces {first.get('label')} and {second.get('label')} do not form "
                        f"a valid Glass opening nest on sheet {sheet.get('sheet_no')}."
                    )
                elif fault == "kerf" and required_kerf_cm:
                    errors.append(
                        f"Pieces {first.get('label')} and {second.get('label')} do not preserve "
                        f"the required {required_kerf_cm:g} cm kerf clearance on sheet "
                        f"{sheet.get('sheet_no')}."
                    )

    for piece_id, piece in expected.items():
        count = seen.get(piece_id, 0)
        if count != 1:
            errors.append(
                f"Piece {piece.get('label')} appears {count} times; expected exactly once."
            )

    if plan.get("unplaced"):
        errors.append(f"Plan contains {len(plan['unplaced'])} unplaced piece(s).")
    return errors


__all__ = [
    "VALIDATION_DEADLINE_EXCEEDED",
    "evaluate_plan",
    "validate_plan",
]
