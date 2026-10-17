"""Place eligible Regular doors inside Glass openings after the base pack.

The base MaxRects, Shelf, Guillotine, Skyline, and CP-SAT searches stay
unchanged. This pass runs once on the winning plan. It keeps that plan unless
the nested result is geometrically valid and strictly better on
``industrial_rank``. A tie, a Panel Saw job, or any failed check returns the
baseline object untouched.

Clearance uses the plan Kerf once: the usable opening is the finished hole
inset by that Kerf, and pieces inside it keep the same Kerf between each
other. This pass proves rectangle containment only. It does not schedule CNC
toolpaths or claim that the nested piece stays fixtured while the frame is cut.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from .catalog import MACHINE_TYPES as MACHINE_CATALOG
from .machining_overlay import machining_values
from .primitives import (
    make_placed_piece,
    num,
    orientations_for,
    rect_intersects,
    rects_have_clearance,
)

GLASS_HOST_PIECE_ID = "glass_host_piece_id"
_PANEL_SAW_ID = next(
    machine.id for machine in MACHINE_CATALOG if machine.id == "Panel Saw"
)
_GEOMETRY_TOLERANCE_CM = 1e-7
_REPACK_METHOD = "MaxRects Best Short Side"


def nesting_time_budget_sec(time_limit_sec: float) -> float:
    """Bound the post-pass to a slice of the caller's existing time limit."""

    limit = max(0.0, float(time_limit_sec or 0))
    if limit <= 0:
        return 0.0
    return min(limit, max(0.25, limit * 0.25))


def nested_plan_is_better(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> bool:
    """True only when the candidate rank is strictly better than the baseline."""

    candidate_rank = tuple(candidate.get("industrial_rank") or ())
    baseline_rank = tuple(baseline.get("industrial_rank") or ())
    if not candidate_rank or not baseline_rank:
        return False
    if len(candidate_rank) != len(baseline_rank):
        return False
    return candidate_rank < baseline_rank


def opening_board_rect(placed: Mapping[str, Any]) -> dict[str, float] | None:
    """Finished Glass hole in usable-sheet centimetres.

    ``glass_hole_local_mm`` is already in the placed rectangle, including the
    one 90° mapping ``record_glass_opening`` applied. Sheet Y grows downward
    from the top of the usable area, matching the stored piece origin.
    """

    if str(placed.get("piece_type") or "") != "Glass":
        return None
    ring = placed.get("glass_hole_local_mm")
    if not isinstance(ring, (list, tuple)) or len(ring) < 4:
        return None
    points: list[tuple[float, float]] = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        points.append((float(point[0]), float(point[1])))
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    if max_x - min_x <= 0.05 or max_y - min_y <= 0.05:
        return None
    for x_mm, y_mm in points:
        on_vertical = abs(x_mm - min_x) <= 0.05 or abs(x_mm - max_x) <= 0.05
        on_horizontal = abs(y_mm - min_y) <= 0.05 or abs(y_mm - max_y) <= 0.05
        if not on_vertical or not on_horizontal:
            return None
    rect = {
        "x": num(placed.get("x")) + (min_x / 10.0),
        "y": num(placed.get("y")) + (min_y / 10.0),
        "w": (max_x - min_x) / 10.0,
        "h": (max_y - min_y) / 10.0,
    }
    host = _rect(placed)
    if not _strictly_inside(rect, host, _GEOMETRY_TOLERANCE_CM):
        return None
    return rect


def guest_is_eligible(piece: Mapping[str, Any]) -> bool:
    """Regular cut rectangles only. Machining and non-rectangular cuts stay out."""

    if str(piece.get("piece_type") or "Regular") != "Regular":
        return False
    if str(piece.get("clipped_corner_position") or "").strip():
        return False
    if str(piece.get("special_shape_geometry_json") or "").strip():
        return False
    if piece.get("edge_break") or piece.get("edge_break_only"):
        return False
    for spec in machining_values(piece).values():
        if spec["enabled"] or str(spec["side"] or "").strip() or spec["width_cm"] > 0:
            return False
    return True


def classify_piece_pair(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    kerf_cm: float,
    tolerance: float = _GEOMETRY_TOLERANCE_CM,
) -> str:
    """Classify one pair as ``nested``, ``invalid``, or ``separate``.

    ``separate`` leaves the caller on the ordinary rectangle rules. A proven
    nest is a Regular piece whose declared host is the Glass piece and whose
    cut rectangle lies inside that hole by at least one Kerf.
    """

    first_hosts = _declared_host_id(second) == _piece_id(first)
    second_hosts = _declared_host_id(first) == _piece_id(second)
    if first_hosts and second_hosts:
        return "invalid"
    if first_hosts:
        return "nested" if _proven_nest(second, first, kerf_cm, tolerance) else "invalid"
    if second_hosts:
        return "nested" if _proven_nest(first, second, kerf_cm, tolerance) else "invalid"
    return "separate"


def host_link_errors(
    placed_pieces: list[Mapping[str, Any]],
) -> list[str]:
    """Reject missing, circular, or cross-sheet host links."""

    by_id: dict[int, Mapping[str, Any]] = {}
    sheet_of: dict[int, Any] = {}
    errors: list[str] = []
    for placed in placed_pieces:
        piece_id = _piece_id(placed)
        if piece_id is None:
            continue
        by_id[piece_id] = placed
        sheet_of[piece_id] = placed.get("_sheet_no")

    for placed in placed_pieces:
        piece_id = _piece_id(placed)
        host_id = _declared_host_id(placed)
        if piece_id is None or host_id is None:
            continue
        label = placed.get("label")
        if host_id == piece_id or host_id not in by_id:
            errors.append(
                f"Piece {label} declares a Glass host that is not in the plan."
            )
            continue
        if sheet_of.get(host_id) != placed.get("_sheet_no"):
            errors.append(
                f"Piece {label} declares a Glass host on a different sheet."
            )
        seen = {piece_id}
        cursor = host_id
        while cursor is not None:
            if cursor in seen:
                errors.append(
                    f"Piece {label} is part of a circular Glass host relation."
                )
                break
            seen.add(cursor)
            cursor = _declared_host_id(by_id[cursor]) if cursor in by_id else None
    return errors


def nest_glass_openings(
    baseline: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    time_limit_sec: float,
    min_remnant_width_cm: float,
    min_remnant_length_cm: float,
    min_remnant_area_m2: float,
) -> dict[str, Any]:
    """Return a strictly better nested plan, or the original baseline."""

    if machine_type == _PANEL_SAW_ID:
        return baseline
    budget = nesting_time_budget_sec(time_limit_sec)
    if budget <= 0 or not baseline.get("industrial_rank"):
        return baseline
    started = time.monotonic()
    openings = _openings(baseline, kerf_cm)
    if not openings:
        return baseline
    selected = _select_guests(pieces, openings, kerf_cm)
    if not selected:
        return baseline
    if time.monotonic() - started > budget:
        return baseline

    from .evaluation import validate_plan
    from .optimizer import enrich_plan_metrics
    from .registry import METHOD_CONFIGS, run_single_method

    selected_ids = {int(piece["id"]) for piece in selected}
    remainder = [piece for piece in pieces if int(piece["id"]) not in selected_ids]
    method_key = str(baseline.get("method_key") or "")
    if method_key not in METHOD_CONFIGS:
        method_key = _REPACK_METHOD
    repacked = run_single_method(
        remainder,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        method_key,
    )
    if time.monotonic() - started > budget or repacked.get("unplaced"):
        return baseline
    placed = _place_guests(repacked, selected, kerf_cm)
    if placed is None:
        return baseline
    candidate = placed
    for key in (
        "optimization_mode",
        "ordering_strategy",
        "attempts",
        "search_elapsed_sec",
        "search_time_limit_sec",
        "solver_status",
        "solver_wall_time_sec",
        "method_key",
        "method_label",
        "complexity",
    ):
        if key in baseline:
            candidate[key] = baseline[key]
    used_area = sum(num(piece.get("area_m2")) for piece in pieces)
    board_area = len(candidate.get("sheets") or []) * (board_w_cm * board_h_cm / 10000)
    candidate["used_area_m2"] = used_area
    candidate["total_board_area_m2"] = board_area
    candidate["waste_area_m2"] = max(0.0, board_area - used_area)
    candidate = enrich_plan_metrics(
        candidate,
        str(candidate.get("method_key") or method_key),
        machine_type,
        min_remnant_width_cm=min_remnant_width_cm,
        min_remnant_length_cm=min_remnant_length_cm,
        min_remnant_area_m2=min_remnant_area_m2,
    )
    errors = validate_plan(
        candidate,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm=kerf_cm,
    )
    if errors or not nested_plan_is_better(candidate, baseline):
        return baseline
    return candidate


def _openings(plan: Mapping[str, Any], kerf_cm: float) -> list[dict[str, Any]]:
    openings: list[dict[str, Any]] = []
    for sheet in plan.get("sheets") or []:
        for placed in sheet.get("pieces") or []:
            hole = opening_board_rect(placed)
            if hole is None:
                continue
            usable = _inset(hole, _edge_gap(kerf_cm))
            if usable["w"] <= _GEOMETRY_TOLERANCE_CM or usable["h"] <= _GEOMETRY_TOLERANCE_CM:
                continue
            openings.append(
                {
                    "host_id": int(placed["id"]),
                    "sheet_no": sheet.get("sheet_no"),
                    "usable": usable,
                }
            )
    openings.sort(
        key=lambda opening: (
            -(opening["usable"]["w"] * opening["usable"]["h"]),
            opening["host_id"],
        )
    )
    return openings


def _select_guests(
    pieces: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    kerf_cm: float,
) -> list[dict[str, Any]]:
    eligible = [piece for piece in pieces if guest_is_eligible(piece)]
    eligible.sort(
        key=lambda piece: (
            -(num(piece.get("width_cm")) * num(piece.get("length_cm"))),
            int(piece["id"]),
        )
    )
    occupancy: dict[int, list[dict[str, float]]] = {
        opening["host_id"]: [] for opening in openings
    }
    selected: list[dict[str, Any]] = []
    for guest in eligible:
        for opening in openings:
            local = _place_in_usable(
                guest,
                opening["usable"],
                occupancy[opening["host_id"]],
                kerf_cm,
            )
            if local is None:
                continue
            occupancy[opening["host_id"]].append(local)
            selected.append(guest)
            break
    return selected


def _place_guests(
    plan: dict[str, Any],
    guests: list[dict[str, Any]],
    kerf_cm: float,
) -> dict[str, Any] | None:
    openings = _openings(plan, kerf_cm)
    if not openings:
        return None
    sheets = {
        sheet.get("sheet_no"): sheet for sheet in plan.get("sheets") or []
    }
    hosts = {
        opening["host_id"]: opening for opening in openings
    }
    occupancy: dict[int, list[dict[str, float]]] = {
        opening["host_id"]: [] for opening in openings
    }
    ordered = sorted(
        guests,
        key=lambda piece: (
            -(num(piece.get("width_cm")) * num(piece.get("length_cm"))),
            int(piece["id"]),
        ),
    )
    for guest in ordered:
        placed_into = None
        for opening in openings:
            local = _place_in_usable(
                guest,
                opening["usable"],
                occupancy[opening["host_id"]],
                kerf_cm,
            )
            if local is None:
                continue
            occupancy[opening["host_id"]].append(local)
            placed_into = (opening, local)
            break
        if placed_into is None:
            return None
        opening, local = placed_into
        if opening["host_id"] not in hosts:
            return None
        sheet = sheets.get(opening["sheet_no"])
        if sheet is None:
            return None
        placed = make_placed_piece(
            guest,
            opening["usable"]["x"] + local["x"],
            opening["usable"]["y"] + local["y"],
            local["w"],
            local["h"],
            bool(local["rotated"]),
        )
        placed[GLASS_HOST_PIECE_ID] = opening["host_id"]
        sheet.setdefault("pieces", []).append(placed)
    plan["unplaced"] = []
    return plan


def _place_in_usable(
    guest: Mapping[str, Any],
    usable: Mapping[str, float],
    occupied: list[dict[str, float]],
    kerf_cm: float,
) -> dict[str, float] | None:
    gap = max(0.0, num(kerf_cm))
    tolerance = _GEOMETRY_TOLERANCE_CM
    for orientation in orientations_for(dict(guest)):
        for x_pos, y_pos in _candidate_positions(occupied, gap):
            rect = {
                "x": x_pos,
                "y": y_pos,
                "w": num(orientation["w"]),
                "h": num(orientation["h"]),
                "rotated": bool(orientation["rotated"]),
            }
            if (
                rect["x"] < -tolerance
                or rect["y"] < -tolerance
                or rect["x"] + rect["w"] > num(usable["w"]) + tolerance
                or rect["y"] + rect["h"] > num(usable["h"]) + tolerance
            ):
                continue
            if any(rect_intersects(rect, other) for other in occupied):
                continue
            if any(
                not rects_have_clearance(rect, other, gap, tolerance)
                for other in occupied
            ):
                continue
            return rect
    return None


def _candidate_positions(
    occupied: list[dict[str, float]],
    gap: float,
) -> list[tuple[float, float]]:
    positions = [(0.0, 0.0)]
    for rect in occupied:
        positions.append((num(rect["x"]) + num(rect["w"]) + gap, num(rect["y"])))
        positions.append((num(rect["x"]), num(rect["y"]) + num(rect["h"]) + gap))
        positions.append((num(rect["x"]) + num(rect["w"]) + gap, 0.0))
        positions.append((0.0, num(rect["y"]) + num(rect["h"]) + gap))
    unique = {(round(x_pos, 6), round(y_pos, 6)) for x_pos, y_pos in positions}
    return sorted(unique)


def _proven_nest(
    guest: Mapping[str, Any],
    host: Mapping[str, Any],
    kerf_cm: float,
    tolerance: float,
) -> bool:
    if not guest_is_eligible(guest):
        return False
    if str(host.get("piece_type") or "") != "Glass":
        return False
    hole = opening_board_rect(host)
    if hole is None:
        return False
    usable = _inset(hole, _edge_gap(kerf_cm))
    return _inside_rect(_rect(guest), usable, tolerance)


def _declared_host_id(piece: Mapping[str, Any]) -> int | None:
    value = piece.get(GLASS_HOST_PIECE_ID)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _piece_id(piece: Mapping[str, Any]) -> int | None:
    try:
        return int(piece["id"])
    except (KeyError, TypeError, ValueError):
        return None


def _rect(piece: Mapping[str, Any]) -> dict[str, float]:
    return {
        "x": num(piece.get("x")),
        "y": num(piece.get("y")),
        "w": num(piece.get("w")),
        "h": num(piece.get("h")),
    }


def _inset(rect: Mapping[str, float], gap: float) -> dict[str, float]:
    return {
        "x": num(rect["x"]) + gap,
        "y": num(rect["y"]) + gap,
        "w": num(rect["w"]) - (2.0 * gap),
        "h": num(rect["h"]) - (2.0 * gap),
    }


def _edge_gap(kerf_cm: float) -> float:
    gap = max(0.0, num(kerf_cm))
    if gap <= _GEOMETRY_TOLERANCE_CM:
        return _GEOMETRY_TOLERANCE_CM * 2.0
    return gap


def _inside_rect(
    inner: Mapping[str, float],
    outer: Mapping[str, float],
    tolerance: float,
) -> bool:
    return (
        num(inner["x"]) >= num(outer["x"]) - tolerance
        and num(inner["y"]) >= num(outer["y"]) - tolerance
        and num(inner["x"]) + num(inner["w"]) <= num(outer["x"]) + num(outer["w"]) + tolerance
        and num(inner["y"]) + num(inner["h"]) <= num(outer["y"]) + num(outer["h"]) + tolerance
    )


def _strictly_inside(
    inner: Mapping[str, float],
    outer: Mapping[str, float],
    tolerance: float,
) -> bool:
    return (
        num(inner["x"]) > num(outer["x"]) + tolerance
        and num(inner["y"]) > num(outer["y"]) + tolerance
        and num(inner["x"]) + num(inner["w"]) < num(outer["x"]) + num(outer["w"]) - tolerance
        and num(inner["y"]) + num(inner["h"]) < num(outer["y"]) + num(outer["h"]) - tolerance
    )
