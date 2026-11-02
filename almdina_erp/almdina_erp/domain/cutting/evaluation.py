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
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        xs.append(x)
        ys.append(y)
    min_x = min(xs)
    min_y = min(ys)
    return min_x, min_y, max(xs) - min_x, max(ys) - min_y


def _angle_matches(left: float, right: float) -> bool:
    return abs((left - right + 180.0) % 360.0 - 180.0) <= 0.05


def _void_rotation_matches_piece(
    placed: dict[str, Any],
    source: dict[str, Any],
    tolerance: float,
    sheet_pieces: list[dict[str, Any]],
    expected: dict[int, dict[str, Any]],
    kerf_cm: float | None,
) -> bool:
    """Accept one stored angle only when it is the proven void-edge angle.

    Quarter-turns stay on the historical ``rotated`` flag. An outline whose
    angle disagrees with the void edge keeps the ordinary dimension check.
    """

    # Only the plain rectangular guest has a proven non-quarter DXF/import
    # contract. Glass holes and machining paths still require quarter turns.
    if str(source.get("piece_type") or "Regular") != "Regular" or any(
        source.get(key) for key in ("extra_liner", "extra_back_groove", "extra_recessed_handle_cutout")
    ):
        return False
    outline = placed.get("placement_outline_cm")
    if not isinstance(outline, (list, tuple)) or len(outline) != 4:
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
    if _placement_outline_bounds(placed) is None or not math.isfinite(rotation + void_angle):
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
    if not (
        abs(lengths[0] - short) <= slack
        and abs(lengths[1] - short) <= slack
        and abs(lengths[-1] - long) <= slack
        and abs(lengths[-2] - long) <= slack
    ):
        return False
    from .shape_aware_nesting import (
        _clears, _contour_sits_in_void, _notch_bounds, _placed_corner,
        _rotated_rectangle, non_quarter_rotation_is_admitted,
    )
    from .dxf_geometry import point_in_polygon
    from .glass_opening_nesting import material_outline_cm

    cx = sum(point[0] for point in points) / 4
    cy = sum(point[1] for point in points) / 4
    exact = _rotated_rectangle(cx, cy, width, height, rotation)
    if any(math.hypot(x - ex, y - ey) > tolerance for (x, y), (ex, ey) in zip(points, exact)):
        return False
    clips = []
    for other in sheet_pieces:
        original = expected.get(int(other["id"]), {})
        if original.get("piece_type") != "Clipped Corner":
            continue
        canonical = _placed_corner(
            original, x_cm=num(other.get("x")), y_cm=num(other.get("y")),
            mirrored=bool(other.get("corner_mirrored")),
            turns=int(other.get("corner_rotation_quarter_turns") or (1 if other.get("rotated") else 0)),
        )
        ring = material_outline_cm(canonical)
        notch = _notch_bounds(ring)
        if ring is None or notch is None:
            continue
        if not non_quarter_rotation_is_admitted(
            rotation, cut_width_cm=notch["w"], cut_length_cm=notch["h"],
            outline_inside_void=True,
        ):
            continue
        bx = num(other.get("x")) + num(other.get("w")) / 2
        by = num(other.get("y")) + num(other.get("h")) / 2
        # The missing corner must face the guest, one host per quadrant.
        nx = notch["x"] + notch["w"] / 2
        ny = notch["y"] + notch["h"] / 2
        if (nx - bx) * (cx - bx) <= 0 or (ny - by) * (cy - by) <= 0:
            continue
        clips.append(((bx - cx) ** 2 + (by - cy) ** 2, (bx < cx, by < cy), ring))
    nearby = sorted(clips, key=lambda item: item[0])[:4]
    rings = [item[2] for item in nearby]
    if len(nearby) != 4 or len({item[1] for item in nearby}) != 4:
        return False
    boxes = [(min(x for x, _ in ring), min(y for _, y in ring),
              max(x for x, _ in ring), max(y for _, y in ring)) for ring in rings]
    widths = [box[2] - box[0] for box in boxes]
    heights = [box[3] - box[1] for box in boxes]
    if max(widths) - min(widths) > tolerance or max(heights) - min(heights) > tolerance:
        return False
    xs = sorted({round(box[0], 6) for box in boxes})
    ys = sorted({round(box[1], 6) for box in boxes})
    if len(xs) != 2 or len(ys) != 2:
        return False
    gap_x, gap_y = xs[1] - xs[0] - widths[0], ys[1] - ys[0] - heights[0]
    if gap_x < -tolerance or abs(gap_x - gap_y) > 1e-6:
        return False
    if kerf_cm is not None and abs(gap_x - kerf_cm) > 1e-6:
        return False
    if any(x < xs[0] - tolerance or y < ys[0] - tolerance
           or x > xs[1] + widths[0] + tolerance or y > ys[1] + heights[0] + tolerance
           for x, y in points):
        return False
    return _contour_sits_in_void(points, rings, point_in_polygon) and _clears(points, rings, kerf_cm or 0)




def placement_permission_errors(
    plan: dict[str, Any],
    requested_pieces: list[dict[str, Any]],
    *,
    mirroring_allowed: bool,
) -> list[str]:
    """Reject a recorded quarter-turn or mirror the piece is not allowed to use.

    Every placed piece is checked, not only search candidates. The clipped-void
    outline is the one non-quarter exception and is not a quarter-turn unless a
    mirror flag is also stored.
    """

    from .placement_orientation import (
        PlacementOrientationError,
        assert_orientation_allowed,
        recorded_mirror,
        resolve_placement_orientation,
    )

    expected = {int(piece["id"]): piece for piece in requested_pieces}
    errors: list[str] = []
    for sheet in plan.get("sheets") or []:
        for placed in sheet.get("pieces") or []:
            try:
                piece_id = int(placed["id"])
            except (TypeError, ValueError):
                continue
            source = expected.get(piece_id)
            if source is None:
                continue
            if placed.get("placement_outline_cm") and not recorded_mirror(placed):
                if _void_rotation_matches_piece(placed, source, 1e-7, sheet.get("pieces") or [], expected, None):
                    continue
                errors.append(f"Piece {placed.get('label')} has invalid dimensions or rotation state.")
                continue
            try:
                assert_orientation_allowed(
                    resolve_placement_orientation(placed),
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
            if placed.get("placement_outline_cm"):
                if not _void_rotation_matches_piece(placed, source, tolerance, pieces, expected, required_kerf_cm):
                    errors.append(f"Piece {placed.get('label')} has invalid dimensions or rotation state.")
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
