"""Cross-board repack after the base search.

A board is cancelled only when every piece on it fits the remaining boards,
the piece count is unchanged, and validation reports no overlap or kerf fault.
Finished nests move only as rigid groups: the same rotation, mirror, kerf
gaps, void guests, and glass-host links. Loose regular pieces may still move
one at a time. When the board count stays the same, a short local search may
move or swap a few of those loose pieces so the largest separable remnant
grows. Fewer boards remain better than a larger remnant.
"""

from __future__ import annotations

import time
from copy import deepcopy
from itertools import combinations
from typing import Any

from .primitives import (
    make_placed_piece,
    num,
    orientations_for,
    prune_free_rects,
    rects_have_clearance,
    split_free_rect,
)


_MAX_REMNANT_ATTEMPTS = 12
_MAX_WHOLE_REPACK_ATTEMPTS = 16
_MAX_REPACK_ATTEMPTS = 64
_MAX_REPACK_PIECES = 64
_LOCKED_PIECE_TYPES = frozenset({"Clipped Corner", "L-Shaped Corner", "Glass"})
_PRESERVED_PLAN_KEYS = (
    "method_key",
    "method_label",
    "optimization_mode",
    "ordering_strategy",
    "attempts",
    "complexity",
    "search_elapsed_sec",
    "search_time_limit_sec",
    "solver_status",
    "solver_wall_time_sec",
    "glass_nesting_diagnostics",
    "shape_nesting_diagnostics",
)


def improve_plan_search(
    plan: dict[str, Any],
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
    mirroring_allowed: bool = False,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    """Drop cancellable boards, then try bounded same-count remnant moves."""

    if machine_type == "Panel Saw" or time_limit_sec <= 0:
        return plan
    if plan.get("unplaced") or not plan.get("sheets"):
        return plan
    if deadline_monotonic is None:
        deadline_monotonic = time.monotonic() + float(time_limit_sec)
    if time.monotonic() >= deadline_monotonic:
        return plan
    from .evaluation import placement_permission_errors, validate_plan
    from .nesting_consolidation import consolidate_nested_boards
    from .optimizer import _candidate_is_better, enrich_plan_metrics

    metric_kwargs = {
        "min_remnant_width_cm": min_remnant_width_cm,
        "min_remnant_length_cm": min_remnant_length_cm,
        "min_remnant_area_m2": min_remnant_area_m2,
    }
    consolidated = consolidate_nested_boards(
        plan,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type=machine_type,
        mirroring_allowed=mirroring_allowed,
        deadline=min(
            time.monotonic() + min(1.5, max(0.05, 0.2 * float(time_limit_sec))),
            deadline_monotonic,
        ),
    )
    best = plan
    if consolidated is not plan:
        best = enrich_plan_metrics(
            consolidated,
            str(plan.get("method_key") or ""),
            machine_type,
            **metric_kwargs,
        )
        for key in _PRESERVED_PLAN_KEYS:
            if key in plan and key not in best:
                best[key] = plan[key]
    # A receiving board may have enough material capacity but no current slot.
    # Re-form a bounded regular-piece neighborhood before optimizing offcuts.
    for candidate in _repacked_board_candidates(
        best, pieces, board_w_cm, board_h_cm, kerf_cm, deadline_monotonic,
    ):
        accepted = _accept_candidate(candidate, best, pieces, board_w_cm, board_h_cm, kerf_cm,
            machine_type=machine_type, mirroring_allowed=mirroring_allowed, metric_kwargs=metric_kwargs,
            enrich_plan_metrics=enrich_plan_metrics, validate_plan=validate_plan,
            permission_errors=placement_permission_errors, is_better=_candidate_is_better,
            deadline=deadline_monotonic)
        if accepted is not None:
            best = accepted
            break
    # Compact a bounded number of loose pieces/rigid nests even on one board.
    # Every accepted shift must improve the existing industrial contract.
    for candidate in _compaction_candidates(best, kerf_cm, board_w_cm, board_h_cm, deadline_monotonic):
        accepted = _accept_candidate(candidate, best, pieces, board_w_cm, board_h_cm, kerf_cm,
            machine_type=machine_type, mirroring_allowed=mirroring_allowed, metric_kwargs=metric_kwargs,
            enrich_plan_metrics=enrich_plan_metrics, validate_plan=validate_plan,
            permission_errors=placement_permission_errors, is_better=_candidate_is_better,
            deadline=deadline_monotonic)
        if accepted is not None:
            best = accepted
    sheets = list(best.get("sheets") or [])
    if len(sheets) < 2:
        return best
    ordered = sorted(
        sheets,
        key=lambda sheet: (
            len(sheet.get("pieces") or []),
            sum(num(piece.get("area_m2")) for piece in sheet.get("pieces") or []),
        ),
    )
    for victim in ordered[:3]:
        # First Fit can consume the only gap that fits a later piece. Retry
        # that victim once, visiting the same destination boards in reverse.
        for reverse_destinations in (False, True):
            if time.monotonic() >= deadline_monotonic:
                break
            candidate = _move_sheet_onto_others(
                best, victim, kerf_cm, deadline_monotonic=deadline_monotonic,
                reverse_destinations=reverse_destinations,
            )
            if candidate is None:
                continue
            if len(candidate.get("sheets") or []) >= len(best.get("sheets") or []):
                continue
            accepted = _accept_candidate(
                candidate,
                best,
                pieces,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                machine_type=machine_type,
                mirroring_allowed=mirroring_allowed,
                metric_kwargs=metric_kwargs,
                enrich_plan_metrics=enrich_plan_metrics,
                validate_plan=validate_plan,
                permission_errors=placement_permission_errors,
                is_better=_candidate_is_better,
                deadline=deadline_monotonic,
            )
            if accepted is not None:
                best = accepted
                break
    deadline = min(
        time.monotonic() + min(time_limit_sec, max(0.05, 0.15 * time_limit_sec)),
        deadline_monotonic,
    )
    return _improve_remnants(
        best,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type=machine_type,
        mirroring_allowed=mirroring_allowed,
        metric_kwargs=metric_kwargs,
        deadline=deadline,
        enrich_plan_metrics=enrich_plan_metrics,
        validate_plan=validate_plan,
        permission_errors=placement_permission_errors,
        is_better=_candidate_is_better,
    )


def regular_board_floor_proven(plan, pieces, board_w_cm, board_h_cm):
    """A valid all-full-board rectangular plan cannot lose another board."""
    sheets = plan.get("sheets") or []
    return (board_w_cm > 0 and board_h_cm > 0 and len(sheets) > 1
        and not plan.get("unplaced") and bool(pieces)
        and all((p.get("piece_type") or "Regular") == "Regular"
            and (p.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD" for p in pieces)
        and not _locked_piece_ids(plan)
        and all((s.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
            and all((p.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
                    and (p.get("piece_type") or "Regular") == "Regular"
                    and not p.get("geometry") and not p.get("overlays")
                    for p in s.get("pieces") or []) for s in sheets)
        and sum(num(p.get("width_cm"))*num(p.get("length_cm")) for p in pieces)
            > (len(sheets)-1)*board_w_cm*board_h_cm + 1e-9)


def _regular_layout_quality(plan, kerf_cm):
    """Exact adjacency fraction and repeated-size board splits; no score."""
    aligned = adjacent = 0
    sizes = {}
    for sheet_index, sheet in enumerate(plan.get("sheets") or []):
        placed = sheet.get("pieces") or []
        for index, piece in enumerate(placed):
            size = tuple(sorted((round(num(piece.get("w")), 6), round(num(piece.get("h")), 6))))
            sizes.setdefault(size, set()).add(sheet_index)
            for other in placed[index+1:]:
                dx = max(other["x"]-piece["x"]-piece["w"], piece["x"]-other["x"]-other["w"])
                dy = max(other["y"]-piece["y"]-piece["h"], piece["y"]-other["y"]-other["h"])
                if (abs(dx-kerf_cm) <= 1e-6 and dy < 0) or (abs(dy-kerf_cm) <= 1e-6 and dx < 0):
                    adjacent += 1
                    axis, extent = ("y", "h") if abs(dx-kerf_cm) <= 1e-6 else ("x", "w")
                    aligned += int(abs(piece[axis]-other[axis]) <= 1e-6 or
                        abs(piece[axis]+piece[extent]-other[axis]-other[extent]) <= 1e-6)
    return aligned, max(1, adjacent), sum(len(boards)-1 for boards in sizes.values())


def improve_same_count_layout(plan, pieces, board_w_cm, board_h_cm, kerf_cm, *,
        machine_type, mirroring_allowed, metric_kwargs, deadline):
    """At most three dense regular-board pairs; no cancellation/shape policy change."""
    if machine_type not in {"Auto", "CNC Router"} or time.monotonic() >= deadline:
        return plan
    if not regular_board_floor_proven(plan, pieces, board_w_cm, board_h_cm):
        return plan
    from .evaluation import placement_permission_errors, validate_plan
    from .optimizer import _run_preordered_method, order_pieces, enrich_plan_metrics, _candidate_is_better

    source = {int(p["id"]): p for p in pieces}
    locked = _locked_piece_ids(plan)
    eligible = [(i, s) for i, s in enumerate(plan["sheets"]) if s.get("pieces") and all(
        int(p["id"]) in source and int(p["id"]) not in locked for p in s["pieces"])]
    # Preserve the sparse remnant board where possible; organize dense pairs first.
    eligible.sort(key=lambda item: -sum(num(p.get("w"))*num(p.get("h")) for p in item[1]["pieces"]))
    best = plan
    before = _regular_layout_quality(plan, kerf_cm)
    attempts = 0
    for left in range(min(3, len(eligible))):
        for right in range(left+1, min(3, len(eligible))):
            if attempts >= 3 or time.monotonic() >= deadline:
                return best
            i, first = eligible[left]
            j, second = eligible[right]
            subset = [source[int(p["id"])] for sheet in (first, second) for p in sheet["pieces"]]
            if len(subset) > _MAX_REPACK_PIECES:
                continue
            attempts += 1
            packed = _run_preordered_method(order_pieces(subset, "long_side_desc"), subset,
                board_w_cm, board_h_cm, kerf_cm, "MaxRects Contact Point", "long_side_desc")
            if packed.get("unplaced") or len(packed.get("sheets") or []) != 2:
                continue
            candidate = deepcopy(plan)
            for index, sheet in zip((i, j), packed["sheets"]):
                candidate["sheets"][index]["pieces"] = sheet["pieces"]
                for cache in ("free_rects", "skyline", "shelves"):
                    candidate["sheets"][index].pop(cache, None)
            after = _regular_layout_quality(candidate, kerf_cm)
            alignment_change = after[0]*before[1] - before[0]*after[1]
            if alignment_change < 0 or after[2] > before[2] or (alignment_change == 0 and after[2] == before[2]):
                continue
            accepted = _accept_candidate(candidate, best, pieces, board_w_cm, board_h_cm, kerf_cm,
                machine_type=machine_type, mirroring_allowed=mirroring_allowed, metric_kwargs=metric_kwargs,
                enrich_plan_metrics=enrich_plan_metrics, validate_plan=validate_plan,
                permission_errors=placement_permission_errors, is_better=_candidate_is_better, deadline=deadline)
            if accepted is not None and time.monotonic() < deadline:
                best = accepted
    return best


def improve_board_regrouping(plan, pieces, board_w_cm, board_h_cm, kerf_cm, *,
        machine_type, mirroring_allowed, metric_kwargs, deadline, candidate_callback=None):
    """Experimental final-tail regrouping of a validated incumbent.

    No extra time is reserved. Completed improvements are published immediately
    so a later timed-out proposal cannot erase earlier verified work. This is
    deliberately opt-in at the Smart caller, pending the paired adoption gates.
    """
    if (machine_type not in {"Auto", "CNC Router"} or plan.get("unplaced")
            or time.monotonic() >= deadline):
        return plan
    from .evaluation import placement_permission_errors, validate_plan
    from .optimizer import _candidate_is_better, enrich_plan_metrics

    best = plan
    for candidate in _regrouped_board_candidates(
        plan, pieces, board_w_cm, board_h_cm, kerf_cm, deadline,
    ):
        if time.monotonic() >= deadline:
            break
        accepted = _accept_candidate(candidate, best, pieces, board_w_cm, board_h_cm, kerf_cm,
            machine_type=machine_type, mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs, enrich_plan_metrics=enrich_plan_metrics,
            validate_plan=validate_plan, permission_errors=placement_permission_errors,
            is_better=_candidate_is_better, deadline=deadline)
        if accepted is not None and time.monotonic() < deadline:
            best = accepted
            if candidate_callback is not None:
                candidate_callback(best)
    return best


def _regrouped_board_candidates(plan, pieces, board_w_cm, board_h_cm, kerf_cm, deadline):
    """At most 24 native packs over small, whole regular-board neighborhoods.

    Packing uses the original source objects for identities, machining and
    transform permissions. Protected sheets stay intact; no partial insertion
    can escape. Proposals still require whole-plan industrial validation.
    """
    from .optimizer import _run_preordered_method, order_pieces

    if time.monotonic() >= deadline:
        return
    source = {int(piece["id"]): piece for piece in pieces}
    locked = _locked_piece_ids(plan)
    eligible = []
    for sheet in plan.get("sheets") or []:
        if ((sheet.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
                or not sheet.get("pieces")):
            continue
        if all(int(piece["id"]) in source and int(piece["id"]) not in locked
            and all((item.get("piece_type") or "Regular") == "Regular"
                and (item.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
                and not item.get("geometry") and not item.get("overlays")
                and not item.get("placement_outline_cm")
                and not item.get("special_shape_geometry_json")
                for item in (piece, source[int(piece["id"])]))
            for piece in sheet["pieces"]):
            eligible.append(sheet)
    eligible.sort(key=lambda sheet: (len(sheet["pieces"]),
        sum(num(piece.get("area_m2")) for piece in sheet["pieces"]), sheet["sheet_no"]))
    neighborhoods = [combo for count in (2, 3) for combo in combinations(eligible[:4], count)
        if sum(len(sheet["pieces"]) for sheet in combo) <= _MAX_REPACK_PIECES]
    neighborhoods.sort(key=lambda combo: (sum(len(sheet["pieces"]) for sheet in combo), len(combo)))
    attempts = 0
    for combo in neighborhoods[:3]:
        subset = [source[piece_id] for piece_id in sorted(
            int(piece["id"]) for sheet in combo for piece in sheet["pieces"])]
        sheet_numbers = {sheet["sheet_no"] for sheet in combo}
        for ordering in ("long_side_desc", "area_desc", "short_side_desc"):
            for method in ("MaxRects Bottom Left", "MaxRects Contact Point",
                           "MaxRects Best Short Side", "MaxRects Best Area"):
                if attempts >= 24 or time.monotonic() >= deadline:
                    return
                attempts += 1
                packed = _run_preordered_method(order_pieces(subset, ordering), subset,
                    board_w_cm, board_h_cm, kerf_cm, method, ordering)
                if (packed.get("unplaced") or not packed.get("sheets")
                        or len(packed["sheets"]) > len(combo)):
                    continue
                candidate = deepcopy(plan)
                kept = [sheet for sheet in candidate["sheets"] if sheet["sheet_no"] not in sheet_numbers]
                # Keep full-board metadata while replacing packing caches and
                # placements. Unselected sheets are copied without alterations.
                replacements = []
                for old, new in zip(combo, packed["sheets"]):
                    replacement = deepcopy(old)
                    for cache in ("free_rects", "skyline", "shelves"):
                        replacement.pop(cache, None)
                    replacement.update(new)
                    replacements.append(replacement)
                candidate["sheets"] = kept + replacements
                for number, sheet in enumerate(candidate["sheets"], 1):
                    sheet["sheet_no"] = number
                if time.monotonic() >= deadline:
                    return
                yield candidate


def _repacked_board_candidates(plan, pieces, board_w_cm, board_h_cm, kerf_cm, deadline):
    """Try cancelling a board by re-packing one receiving board with its pieces.

    Source objects preserve identity, permissions and machining. Irregular,
    nested and OFFCUT pieces stay on their existing paths. Every result still
    passes the normal whole-plan acceptance gate; this only generates proposals.
    """
    from .optimizer import _run_preordered_method, order_pieces

    source = {int(p["id"]): p for p in pieces}
    locked = _locked_piece_ids(plan)
    sheets = list(plan.get("sheets") or [])
    if len(sheets) < 2:
        return
    if all((p.get("piece_type") or "Regular") == "Regular"
           and (p.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD" for p in pieces) and sum(
        num(p.get("width_cm"))*num(p.get("length_cm")) for p in pieces
    ) > (len(sheets)-1)*board_w_cm*board_h_cm + 1e-9:
        return  # Material area already proves that another board cannot go.
    eligible = [s for s in sheets if s.get("pieces") and all(
        int(p["id"]) in source and int(p["id"]) not in locked
        and (source[int(p["id"])].get("piece_type") or "Regular") == "Regular"
        and (source[int(p["id"])].get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
        and (p.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
        for p in s["pieces"])]
    eligible.sort(key=lambda s: (len(s["pieces"]), sum(num(p.get("area_m2")) for p in s["pieces"])))
    attempts = 0

    def pack_one(subset, orderings):
        nonlocal attempts
        if len(subset) > _MAX_REPACK_PIECES or sum(
            num(p.get("width_cm"))*num(p.get("length_cm")) for p in subset
        ) > board_w_cm*board_h_cm + 1e-9:
            return None
        for ordering in orderings:
            sequence = order_pieces(subset, ordering)
            for method in ("MaxRects Contact Point", "MaxRects Best Short Side", "MaxRects Best Area", "MaxRects Bottom Left"):
                if time.monotonic() >= deadline or attempts >= _MAX_REPACK_ATTEMPTS:
                    return None
                attempts += 1
                packed = _run_preordered_method(sequence, subset, board_w_cm, board_h_cm,
                    kerf_cm, method, ordering)
                if not packed.get("unplaced") and len(packed.get("sheets") or []) == 1:
                    return packed["sheets"][0]
        return None

    def renumber(candidate):
        for number, sheet in enumerate(candidate["sheets"], 1):
            sheet["sheet_no"] = number
        return candidate

    # Try the whole victim first, reserving work for distributed reinsertion.
    attempted = set()
    for victim in eligible[:3]:
        for target in eligible[:4]:
            if time.monotonic() >= deadline:
                return
            if victim is target or attempts >= _MAX_WHOLE_REPACK_ATTEMPTS:
                continue
            pair = frozenset((victim["sheet_no"], target["sheet_no"]))
            if pair in attempted:
                continue
            attempted.add(pair)
            subset = [source[int(p["id"])] for s in (target, victim) for p in s["pieces"]]
            packed = pack_one(subset, ("area_desc", "long_side_desc"))
            if packed is not None:
                candidate = deepcopy(plan)
                candidate["sheets"] = [s for s in candidate["sheets"] if s["sheet_no"] not in pair]
                candidate["sheets"].append(packed)
                yield renumber(candidate)

    # Several victim pieces can require different receiving boards. Re-pack
    # only the receiving board of each insertion, committing nothing partially.
    eligible_numbers = {s["sheet_no"] for s in eligible[:4]}
    for victim in eligible[:3]:
        moving = sorted(victim["pieces"], key=lambda p: -num(p.get("area_m2")))
        for reverse in (False, True):
            candidate = deepcopy(plan)
            candidate["sheets"] = [s for s in candidate["sheets"] if s["sheet_no"] != victim["sheet_no"]]
            targets = sorted(candidate["sheets"], key=lambda s: sum(num(p.get("area_m2")) for p in s["pieces"]),
                reverse=reverse)
            for piece in moving:
                inserted = False
                for target in targets:
                    if time.monotonic() >= deadline or attempts >= _MAX_REPACK_ATTEMPTS:
                        return
                    if target["sheet_no"] not in eligible_numbers:
                        continue
                    subset = [source[int(p["id"])] for p in target["pieces"]]+[source[int(piece["id"])]]
                    packed = pack_one(subset, ("area_desc", "long_side_desc", "width_desc", "length_desc"))
                    if packed is not None:
                        target["pieces"] = packed["pieces"]
                        for key in ("free_rects", "skyline", "shelves"):
                            target.pop(key, None)
                        inserted = True
                        break
                if not inserted:
                    break
            else:
                yield renumber(candidate)


def _compaction_candidates(plan, kerf_cm, board_w_cm, board_h_cm, deadline):
    from .nesting_consolidation import (
        STANDALONE, L_PAIR, CLIPPED_PAIR, SINGLE_CORNER,
        best_rigid_translation, extract_placement_groups,
    )
    from .shape_aware_nesting import _translate_pieces

    attempts = 0
    # Three boards, four groups each: no layout-size-dependent candidate growth.
    for sheet in list(plan.get("sheets") or [])[:3]:
        if time.monotonic() >= deadline:
            return
        groups = extract_placement_groups({"sheets": [sheet]})
        groups.sort(key=lambda group: group.origin_x + group.origin_y)
        for group in groups[:4]:
            if time.monotonic() >= deadline or attempts >= _MAX_REMNANT_ATTEMPTS:
                return
            attempts += 1
            ids = set(group.piece_ids)
            copied = deepcopy(plan)
            target = next(item for item in copied["sheets"] if item["sheet_no"] == sheet["sheet_no"])
            target["pieces"] = [p for p in target["pieces"] if int(p["id"]) not in ids]
            if group.kind == STANDALONE:
                piece = group.pieces[0]
                if str(piece.get("piece_type") or "Regular") != "Regular":
                    continue
                source = _source_from_placed(piece)
                spot = _spot_on_sheet(target, source, kerf_cm, deadline_monotonic=deadline)
                if spot is None:
                    continue
                target["pieces"].append(make_placed_piece(source, spot["x"], spot["y"],
                    spot["w"], spot["h"], bool(spot["rotated"])))
            else:
                constraint = "pair" if group.kind in (L_PAIR, CLIPPED_PAIR) else (
                    "single" if group.kind == SINGLE_CORNER else "")
                shift = best_rigid_translation(target, group.pieces, kerf_cm, board_w_cm, board_h_cm,
                                              constraint=constraint, deadline=deadline)
                if shift is None:
                    continue
                target["pieces"].extend(_translate_pieces(group.pieces, shift[0], shift[1]))
            plan = copied
            yield copied


def _move_sheet_onto_others(
    plan: dict[str, Any],
    victim: dict[str, Any],
    kerf_cm: float,
    *,
    deadline_monotonic: float | None = None,
    reverse_destinations: bool = False,
) -> dict[str, Any] | None:
    preserved = _shape_nest_ids(plan)
    moving = [dict(piece) for piece in victim.get("pieces") or []]
    if not moving or any(int(piece["id"]) in preserved for piece in moving):
        return None
    copied = deepcopy(plan)
    kept = [
        sheet
        for sheet in copied.get("sheets") or []
        if sheet.get("sheet_no") != victim.get("sheet_no")
    ]
    if len(kept) == len(copied.get("sheets") or []):
        return None
    moving.sort(
        key=lambda piece: num(piece.get("w")) * num(piece.get("h")),
        reverse=True,
    )
    for piece in moving:
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            return None
        source = _source_from_placed(piece)
        destination = None
        for sheet in reversed(kept) if reverse_destinations else kept:
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                return None
            spot = _spot_on_sheet(sheet, source, kerf_cm, deadline_monotonic=deadline_monotonic)
            if spot is None:
                continue
            placed = make_placed_piece(
                source,
                spot["x"],
                spot["y"],
                spot["w"],
                spot["h"],
                bool(spot["rotated"]),
            )
            sheet.setdefault("pieces", []).append(placed)
            destination = sheet
            break
        if destination is None:
            return None
    for index, sheet in enumerate(kept, start=1):
        sheet["sheet_no"] = index
    copied["sheets"] = kept
    copied["unplaced"] = list(plan.get("unplaced") or [])
    return copied


def _source_from_placed(piece: dict[str, Any]) -> dict[str, Any]:
    source = dict(piece)
    if num(source.get("width_cm")) <= 0:
        source["width_cm"] = num(source.get("original_w") or source.get("w"))
    if num(source.get("length_cm")) <= 0:
        source["length_cm"] = num(source.get("original_h") or source.get("h"))
    return source


def _spot_on_sheet(
    sheet: dict[str, Any],
    piece: dict[str, Any],
    kerf_cm: float,
    *,
    deadline_monotonic: float | None = None,
) -> dict[str, float] | None:
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        return None
    occupied = [
        {
            "x": num(item.get("x")),
            "y": num(item.get("y")),
            "w": num(item.get("w")),
            "h": num(item.get("h")),
        }
        for item in sheet.get("pieces") or []
    ]
    gap = max(0.0, kerf_cm)
    for rect in _free_rectangles(sheet):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            return None
        inset = _inset(rect, kerf_cm)
        for orientation in orientations_for(piece):
            width, height = orientation["w"], orientation["h"]
            # A free-rectangle edge may be the board, not a cut obstacle.
            # Try contact with its real boundaries; clearance decides which
            # sides actually need Kerf. Keep the historical inset as fallback.
            xs = (rect["x"], rect["x"] + gap, rect["x"] + rect["w"] - width)
            ys = (rect["y"], rect["y"] + gap, rect["y"] + rect["h"] - height)
            anchors = [(x, y) for y in ys for x in xs]
            if inset is not None:
                anchors.append((inset["x"], inset["y"]))
            for x, y in dict.fromkeys(anchors):
                if (x < rect["x"] - 1e-6 or y < rect["y"] - 1e-6
                    or x + width > rect["x"] + rect["w"] + 1e-6
                    or y + height > rect["y"] + rect["h"] + 1e-6):
                    continue
                trial = dict(x=x, y=y, w=width, h=height, rotated=bool(orientation["rotated"]))
                if all(rects_have_clearance(trial, other, gap, 1e-6) for other in occupied):
                    return trial
    return None


def _free_rectangles(sheet: dict[str, Any]) -> list[dict[str, float]]:
    free: list[dict[str, float]] = [
        {
            "x": 0.0,
            "y": 0.0,
            "w": num(sheet.get("w")),
            "h": num(sheet.get("h")),
        }
    ]
    for piece in sheet.get("pieces") or []:
        used = {
            "x": num(piece.get("x")),
            "y": num(piece.get("y")),
            "w": num(piece.get("w")),
            "h": num(piece.get("h")),
        }
        nxt: list[dict[str, float]] = []
        for rect in free:
            nxt.extend(split_free_rect(rect, used))
        free = prune_free_rects(nxt)
    return sorted(free, key=lambda rect: rect["w"] * rect["h"], reverse=True)


def _accept_candidate(
    candidate: dict[str, Any],
    best: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    mirroring_allowed: bool,
    metric_kwargs: dict[str, float],
    enrich_plan_metrics: Any,
    validate_plan: Any,
    permission_errors: Any,
    is_better: Any,
    deadline: float | None = None,
) -> dict[str, Any] | None:
    if len(candidate.get("sheets") or []) > len(best.get("sheets") or []):
        return None
    if candidate.get("unplaced"):
        return None
    used_area = sum(num(p.get("area_m2")) for p in pieces)
    total_area = len(candidate.get("sheets") or [])*board_w_cm*board_h_cm/10000
    candidate = dict(candidate, used_area_m2=used_area, total_board_area_m2=total_area,
        waste_area_m2=max(0.0, total_area-used_area))
    enriched = enrich_plan_metrics(
        candidate,
        str(best.get("method_key") or ""),
        machine_type,
        **metric_kwargs,
    )
    for key in _PRESERVED_PLAN_KEYS:
        if key in best and key not in enriched:
            enriched[key] = best[key]
    baseline = best if best.get("industrial_rank") else enrich_plan_metrics(
        best,
        str(best.get("method_key") or ""),
        machine_type,
        **metric_kwargs,
    )
    if not is_better(enriched, baseline):
        return None
    if validate_plan(
        enriched,
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm=kerf_cm,
        deadline_monotonic=deadline,
    ):
        return None
    if permission_errors(enriched, pieces, mirroring_allowed=mirroring_allowed):
        return None
    return enriched


def compact_regular_final(plan, pieces, board_w_cm, board_h_cm, kerf_cm, *,
        machine_type, mirroring_allowed, metric_kwargs):
    """Close gaps in a small zero-remnant final, after native search has ended.

    Four deterministic axis sweeps, without rotation, regrouping or new sheets.
    Positive reusable remnants and protected shapes keep their existing layout.
    This never changes the seed or incumbent used by time-limited native search.
    """
    if (machine_type not in {"Auto", "CNC Router"} or not pieces
            or len(pieces) > _MAX_REPACK_PIECES or plan.get("unplaced")
            or not plan.get("sheets") or not plan.get("industrial_rank") or not plan.get("industrial_metrics")
            or plan.get("industrial_metrics", {}).get("largest_reusable_free_area_m2", 0) > 1e-9
            or any((p.get("piece_type") or "Regular") != "Regular"
                or (p.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD" for p in pieces)
            or _locked_piece_ids(plan)
            or any((s.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
                or any((p.get("piece_type") or "Regular") != "Regular"
                    or (p.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
                    or p.get("geometry") or p.get("overlays") or p.get("special_shape_geometry_json")
                    for p in s.get("pieces") or []) for s in plan["sheets"])):
        return plan
    from .evaluation import validate_plan, placement_permission_errors
    from .optimizer import enrich_plan_metrics

    if validate_plan(plan, pieces, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
        return plan
    best = plan
    for axis, extent, cross, cross_extent, far in (
        ("x", "w", "y", "h", False), ("x", "w", "y", "h", True),
        ("y", "h", "x", "w", False), ("y", "h", "x", "w", True)):
        candidate = deepcopy(best)
        changed = []
        for index, sheet in enumerate(candidate["sheets"]):
            ordered = sorted(sheet.get("pieces") or [], key=lambda p: (p[axis], p[cross], p["id"]), reverse=far)
            moved = False
            for position, piece in enumerate(ordered):
                bound = (board_w_cm if axis == "x" else board_h_cm)-piece[extent] if far else 0.0
                for other in ordered[:position]:
                    gap = max(piece[cross]-other[cross]-other[cross_extent],
                        other[cross]-piece[cross]-piece[cross_extent])
                    if gap < kerf_cm-1e-9:
                        bound = min(bound, other[axis]-kerf_cm-piece[extent]) if far else max(
                            bound, other[axis]+other[extent]+kerf_cm)
                if (far and bound > piece[axis]+1e-6) or (not far and bound < piece[axis]-1e-6):
                    piece[axis] = bound
                    moved = True
            if moved:
                changed.append(index)
                for cache in ("free_rects", "skyline", "shelves"):
                    sheet.pop(cache, None)
        if not changed:
            continue
        candidate = enrich_plan_metrics(candidate, str(plan.get("method_key") or ""),
            machine_type, **metric_kwargs)
        # The first four rank fields cover completeness, boards, machine and
        # reusable remnant. Estimated cuts cannot justify spreading the final.
        if tuple(candidate["industrial_rank"][:4]) > tuple(best["industrial_rank"][:4]):
            continue
        if validate_plan(candidate, pieces, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
            continue
        if placement_permission_errors(candidate, pieces, mirroring_allowed=mirroring_allowed):
            continue
        # Compaction and Final Alignment must share one *final* cutter-center
        # quality contract. Otherwise a border-biased rectangle estimate can
        # discard a long continuous in-board cutter route, forcing the next
        # stage to waste its bounded budget undoing the move.
        from .cut_line_quality import final_cut_quality_key, plan_cut_line_quality
        before = plan_cut_line_quality(best, kerf_cm)
        after = plan_cut_line_quality(candidate, kerf_cm)
        if before is None or after is None:
            continue  # conservative: never invent a score for unproven shapes
        if final_cut_quality_key(after) < final_cut_quality_key(before):
            best = candidate
    return best


def _rectangular_cleanup_geometry(plan, indices, kerf_cm):
    from math import dist
    from .cutter_center_paths import cutter_center_segments

    area = length = 0.0
    for index in indices:
        pieces = plan["sheets"][index].get("pieces") or []
        if not pieces:
            continue
        area += (max(p["x"]+p["w"] for p in pieces)-min(p["x"] for p in pieces)) * (
            max(p["y"]+p["h"] for p in pieces)-min(p["y"] for p in pieces))
        shapes = [([(p["x"]*10, p["y"]*10), ((p["x"]+p["w"])*10, p["y"]*10),
            ((p["x"]+p["w"])*10, (p["y"]+p["h"])*10), (p["x"]*10, (p["y"]+p["h"])*10)], [])
            for p in pieces]
        length += sum(dist(a, b) for a, b in cutter_center_segments(shapes, max(0.0, kerf_cm)*5))/10
    return area, length


def _improve_remnants(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    mirroring_allowed: bool,
    metric_kwargs: dict[str, float],
    deadline: float,
    enrich_plan_metrics: Any,
    validate_plan: Any,
    permission_errors: Any,
    is_better: Any,
) -> dict[str, Any]:
    """Move or swap a few regular pieces while the board count does not rise."""

    best = plan
    attempts = 0
    for move in _remnant_moves(best, deadline=deadline):
        if attempts >= _MAX_REMNANT_ATTEMPTS or time.monotonic() > deadline:
            break
        attempts += 1
        candidate = _relocate(best, move, kerf_cm)
        if candidate is None:
            continue
        accepted = _accept_candidate(
            candidate,
            best,
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type=machine_type,
            mirroring_allowed=mirroring_allowed,
            metric_kwargs=metric_kwargs,
            enrich_plan_metrics=enrich_plan_metrics,
            validate_plan=validate_plan,
            permission_errors=permission_errors,
            is_better=is_better,
            deadline=deadline,
        )
        if accepted is not None:
            best = accepted
    return best


def _remnant_moves(plan: dict[str, Any], *, deadline: float | None = None) -> list[tuple[tuple[int, int], ...]]:
    """A bounded list of piece moves and swaps, largest newly freed area first."""

    locked = _locked_piece_ids(plan)
    sheets = list(plan.get("sheets") or [])
    ranked: list[tuple[float, tuple[tuple[int, int], ...]]] = []
    for source in sheets:
        if deadline is not None and time.monotonic() >= deadline:
            return []
        movable = [
            piece
            for piece in source.get("pieces") or []
            if int(piece["id"]) not in locked
        ]
        movable.sort(
            key=lambda piece: _freed_area(source, piece),
            reverse=True,
        )
        chosen = movable[:2]
        for piece in chosen:
            for destination in sheets:
                if deadline is not None and time.monotonic() >= deadline:
                    return []
                if destination.get("sheet_no") == source.get("sheet_no"):
                    continue
                ranked.append(
                    (
                        _freed_area(source, piece),
                        ((int(piece["id"]), int(destination["sheet_no"])),),
                    )
                )
        if len(chosen) == 2:
            for destination in sheets:
                if deadline is not None and time.monotonic() >= deadline:
                    return []
                if destination.get("sheet_no") == source.get("sheet_no"):
                    continue
                ranked.append(
                    (
                        _freed_area(source, chosen[0]) + _freed_area(source, chosen[1]),
                        tuple(
                            (int(piece["id"]), int(destination["sheet_no"]))
                            for piece in chosen
                        ),
                    )
                )
    for left_index, left in enumerate(sheets):
        for right in sheets[left_index + 1 :]:
            if deadline is not None and time.monotonic() >= deadline:
                return []
            left_piece = _smallest_movable(left, locked)
            right_piece = _smallest_movable(right, locked)
            if left_piece is None or right_piece is None:
                continue
            ranked.append(
                (
                    0.0,
                    (
                        (int(left_piece["id"]), int(right["sheet_no"])),
                        (int(right_piece["id"]), int(left["sheet_no"])),
                    ),
                )
            )
    ranked.sort(key=lambda item: item[0], reverse=True)
    unique: list[tuple[tuple[int, int], ...]] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for _score, move in ranked:
        if move in seen:
            continue
        seen.add(move)
        unique.append(move)
        if len(unique) >= _MAX_REMNANT_ATTEMPTS:
            break
    return unique


def _relocate(
    plan: dict[str, Any],
    move: tuple[tuple[int, int], ...],
    kerf_cm: float,
) -> dict[str, Any] | None:
    copied = deepcopy(plan)
    located: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for sheet in copied.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            located[int(piece["id"])] = (sheet, piece)
    removed: list[tuple[dict[str, Any], int]] = []
    for piece_id, destination_no in move:
        found = located.get(int(piece_id))
        if found is None:
            return None
        source, piece = found
        source_pieces = source.setdefault("pieces", [])
        source_pieces.remove(piece)
        removed.append((piece, int(destination_no)))
    removed.sort(
        key=lambda item: num(item[0].get("w")) * num(item[0].get("h")),
        reverse=True,
    )
    sheets_by_no = {
        int(sheet.get("sheet_no")): sheet for sheet in copied.get("sheets") or []
    }
    for piece, destination_no in removed:
        destination = sheets_by_no.get(destination_no)
        if destination is None:
            return None
        source = _source_from_placed(piece)
        spot = _spot_on_sheet(destination, source, kerf_cm)
        if spot is None:
            return None
        destination.setdefault("pieces", []).append(
            make_placed_piece(
                source,
                spot["x"],
                spot["y"],
                spot["w"],
                spot["h"],
                bool(spot["rotated"]),
            )
        )
    kept = [sheet for sheet in copied.get("sheets") or [] if sheet.get("pieces")]
    if len(kept) != len(copied.get("sheets") or []):
        for index, sheet in enumerate(kept, start=1):
            sheet["sheet_no"] = index
        copied["sheets"] = kept
    copied["unplaced"] = list(plan.get("unplaced") or [])
    return copied


def _locked_piece_ids(plan: dict[str, Any]) -> set[int]:
    locked: set[int] = set()
    for sheet in plan.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            try:
                piece_id = int(piece["id"])
            except (TypeError, ValueError):
                continue
            host = piece.get("glass_host_piece_id")
            if host not in (None, ""):
                locked.add(piece_id)
                try:
                    locked.add(int(host))
                except (TypeError, ValueError):
                    pass
            if piece.get("placement_outline_cm"):
                locked.add(piece_id)
            if str(piece.get("piece_type") or "") in _LOCKED_PIECE_TYPES:
                locked.add(piece_id)
    locked.update(_shape_nest_ids(plan))
    return locked


def _shape_nest_ids(plan: dict[str, Any]) -> set[int]:
    """Pieces placed by a corner or glass nest, including guests in that void."""

    locked: set[int] = set()
    for sheet in plan.get("sheets") or []:
        pieces = list(sheet.get("pieces") or [])
        nested = [piece for piece in pieces if _records_shape_nest(piece)]
        for piece in nested:
            try:
                locked.add(int(piece["id"]))
            except (TypeError, ValueError):
                continue
        if not nested:
            continue
        min_x = min(num(piece.get("x")) for piece in nested)
        min_y = min(num(piece.get("y")) for piece in nested)
        max_x = max(num(piece.get("x")) + num(piece.get("w")) for piece in nested)
        max_y = max(num(piece.get("y")) + num(piece.get("h")) for piece in nested)
        for piece in pieces:
            if piece in nested:
                continue
            center_x = num(piece.get("x")) + num(piece.get("w")) / 2
            center_y = num(piece.get("y")) + num(piece.get("h")) / 2
            if min_x - 1e-6 <= center_x <= max_x + 1e-6 and min_y - 1e-6 <= center_y <= max_y + 1e-6:
                try:
                    locked.add(int(piece["id"]))
                except (TypeError, ValueError):
                    continue
    return locked


def _records_shape_nest(piece: dict[str, Any]) -> bool:
    if piece.get("glass_host_piece_id") not in (None, ""):
        return True
    if piece.get("placement_outline_cm") or piece.get("placement_rotation_deg"):
        return True
    if piece.get("mirrored") or piece.get("corner_mirrored") or piece.get("placement_mirrored"):
        return True
    return "corner_rotation_quarter_turns" in piece or "placement_quarter_turns" in piece


def _smallest_movable(
    sheet: dict[str, Any],
    locked: set[int],
) -> dict[str, Any] | None:
    movable = [
        piece
        for piece in sheet.get("pieces") or []
        if int(piece["id"]) not in locked
    ]
    if not movable:
        return None
    return min(movable, key=lambda piece: num(piece.get("w")) * num(piece.get("h")))


def _freed_area(sheet: dict[str, Any], piece: dict[str, Any]) -> float:
    before = _largest_free_area(sheet)
    remaining = [
        item for item in sheet.get("pieces") or [] if item.get("id") != piece.get("id")
    ]
    after = _largest_free_area({**sheet, "pieces": remaining})
    return after - before


def _largest_free_area(sheet: dict[str, Any]) -> float:
    return max(
        (rect["w"] * rect["h"] for rect in _free_rectangles(sheet)),
        default=0.0,
    )


def _inset(rect: dict[str, float], kerf_cm: float) -> dict[str, float] | None:
    gap = max(0.0, kerf_cm)
    width = rect["w"] - 2 * gap
    height = rect["h"] - 2 * gap
    if width <= 1e-6 or height <= 1e-6:
        return None
    return {
        "x": rect["x"] + gap,
        "y": rect["y"] + gap,
        "w": width,
        "h": height,
    }


__all__ = ["improve_plan_search"]
