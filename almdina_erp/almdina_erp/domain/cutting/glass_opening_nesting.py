"""Place proven cut outlines inside Glass openings after the base pack.

The base MaxRects, Shelf, Guillotine, Skyline, and CP-SAT searches stay
unchanged. This pass runs once on the winning plan. A nest is accepted when
the guest outlines sit inside the real openings with kerf and without overlap.
Board count, remnant area, and ``industrial_rank`` do not reject that nest.
Between two valid nests, more guests win, then a larger guest area, then rank.

Guests are moved into the openings of the current layout first. Repacking the
other pieces is optional: it can replace the direct nest when it is also valid
and better, and its failure leaves the direct nest in place.

Clearance uses the plan Kerf once: the usable opening is the finished hole
inset by that Kerf, and pieces inside it keep the same Kerf between each
other. Final acceptance uses the real cut outline. A Glass guest may host one
further piece, and no host chain may go deeper than that.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any, Mapping, Sequence

from .catalog import MACHINE_TYPES as MACHINE_CATALOG
from .dxf_geometry import polygon_distance, validate_polygon
from .dxf_topology import (
    PartGeometry,
    containing_hole,
    material_footprints_overlap,
    polygon_strictly_contains_polygon,
)
from .glass_opening_dxf import GlassOpeningError, placed_glass_hole_mm
from .primitives import (
    make_placed_piece,
    num,
    orientations_for,
    rect_intersects,
    rects_have_clearance,
)

GLASS_HOST_PIECE_ID = "glass_host_piece_id"
# Board glass, a glass inside it, then one more piece. No fourth level.
MAX_NESTING_DEPTH = 2
_PANEL_SAW_ID = next(
    machine.id for machine in MACHINE_CATALOG if machine.id == "Panel Saw"
)
_GEOMETRY_TOLERANCE_CM = 1e-7
_SPECIAL_EPSILON_CM = 0.001
_MAX_SPECIAL_VERTICES = 64
_CORNER_TYPES = frozenset({"Clipped Corner", "L-Shaped Corner"})
_ROTATED_CORNER = {
    "Top Left": "Top Right",
    "Top Right": "Bottom Right",
    "Bottom Right": "Bottom Left",
    "Bottom Left": "Top Left",
}
_REPACK_METHOD = "MaxRects Best Short Side"


def nesting_time_budget_sec(time_limit_sec: float) -> float:
    """Bound the post-pass to a slice of the caller's existing time limit."""

    limit = max(0.0, float(time_limit_sec or 0))
    if limit <= 0:
        return 0.0
    return min(limit, max(0.25, limit * 0.25))


def nested_piece_count(plan: Mapping[str, Any]) -> int:
    """Unique pieces whose placement declares one Glass host."""

    seen: set[int] = set()
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            if piece.get(GLASS_HOST_PIECE_ID) in (None, ""):
                continue
            piece_id = _piece_id(piece)
            if piece_id is not None:
                seen.add(piece_id)
    return len(seen)


def nested_guest_area(plan: Mapping[str, Any]) -> float:
    """Cut area of unique pieces sitting in a Glass opening."""

    seen: set[int] = set()
    area = 0.0
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            if piece.get(GLASS_HOST_PIECE_ID) in (None, ""):
                continue
            piece_id = _piece_id(piece)
            if piece_id is None or piece_id in seen:
                continue
            seen.add(piece_id)
            width = num(piece.get("w"))
            height = num(piece.get("h"))
            area += width * height if width > 0 and height > 0 else num(piece.get("area_m2")) * 10000
    return area


def nested_plan_is_better(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> bool:
    """Choose between two already valid nests.

    More guests win, then a larger guest area. Industrial rank is only the
    tie-break. It never decides whether a valid nest may replace a plan that
    has not used the opening.
    """

    candidate_count = nested_piece_count(candidate)
    baseline_count = nested_piece_count(baseline)
    if candidate_count != baseline_count:
        return candidate_count > baseline_count
    candidate_area = nested_guest_area(candidate)
    baseline_area = nested_guest_area(baseline)
    if abs(candidate_area - baseline_area) > 1e-6:
        return candidate_area > baseline_area
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
    """Any order piece whose real cut outline can be proven.

    Banding and machining stay on the piece and move with it. A Special door
    without an exact manufacturing polygon is not eligible. A Glass door is
    eligible only when its own opening can be produced.
    """

    return material_outline_cm(_as_placed_source(piece)) is not None


def classify_piece_pair(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    kerf_cm: float,
    tolerance: float = _GEOMETRY_TOLERANCE_CM,
    sheet_pieces: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Classify one pair as ``nested``, ``invalid``, or ``separate``.

    ``separate`` leaves the caller on the ordinary rectangle rules. A proven
    nest puts the guest's real cut outline inside the host opening by at least
    one Kerf. A deeper piece is accepted against an outer Glass only when its
    host chain reaches that Glass.
    """

    first_hosts = _declared_host_id(second) == _piece_id(first)
    second_hosts = _declared_host_id(first) == _piece_id(second)
    if first_hosts and second_hosts:
        return "invalid"
    if first_hosts:
        return "nested" if _proven_nest(second, first, kerf_cm, tolerance) else "invalid"
    if second_hosts:
        return "nested" if _proven_nest(first, second, kerf_cm, tolerance) else "invalid"
    catalog = sheet_pieces if sheet_pieces is not None else (first, second)
    for guest, host in ((second, first), (first, second)):
        indirect = _indirect_relation(guest, host, kerf_cm, tolerance, catalog)
        if indirect is not None:
            return indirect
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
        depth = 0
        while cursor is not None:
            depth += 1
            if depth > MAX_NESTING_DEPTH:
                errors.append(
                    f"Piece {label} exceeds the Glass nesting depth."
                )
                break
            if cursor in seen:
                errors.append(
                    f"Piece {label} is part of a circular Glass host relation."
                )
                break
            seen.add(cursor)
            cursor = _declared_host_id(by_id[cursor]) if cursor in by_id else None
    return errors


def _without_guests(
    plan: Mapping[str, Any],
    guest_ids: set[int],
) -> dict[str, Any]:
    """Copy a layout with the selected guests removed from their old positions."""

    copied = deepcopy(plan)
    for sheet in copied.get("sheets") or []:
        sheet["pieces"] = [
            piece
            for piece in (sheet.get("pieces") or [])
            if _piece_id(piece) not in guest_ids
        ]
    copied["sheets"] = [
        sheet for sheet in (copied.get("sheets") or []) if sheet.get("pieces")
    ]
    copied["unplaced"] = [
        piece
        for piece in (copied.get("unplaced") or [])
        if _piece_id(piece) not in guest_ids
    ]
    return copied


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
    guest_exclusions: frozenset[int] = frozenset(),
    preserve_existing: bool = False,
) -> dict[str, Any]:
    """Compare a few complete, validated opening assignments in one budget."""
    from copy import deepcopy
    from .optimizer import _candidate_is_better

    if machine_type == _PANEL_SAW_ID or time_limit_sec <= 0:
        return _nest_glass_openings(baseline, pieces, board_w_cm, board_h_cm, kerf_cm,
            machine_type=machine_type, time_limit_sec=time_limit_sec,
            min_remnant_width_cm=min_remnant_width_cm, min_remnant_length_cm=min_remnant_length_cm,
            min_remnant_area_m2=min_remnant_area_m2)
    deadline = time.monotonic() + nesting_time_budget_sec(time_limit_sec)
    best = None
    variants = ({}, {"small_openings_first": True},
                {"small_openings_first": True, "guest_order": "width"})
    for index, assignment_options in enumerate(variants):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        candidate = _nest_glass_openings(deepcopy(baseline), pieces, board_w_cm, board_h_cm, kerf_cm,
            machine_type=machine_type, time_limit_sec=time_limit_sec,
            min_remnant_width_cm=min_remnant_width_cm, min_remnant_length_cm=min_remnant_length_cm,
            min_remnant_area_m2=min_remnant_area_m2, assignment_options={**assignment_options,
                "excluded_guest_ids": guest_exclusions, "preserve_existing": preserve_existing},
            deadline=time.monotonic() + remaining / (len(variants) - index))
        if best is None or _candidate_is_better(candidate, best):
            best = candidate
    return best if best is not None else baseline


def _nest_glass_openings(
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
    assignment_options: dict[str, Any] | None = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Return a better nested plan, or the original baseline."""

    def _finish(plan: dict[str, Any], **diagnostics: Any) -> dict[str, Any]:
        plan["glass_nesting_diagnostics"] = {
            "openings_found": int(diagnostics.get("openings_found") or 0),
            "guests_selected": list(diagnostics.get("guests_selected") or ()),
            "outcome": str(diagnostics.get("outcome") or "skipped"),
            "baseline_rank": tuple(baseline.get("industrial_rank") or ()),
            "candidate_rank": diagnostics.get("candidate_rank"),
            "baseline_nested_count": nested_piece_count(baseline),
            "candidate_nested_count": int(diagnostics.get("candidate_nested_count") or 0),
            "validation_error_count": int(diagnostics.get("validation_error_count") or 0),
        }
        return plan

    if machine_type == _PANEL_SAW_ID:
        return _finish(baseline, outcome="panel_saw")
    budget = nesting_time_budget_sec(time_limit_sec)
    assignment_options = assignment_options or {}
    if deadline is not None:
        budget = min(budget, max(0.0, deadline - time.monotonic()))
    if budget <= 0 or not baseline.get("industrial_rank"):
        return _finish(baseline, outcome="no_budget")
    started = time.monotonic()
    assignment_options = {**assignment_options, "deadline": started + budget}
    openings = _openings(baseline, kerf_cm, respect_existing=bool(assignment_options.get("preserve_existing")))
    if not openings:
        return _finish(baseline, outcome="no_openings", openings_found=0)
    assignments: list[dict[str, Any]] = []
    selected = _select_guests(pieces, openings, kerf_cm, assignment_records=assignments, **assignment_options)
    selected_ids = [int(piece["id"]) for piece in selected]
    if not selected:
        return _finish(
            baseline,
            outcome="no_guests",
            openings_found=len(openings),
        )
    if time.monotonic() - started > budget:
        return _finish(
            baseline,
            outcome="budget",
            openings_found=len(openings),
            guests_selected=selected_ids,
        )

    from .evaluation import VALIDATION_DEADLINE_EXCEEDED, validate_plan
    from .optimizer import enrich_plan_metrics
    from .registry import METHOD_CONFIGS, run_single_method

    selected_id_set = set(selected_ids)
    method_key = str(baseline.get("method_key") or "")
    if method_key not in METHOD_CONFIGS:
        method_key = _REPACK_METHOD
    context = {
        "openings_found": len(openings),
        "guests_selected": selected_ids,
    }

    def _expired(plan: dict[str, Any] | None) -> dict[str, Any] | None:
        if time.monotonic() - started <= budget:
            return None
        if plan is not None:
            return _finish(
                plan,
                outcome="accepted",
                candidate_rank=tuple(plan.get("industrial_rank") or ()),
                candidate_nested_count=nested_piece_count(plan),
                **context,
            )
        return _finish(baseline, outcome="budget", **context)

    def _prepare(placed: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
        if placed is None:
            return None, "place_failed"
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
        board_area = len(candidate.get("sheets") or []) * (
            board_w_cm * board_h_cm / 10000
        )
        candidate["used_area_m2"] = used_area
        candidate["total_board_area_m2"] = board_area
        candidate["waste_area_m2"] = max(0.0, board_area - used_area)
        expired = _expired(None)
        if expired is not None:
            return None, "budget"
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
            deadline_monotonic=started + budget,
        )
        if errors == [VALIDATION_DEADLINE_EXCEEDED]:
            return None, "budget"
        if errors:
            return candidate, "rejected_validation"
        return candidate, "accepted"

    direct_source = _without_guests(baseline, selected_id_set)
    try:
        direct_placed = _place_guests(direct_source, selected, kerf_cm, assignments=assignments, **assignment_options)
    except GlassOpeningError:
        direct_placed = None
    accepted, failure = _prepare(direct_placed)
    if failure == "budget" and accepted is None:
        return _finish(baseline, outcome="budget", **context)
    if accepted is not None and failure != "accepted":
        accepted = None

    expired = _expired(accepted if failure == "accepted" else None)
    if expired is not None:
        return expired
    if assignment_options.get("preserve_existing"):
        # Joint exploration already owns rigid groups. Repacking source pieces
        # here would silently discard those proven shape/host assignments.
        return _finish(accepted if accepted is not None else baseline,
            outcome="accepted" if accepted is not None else failure,
            candidate_rank=tuple(accepted.get("industrial_rank") or ()) if accepted else None,
            candidate_nested_count=nested_piece_count(accepted) if accepted else nested_piece_count(baseline),
            **context)

    remainder = [piece for piece in pieces if int(piece["id"]) not in selected_id_set]
    repack_plan: dict[str, Any] | None = None
    repacked = run_single_method(
        remainder,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        method_key,
    )
    expired = _expired(accepted)
    if expired is not None:
        return expired
    repack_failure = failure if failure != "accepted" else "repack_unplaced"
    if not repacked.get("unplaced"):
        try:
            repack_placed = _place_guests(repacked, selected, kerf_cm, **assignment_options)
        except GlassOpeningError:
            repack_placed = None
        repack_plan, repack_failure = _prepare(repack_placed)
        if repack_failure == "budget":
            expired = _expired(accepted)
            if expired is not None:
                return expired
            return _finish(baseline, outcome="budget", **context)
        if repack_failure == "accepted" and (
            accepted is None or nested_plan_is_better(repack_plan, accepted)
        ):
            accepted = repack_plan

    if accepted is None:
        return _finish(
            baseline,
            outcome=repack_failure if repack_failure != "accepted" else failure,
            candidate_rank=tuple((repack_plan or {}).get("industrial_rank") or ())
            if repack_failure == "rejected_validation"
            else None,
            candidate_nested_count=nested_piece_count(repack_plan)
            if repack_failure == "rejected_validation" and repack_plan is not None
            else 0,
            validation_error_count=1 if repack_failure == "rejected_validation" else 0,
            **context,
        )
    return _finish(
        accepted,
        outcome="accepted",
        candidate_rank=tuple(accepted.get("industrial_rank") or ()),
        candidate_nested_count=nested_piece_count(accepted),
        **context,
    )


def _openings(plan: Mapping[str, Any], kerf_cm: float, *, respect_existing: bool = False) -> list[dict[str, Any]]:
    openings: list[dict[str, Any]] = []
    for sheet in plan.get("sheets") or []:
        for placed in sheet.get("pieces") or []:
            hole = opening_board_rect(placed)
            if hole is None:
                continue
            usable = _inset(hole, _edge_gap(kerf_cm))
            if usable["w"] <= _GEOMETRY_TOLERANCE_CM or usable["h"] <= _GEOMETRY_TOLERANCE_CM:
                continue
            sheet_pieces = sheet.get("pieces") or []
            occupied = [{"x": num(p.get("x"))-usable["x"], "y": num(p.get("y"))-usable["y"],
                         "w": num(p.get("w")), "h": num(p.get("h"))}
                        for p in sheet_pieces if _declared_host_id(p) == _piece_id(placed)] if respect_existing else []
            openings.append(
                {
                    "host_id": int(placed["id"]),
                    "sheet_no": sheet.get("sheet_no"),
                    "usable": usable,
                    "depth": _nesting_depth(placed, sheet_pieces) if respect_existing else 0,
                    "occupied": occupied,
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
    assignment_records: list[dict[str, Any]] | None = None,
    **assignment_options: Any,
) -> list[dict[str, Any]]:
    eligible = [piece for piece in pieces if guest_is_eligible(piece)]
    assignments = _assign_into_openings(eligible, openings, kerf_cm, **assignment_options)
    if assignment_records is not None:
        assignment_records.extend(assignments)
    return [assignment["guest"] for assignment in assignments]


def _place_guests(
    plan: dict[str, Any],
    guests: list[dict[str, Any]],
    kerf_cm: float,
    assignments: list[dict[str, Any]] | None = None,
    **assignment_options: Any,
) -> dict[str, Any] | None:
    openings = _openings(plan, kerf_cm, respect_existing=bool(assignment_options.get("preserve_existing")))
    if not openings:
        return None
    if assignments is None:
        assignments = _assign_into_openings(guests, openings, kerf_cm, **assignment_options)
    if len(assignments) != len(guests):
        return None
    for assignment in assignments:
        opening = assignment["opening"]
        local = assignment["local"]
        # Keep the proven guest→host choice. A nested Glass host may itself
        # have moved; resolve its live opening instead of re-running First Fit.
        found = next(((sheet, host) for sheet in plan.get("sheets") or []
                      for host in sheet.get("pieces") or [] if _piece_id(host) == opening["host_id"]), None)
        if found is None:
            return None
        sheet, host = found
        hole = opening_board_rect(host)
        if hole is None:
            return None
        usable = _inset(hole, _edge_gap(kerf_cm))
        placed = make_placed_piece(
            assignment["guest"],
            usable["x"] + local["x"],
            usable["y"] + local["y"],
            local["w"],
            local["h"],
            bool(local["rotated"]),
        )
        placed[GLASS_HOST_PIECE_ID] = opening["host_id"]
        sheet.setdefault("pieces", []).append(placed)
    plan["unplaced"] = []
    return plan


def _assign_into_openings(
    guests: list[dict[str, Any]],
    openings: list[dict[str, Any]],
    kerf_cm: float,
    *,
    small_openings_first: bool = False,
    guest_order: str = "area",
    deadline: float | None = None,
    excluded_guest_ids: frozenset[int] = frozenset(),
    preserve_existing: bool = False,
) -> list[dict[str, Any]]:
    """Greedy largest-first placement. A nested Glass publishes its opening."""

    working = [dict(opening, depth=int(opening.get("depth") or 0)) for opening in openings]
    if small_openings_first:
        working.sort(key=lambda opening: (opening["usable"]["w"] * opening["usable"]["h"], opening["host_id"]))
    occupancy: dict[int, list[dict[str, float]]] = {
        opening["host_id"]: list(opening.get("occupied") or []) if preserve_existing else [] for opening in working
    }
    ordered = sorted(
        guests,
        key=lambda piece: (
            -max(num(piece.get("width_cm")), num(piece.get("length_cm"))) if guest_order == "width"
            else -(num(piece.get("width_cm")) * num(piece.get("length_cm"))),
            int(piece["id"]),
        ),
    )
    assignments: list[dict[str, Any]] = []
    for guest in ordered:
        if _piece_id(guest) in excluded_guest_ids:
            continue
        if deadline is not None and time.monotonic() >= deadline:
            break
        placed_into = None
        for opening in working:
            if int(opening["depth"]) + 1 > MAX_NESTING_DEPTH:
                continue
            if _piece_id(guest) in _host_chain(opening["host_id"], working):
                continue
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
            continue
        opening, local = placed_into
        assignments.append({"guest": guest, "opening": opening, "local": local})
        _publish_nested_opening(guest, opening, local, working, occupancy, kerf_cm)
    return assignments


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
    if str(host.get("piece_type") or "") != "Glass":
        return False
    return _outline_in_hole(guest, host, kerf_cm, tolerance)


def _indirect_relation(
    guest: Mapping[str, Any],
    host: Mapping[str, Any],
    kerf_cm: float,
    tolerance: float,
    pieces: Sequence[Mapping[str, Any]],
) -> str | None:
    host_id = _piece_id(host)
    if host_id is None or str(host.get("piece_type") or "") != "Glass":
        return None
    if _declared_host_id(guest) in (None, host_id):
        return None
    inside = _outline_in_hole(guest, host, kerf_cm, tolerance)
    if not inside:
        return None
    if not _chain_reaches(guest, host_id, pieces):
        return "invalid"
    if _nesting_depth(guest, pieces) > MAX_NESTING_DEPTH:
        return "invalid"
    return "nested"


def _outline_in_hole(
    guest: Mapping[str, Any],
    host: Mapping[str, Any],
    kerf_cm: float,
    tolerance: float,
) -> bool:
    outer = material_outline_cm(guest)
    hole = _hole_polygon(host)
    if outer is None or hole is None:
        return False
    if not polygon_strictly_contains_polygon(hole, outer):
        return False
    return polygon_distance(hole, outer) + tolerance >= _edge_gap(kerf_cm)


def material_pair_issue(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    kerf_cm: float,
    tolerance: float,
) -> str | None:
    """Compare real cut material for two pieces that participate in a nest."""

    first_part = _part_geometry(first)
    second_part = _part_geometry(second)
    if first_part is None or second_part is None:
        return "unproven"
    if material_footprints_overlap(first_part, second_part):
        return "overlap"
    hole = containing_hole(first_part, second_part.outer)
    other = second_part.outer
    if hole is None:
        hole = containing_hole(second_part, first_part.outer)
        other = first_part.outer
    gap = _edge_gap(kerf_cm)
    if hole is not None:
        if polygon_distance(hole, other) + tolerance < gap:
            return "kerf"
        return None
    if polygon_distance(first_part.outer, second_part.outer) + tolerance < gap:
        return "kerf"
    return None


def undeclared_opening_containment(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    tolerance: float = _GEOMETRY_TOLERANCE_CM,
) -> bool:
    """True when one outline sits in the other's Glass hole without a host link."""

    if _declared_host_id(first) is not None or _declared_host_id(second) is not None:
        return False
    first_part = _part_geometry(first)
    second_part = _part_geometry(second)
    if first_part is None or second_part is None:
        return False
    if containing_hole(first_part, second_part.outer, tolerance=tolerance) is not None:
        return True
    if containing_hole(second_part, first_part.outer, tolerance=tolerance) is not None:
        return True
    return False


def layout_pair_fault(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    kerf_cm: float,
    tolerance: float = _GEOMETRY_TOLERANCE_CM,
    sheet_pieces: Sequence[Mapping[str, Any]] | None = None,
    first_rect: Mapping[str, float] | None = None,
    second_rect: Mapping[str, float] | None = None,
) -> str | None:
    """Shared layout fault for optimizer validation and DXF export.

    Returns ``None`` when the pair is clear, otherwise ``overlap``, ``kerf``, or
    ``invalid``. Proven Glass nests are accepted only after real-outline checks.
    Bounding boxes are the fallback when either outline is unproven.
    """

    relation = classify_piece_pair(
        first,
        second,
        kerf_cm=kerf_cm,
        tolerance=tolerance,
        sheet_pieces=sheet_pieces,
    )
    if relation == "nested":
        return None
    if relation == "invalid":
        return "invalid"
    hosted = _declared_host_id(first) is not None or _declared_host_id(second) is not None
    if hosted or (
        material_outline_cm(first) is not None and material_outline_cm(second) is not None
    ):
        if not hosted and undeclared_opening_containment(
            first, second, tolerance=tolerance
        ):
            return "overlap"
        issue = material_pair_issue(
            first,
            second,
            kerf_cm=kerf_cm,
            tolerance=tolerance,
        )
        if issue is None:
            return None
        return issue
    rect_a = first_rect or _rect(first)
    rect_b = second_rect or _rect(second)
    if rect_intersects(rect_a, rect_b):
        return "overlap"
    gap = max(0.0, num(kerf_cm))
    if gap and not rects_have_clearance(rect_a, rect_b, gap, tolerance):
        return "kerf"
    return None


def material_outline_cm(piece: Mapping[str, Any]) -> tuple[tuple[float, float], ...] | None:
    """Board-centimetre cut outline. ``None`` means the shape is not proven."""

    stored = piece.get("placement_outline_cm")
    if isinstance(stored, (list, tuple)) and len(stored) >= 3:
        points: list[tuple[float, float]] = []
        for point in stored:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            points.append((float(point[0]), float(point[1])))
        return tuple(points)
    placed = _as_placed_source(piece)
    kind = str(placed.get("piece_type") or "Regular")
    if kind in _CORNER_TYPES:
        return _corner_outline(placed)
    if kind == "Special":
        return _special_outline(placed)
    if kind == "Glass":
        if _glass_ring(placed) is None:
            return None
        return _rectangle_outline(placed)
    if kind == "Regular":
        return _rectangle_outline(placed)
    return None


def _publish_nested_opening(
    guest: Mapping[str, Any],
    parent: Mapping[str, Any],
    local: Mapping[str, float],
    openings: list[dict[str, Any]],
    occupancy: dict[int, list[dict[str, float]]],
    kerf_cm: float,
) -> None:
    parent_depth = int(parent.get("depth") or 0)
    if str(guest.get("piece_type") or "") != "Glass":
        return
    if parent_depth + 1 >= MAX_NESTING_DEPTH:
        return
    guest_id = _piece_id(guest)
    if guest_id is None or guest_id in occupancy:
        return
    probe = dict(guest)
    probe["x"] = num(parent["usable"]["x"]) + num(local["x"])
    probe["y"] = num(parent["usable"]["y"]) + num(local["y"])
    probe["w"] = num(local["w"])
    probe["h"] = num(local["h"])
    probe["rotated"] = bool(local["rotated"])
    ring = placed_glass_hole_mm(probe, rotated=bool(local["rotated"]))
    if not ring:
        return
    probe["glass_hole_local_mm"] = ring
    hole = opening_board_rect(probe)
    if hole is None:
        return
    usable = _inset(hole, _edge_gap(kerf_cm))
    if usable["w"] <= _GEOMETRY_TOLERANCE_CM or usable["h"] <= _GEOMETRY_TOLERANCE_CM:
        return
    openings.append(
        {
            "host_id": guest_id,
            "sheet_no": parent.get("sheet_no"),
            "usable": usable,
            "depth": parent_depth + 1,
            "host_chain": (*_host_chain(parent["host_id"], openings), guest_id),
        }
    )
    occupancy[guest_id] = []


def _host_chain(host_id: int, openings: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
    for opening in openings:
        if opening.get("host_id") == host_id:
            chain = opening.get("host_chain")
            if chain:
                return tuple(chain)
            return (host_id,)
    return (host_id,)


def _chain_reaches(
    guest: Mapping[str, Any],
    host_id: int,
    pieces: Sequence[Mapping[str, Any]],
) -> bool:
    by_id = {
        piece_id: piece
        for piece in pieces
        if (piece_id := _piece_id(piece)) is not None
    }
    cursor = _declared_host_id(guest)
    seen = {_piece_id(guest)}
    steps = 0
    while cursor is not None:
        steps += 1
        if steps > MAX_NESTING_DEPTH or cursor in seen or cursor not in by_id:
            return False
        if cursor == host_id:
            return True
        seen.add(cursor)
        cursor = _declared_host_id(by_id[cursor])
    return False


def _nesting_depth(
    guest: Mapping[str, Any],
    pieces: Sequence[Mapping[str, Any]],
) -> int:
    by_id = {
        piece_id: piece
        for piece in pieces
        if (piece_id := _piece_id(piece)) is not None
    }
    depth = 0
    cursor = _declared_host_id(guest)
    seen: set[int] = set()
    while cursor is not None:
        if cursor in seen or cursor not in by_id:
            return MAX_NESTING_DEPTH + 1
        seen.add(cursor)
        depth += 1
        cursor = _declared_host_id(by_id[cursor])
    return depth


def _part_geometry(piece: Mapping[str, Any]) -> PartGeometry | None:
    outer = material_outline_cm(piece)
    if outer is None:
        return None
    return PartGeometry(outer=outer, holes=_glass_holes(piece))


def _as_placed_source(piece: Mapping[str, Any]) -> dict[str, Any]:
    placed = dict(piece)
    if num(placed.get("w")) > 0 and num(placed.get("h")) > 0:
        return placed
    placed["x"] = 0.0
    placed["y"] = 0.0
    placed["w"] = num(placed.get("width_cm"))
    placed["h"] = num(placed.get("length_cm"))
    placed["rotated"] = False
    return placed


def _rectangle_outline(
    placed: Mapping[str, Any],
) -> tuple[tuple[float, float], ...] | None:
    width = num(placed.get("w"))
    height = num(placed.get("h"))
    if width <= 0 or height <= 0:
        return None
    x_pos = num(placed.get("x"))
    y_pos = num(placed.get("y"))
    return (
        (x_pos, y_pos),
        (x_pos + width, y_pos),
        (x_pos + width, y_pos + height),
        (x_pos, y_pos + height),
    )


def _corner_outline(
    placed: Mapping[str, Any],
) -> tuple[tuple[float, float], ...] | None:
    oriented = _outline_from_recorded_orientation(placed)
    if oriented is not None:
        return oriented
    width = num(placed.get("w"))
    height = num(placed.get("h"))
    if width <= 0 or height <= 0:
        return None
    position = str(placed.get("clipped_corner_position") or "")
    cut_x = num(placed.get("clipped_corner_width_cm"))
    cut_y = num(placed.get("clipped_corner_length_cm"))
    if placed.get("rotated"):
        position = _ROTATED_CORNER.get(position, "")
        cut_x, cut_y = cut_y, cut_x
    if cut_x <= 0 or cut_y <= 0 or cut_x >= width or cut_y >= height:
        return None
    local = _corner_local(
        width,
        height,
        cut_x,
        cut_y,
        position,
        str(placed.get("piece_type") or ""),
    )
    if local is None or validate_polygon(local, _GEOMETRY_TOLERANCE_CM):
        return None
    x_pos = num(placed.get("x"))
    y_pos = num(placed.get("y"))
    return tuple((x_pos + point[0], y_pos + point[1]) for point in local)


def _special_outline(
    placed: Mapping[str, Any],
) -> tuple[tuple[float, float], ...] | None:
    raw = placed.get("special_shape_geometry_json")
    if isinstance(raw, str):
        if not raw.strip():
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
    elif isinstance(raw, Mapping):
        payload = raw
    else:
        return None
    if (
        not isinstance(payload, Mapping)
        or payload.get("version") != 1
        or payload.get("kind") != "polygon"
        or payload.get("units") != "cm"
        or payload.get("exact") is False
    ):
        return None
    blank_w = round(num(payload.get("blank_width_cm")), 3)
    blank_h = round(num(payload.get("blank_length_cm")), 3)
    expected_w = num(
        placed.get("original_w")
        or placed.get("original_width_cm")
        or placed.get("width_cm")
        or blank_w
    )
    expected_h = num(
        placed.get("original_h")
        or placed.get("original_length_cm")
        or placed.get("length_cm")
        or blank_h
    )
    if blank_w <= 0 or blank_h <= 0:
        return None
    if abs(blank_w - expected_w) > _SPECIAL_EPSILON_CM or abs(blank_h - expected_h) > _SPECIAL_EPSILON_CM:
        return None
    points = _normalized_special_points(payload.get("points"))
    if points is None or not (3 <= len(points) <= _MAX_SPECIAL_VERTICES):
        return None
    if any(
        point[0] < -_SPECIAL_EPSILON_CM
        or point[1] < -_SPECIAL_EPSILON_CM
        or point[0] > blank_w + _SPECIAL_EPSILON_CM
        or point[1] > blank_h + _SPECIAL_EPSILON_CM
        for point in points
    ):
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if (
        abs(min(xs)) > _SPECIAL_EPSILON_CM
        or abs(max(xs) - blank_w) > _SPECIAL_EPSILON_CM
        or abs(min(ys)) > _SPECIAL_EPSILON_CM
        or abs(max(ys) - blank_h) > _SPECIAL_EPSILON_CM
    ):
        return None
    if validate_polygon(points, _SPECIAL_EPSILON_CM):
        return None
    if placed.get("rotated"):
        points = tuple((blank_h - point[1], point[0]) for point in points)
        scale_w, scale_h = blank_h, blank_w
    else:
        scale_w, scale_h = blank_w, blank_h
    viewport_w = num(placed.get("w"))
    viewport_h = num(placed.get("h"))
    if viewport_w <= 0 or viewport_h <= 0 or scale_w <= 0 or scale_h <= 0:
        return None
    x_pos = num(placed.get("x"))
    y_pos = num(placed.get("y"))
    outline = tuple(
        (
            x_pos + (point[0] / scale_w) * viewport_w,
            y_pos + (point[1] / scale_h) * viewport_h,
        )
        for point in points
    )
    if validate_polygon(outline, _GEOMETRY_TOLERANCE_CM):
        return None
    return outline


def _normalized_special_points(points: Any) -> tuple[tuple[float, float], ...] | None:
    if not isinstance(points, (list, tuple)):
        return None
    normalized: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return None
        normalized.append((round(num(point[0]), 3), round(num(point[1]), 3)))
    if len(normalized) > 1 and normalized[0] == normalized[-1]:
        normalized.pop()
    return tuple(normalized)


def _glass_ring(placed: Mapping[str, Any]) -> list[list[float]] | None:
    stored = placed.get("glass_hole_local_mm")
    if isinstance(stored, (list, tuple)) and len(stored) >= 4:
        return stored
    ring = placed_glass_hole_mm(placed, rotated=bool(placed.get("rotated")))
    return ring


def _glass_holes(piece: Mapping[str, Any]) -> tuple[tuple[tuple[float, float], ...], ...]:
    polygon = _hole_polygon(piece)
    if polygon is None:
        return ()
    return (polygon,)


def _hole_polygon(host: Mapping[str, Any]) -> tuple[tuple[float, float], ...] | None:
    rect = opening_board_rect(host)
    if rect is None:
        ring = _glass_ring(host)
        if ring is None:
            return None
        probe = dict(host)
        probe["piece_type"] = "Glass"
        probe["glass_hole_local_mm"] = ring
        if num(probe.get("w")) <= 0:
            probe["w"] = num(probe.get("width_cm"))
            probe["h"] = num(probe.get("length_cm"))
            probe["x"] = num(probe.get("x"))
            probe["y"] = num(probe.get("y"))
        rect = opening_board_rect(probe)
    if rect is None:
        return None
    x_pos = num(rect["x"])
    y_pos = num(rect["y"])
    return (
        (x_pos, y_pos),
        (x_pos + num(rect["w"]), y_pos),
        (x_pos + num(rect["w"]), y_pos + num(rect["h"])),
        (x_pos, y_pos + num(rect["h"])),
    )


def _l_polygons(
    width: float, height: float, cut_x: float, cut_y: float
) -> dict[str, tuple[tuple[float, float], ...]]:
    return {
        "Top Right": (
            (0.0, 0.0),
            (width - cut_x, 0.0),
            (width - cut_x, cut_y),
            (width, cut_y),
            (width, height),
            (0.0, height),
        ),
        "Top Left": (
            (cut_x, 0.0),
            (width, 0.0),
            (width, height),
            (0.0, height),
            (0.0, cut_y),
            (cut_x, cut_y),
        ),
        "Bottom Right": (
            (0.0, 0.0),
            (width, 0.0),
            (width, height - cut_y),
            (width - cut_x, height - cut_y),
            (width - cut_x, height),
            (0.0, height),
        ),
        "Bottom Left": (
            (0.0, 0.0),
            (width, 0.0),
            (width, height),
            (cut_x, height),
            (cut_x, height - cut_y),
            (0.0, height - cut_y),
        ),
    }


def _clipped_polygons(
    width: float, height: float, cut_x: float, cut_y: float
) -> dict[str, tuple[tuple[float, float], ...]]:
    return {
        "Top Right": (
            (0.0, 0.0),
            (width - cut_x, 0.0),
            (width, cut_y),
            (width, height),
            (0.0, height),
        ),
        "Top Left": (
            (cut_x, 0.0),
            (width, 0.0),
            (width, height),
            (0.0, height),
            (0.0, cut_y),
        ),
        "Bottom Right": (
            (0.0, 0.0),
            (width, 0.0),
            (width, height - cut_y),
            (width - cut_x, height),
            (0.0, height),
        ),
        "Bottom Left": (
            (0.0, 0.0),
            (width, 0.0),
            (width, height),
            (cut_x, height),
            (0.0, height - cut_y),
        ),
    }


def _outline_from_recorded_orientation(
    placed: Mapping[str, Any],
) -> tuple[tuple[float, float], ...] | None:
    """Draw a corner from its stored position plus the shared transform.

    Historical pieces that only have ``rotated`` stay on the one-swap path.
    A recorded quarter-turn or mirror is applied once, to the original local
    polygon, and is not combined with that swap.
    """

    turns = placed.get("corner_rotation_quarter_turns")
    if not isinstance(turns, int):
        recorded = placed.get("placement_quarter_turns")
        turns = recorded if isinstance(recorded, int) else None
    from .placement_orientation import recorded_mirror

    if not isinstance(turns, int) and not recorded_mirror(placed):
        return None
    mirrored = recorded_mirror(placed)
    width = num(placed.get("original_w")) or num(placed.get("width_cm"))
    height = num(placed.get("original_h")) or num(placed.get("length_cm"))
    if width <= 0 or height <= 0:
        return None
    position = str(placed.get("clipped_corner_position") or "")
    cut_x = num(placed.get("clipped_corner_width_cm"))
    cut_y = num(placed.get("clipped_corner_length_cm"))
    if cut_x <= 0 or cut_y <= 0 or cut_x >= width or cut_y >= height:
        return None
    local = _corner_local(
        width,
        height,
        cut_x,
        cut_y,
        position,
        str(placed.get("piece_type") or ""),
    )
    if local is None or validate_polygon(local, _GEOMETRY_TOLERANCE_CM):
        return None
    from .placement_orientation import PlacementOrientation, transform_ring

    moved = transform_ring(
        local,
        PlacementOrientation(mirrored, int(turns or 0) % 4),
        width=width,
        height=height,
    )
    x_pos = num(placed.get("x"))
    y_pos = num(placed.get("y"))
    return tuple((x_pos + point[0], y_pos + point[1]) for point in moved)


def _corner_local(
    width: float,
    height: float,
    cut_x: float,
    cut_y: float,
    position: str,
    piece_type: str,
) -> tuple[tuple[float, float], ...] | None:
    table = (
        _l_polygons(width, height, cut_x, cut_y)
        if piece_type == "L-Shaped Corner"
        else _clipped_polygons(width, height, cut_x, cut_y)
    )
    return table.get(position)


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
