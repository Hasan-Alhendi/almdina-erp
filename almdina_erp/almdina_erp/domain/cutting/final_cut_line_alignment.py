"""Bounded, non-packing final alignment of regular System cutter-center lines.

This module is deliberately not called from plan validation or imported DXF.
Only rigid translations within an existing FULL_BOARD are considered.
"""

from __future__ import annotations

import math
import time
from copy import deepcopy
from itertools import zip_longest
from typing import Any

from .cutter_center_paths import cutter_center_segments
from .evaluation import placement_permission_errors, validate_plan
from .optimizer import _largest_reusable_free_area, enrich_plan_metrics
from .plan_search import _locked_piece_ids
from .primitives import num

_MAX_PIECES = 64  # per-sheet bounded search, not a whole-order eligibility limit
_MAX_TRIALS = 24
_MAX_SWEEPS = 4
_EPS = 1e-7
_NETWORK_EPS_MM = 0.05


def _rectangles(plan: dict[str, Any], kerf_cm: float, *,
                regular_only: bool = False) -> tuple[float, int]:
    """Actual canonical cutter centers, summed per board (millimetres)."""
    length = 0.0
    count = 0
    for sheet in plan["sheets"]:
        shapes = [
            (
                [
                    (num(p["x"]) * 10, num(p["y"]) * 10),
                    ((num(p["x"]) + num(p["w"])) * 10, num(p["y"]) * 10),
                    ((num(p["x"]) + num(p["w"])) * 10, (num(p["y"]) + num(p["h"])) * 10),
                    (num(p["x"]) * 10, (num(p["y"]) + num(p["h"])) * 10),
                ],
                [],
            )
            for p in sheet.get("pieces") or []
            if not regular_only or _is_movable_regular(p)
        ]
        segments = cutter_center_segments(shapes, max(0.0, kerf_cm) * 5)
        length += sum(math.dist(a, b) for a, b in segments)
        count += len(segments)
    return length, count


def _is_movable_regular(piece: dict[str, Any]) -> bool:
    return (
        (piece.get("piece_type") or "Regular") == "Regular"
        and (piece.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
        and not any(piece.get(k) for k in (
            "geometry", "overlays", "special_shape_geometry_json",
            "placement_outline_cm", "glass_host_piece_id",
            "mirrored", "corner_mirrored", "placement_mirrored",
        ))
        and not any(piece.get(k) is None for k in ("x", "y", "w", "h"))
    )


def _eligible_ids(sheet: dict[str, Any], sources: dict[int, dict[str, Any]],
                  locked: set[int]) -> set[int]:
    if (sheet.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD":
        return set()
    if len(sheet.get("pieces") or []) > _MAX_PIECES:
        return set()  # large sheets need a separate indexed search, not O(n^3)
    return {
        int(piece["id"])
        for piece in sheet.get("pieces") or []
        if int(piece["id"]) not in locked and _is_movable_regular(piece)
        and int(piece["id"]) in sources
        and (sources[int(piece["id"])].get("piece_type") or "Regular") == "Regular"
        and (sources[int(piece["id"])].get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
    }


def _axis_alignment_score(plan: dict[str, Any], kerf_cm: float,
                          eligible_by_sheet: dict[int, set[int]]) -> int:
    """Secondary visual/coordinate objective, never a fictional shared cut.

    Only disjoint perpendicular bands qualify; nearby touching cuts are scored
    through the *actual* cutter-center network, not this secondary metric.
    """
    score = 0
    for index, sheet in enumerate(plan["sheets"]):
        pieces = [p for p in sheet.get("pieces") or []
                  if int(p["id"]) in eligible_by_sheet.get(index, set())]
        for i, a in enumerate(pieces):
            for b in pieces[i + 1:]:
                for axis, span, cross, cross_span in (
                    ("x", "w", "y", "h"), ("y", "h", "x", "w")
                ):
                    gap = max(
                        num(a[cross]) - num(b[cross]) - num(b[cross_span]),
                        num(b[cross]) - num(a[cross]) - num(a[cross_span]),
                    )
                    if gap <= kerf_cm + _EPS:
                        continue
                    same_start = abs(num(a[axis]) - num(b[axis])) <= _EPS
                    same_end = abs(num(a[axis]) + num(a[span]) -
                                   num(b[axis]) - num(b[span])) <= _EPS
                    score += (int(same_start) + int(same_end)) * int(
                        round(min(num(a[cross_span]), num(b[cross_span])) * 1000)
                    )
    return score


def _groups(sheet: dict[str, Any], axis: str) -> list[tuple[int, ...]]:
    """Singletons plus conservative whole rows/columns, never partial contacts."""
    pieces = sheet.get("pieces") or []
    cross, size = ("y", "h") if axis == "x" else ("x", "w")
    result = {tuple([int(piece["id"])]) for piece in pieces}
    ordered = sorted(pieces, key=lambda p: (num(p[cross]), num(p[cross]) + num(p[size]), int(p["id"])))
    groups: list[list[int]] = []
    group_end = -math.inf
    for piece in ordered:
        lo, hi = num(piece[cross]), num(piece[cross]) + num(piece[size])
        if not groups or lo >= group_end - _EPS:
            groups.append([])
            group_end = hi
        else:
            group_end = max(group_end, hi)
        groups[-1].append(int(piece["id"]))
    for ids in groups:
        if 1 < len(ids) < len(pieces):
            result.add(tuple(sorted(ids)))
    return sorted(result, key=lambda ids: (len(ids), ids))


def _movement_range(
    group: list[dict[str, Any]],
    fixed: list[dict[str, Any]],
    sheet: dict[str, Any],
    axis: str,
    kerf_cm: float,
) -> tuple[float, float] | None:
    """Continuous collision-free interval containing the original placement.

    Crossing a fixed door is disallowed, even if a more distant target would fit.
    Actual acceptance still uses the independent full-plan validator.
    """
    size = "w" if axis == "x" else "h"
    cross, cross_size = ("y", "h") if axis == "x" else ("x", "w")
    lo = max(-num(p[axis]) for p in group)
    hi = min(num(sheet[size]) - num(p[axis]) - num(p[size]) for p in group)
    for moving in group:
        a0, a1 = num(moving[axis]), num(moving[axis]) + num(moving[size])
        for stationary in fixed:
            gap = max(
                num(moving[cross]) - num(stationary[cross]) - num(stationary[cross_size]),
                num(stationary[cross]) - num(moving[cross]) - num(moving[cross_size]),
            )
            if gap >= kerf_cm - _EPS:
                continue
            b0, b1 = num(stationary[axis]), num(stationary[axis]) + num(stationary[size])
            if a1 + kerf_cm <= b0 + _EPS:
                hi = min(hi, b0 - kerf_cm - a1)
            elif b1 + kerf_cm <= a0 + _EPS:
                lo = max(lo, b1 + kerf_cm - a0)
            else:
                return None
    return (lo, hi) if lo <= hi + _EPS else None


def _candidate_moves(
    plan: dict[str, Any], kerf_cm: float,
    eligible_by_sheet: dict[int, set[int]],
    deadline: float | None,
) -> list[tuple[int, str, tuple[int, ...], float]]:
    """Axis events plus real shared-center contacts; no mm-by-mm scanning."""
    targets: dict[tuple[int, str, tuple[int, ...], float], int] = {}
    for sheet_index, sheet in enumerate(plan["sheets"]):
        pieces = list(sheet.get("pieces") or [])
        eligible = eligible_by_sheet.get(sheet_index, set())
        if len(eligible) < 2:
            continue
        by_id = {int(p["id"]): p for p in pieces}
        for axis in ("x", "y"):
            size = "w" if axis == "x" else "h"
            cross, cross_size = ("y", "h") if axis == "x" else ("x", "w")
            for ids in _groups(sheet, axis):
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if not set(ids).issubset(eligible):
                    continue
                members = [by_id[i] for i in ids]
                fixed = [p for p in pieces if int(p["id"]) not in ids]
                movable_range = _movement_range(members, fixed, sheet, axis, kerf_cm)
                if movable_range is None:
                    continue
                lo, hi = movable_range
                for a in members:
                    a0, a1 = num(a[axis]), num(a[axis]) + num(a[size])
                    for b in fixed:
                        if int(b["id"]) not in eligible:
                            continue
                        b0, b1 = num(b[axis]), num(b[axis]) + num(b[size])
                        gap = max(
                            num(a[cross]) - num(b[cross]) - num(b[cross_size]),
                            num(b[cross]) - num(a[cross]) - num(a[cross_size]),
                        )
                        # Axis alignment moves *matching* edges only.
                        # Closing a large inter-row gap merely to create a
                        # touching cutter path is compaction/repacking, not
                        # final alignment. Keep it outside this stage.
                        priority = 2 if gap <= kerf_cm + _EPS else 1
                        shifts = [(b0 - a0, priority), (b1 - a1, priority)]
                        for delta, priority in shifts:
                            if _EPS < abs(delta) and lo - _EPS <= delta <= hi + _EPS:
                                key = (sheet_index, axis, ids, round(delta, 6))
                                targets[key] = max(priority, targets.get(key, 0))
    # Reserve search coverage for both genuine shared-center opportunities and
    # separated-axis opportunities; either class alone can fill the trial cap.
    # Whole rigid rows/columns can retain shared centers that single-piece
    # shifts destroy. Try coherent groups before individual perturbations.
    key = lambda item: (-len(item[2]), abs(item[3]),
                        item[0], item[1], item[2], item[3])
    shared = sorted((move for move, priority in targets.items() if priority == 2), key=key)
    axes = sorted((move for move, priority in targets.items() if priority == 1), key=key)
    result = []
    for real_cut, axis_only in zip_longest(shared, axes):
        if real_cut is not None:
            result.append(real_cut)
        if axis_only is not None:
            result.append(axis_only)
    return result


def _translate_if_clear(
    plan: dict[str, Any], sheet_index: int, axis: str,
    ids: tuple[int, ...], delta: float, kerf_cm: float,
) -> dict[str, Any] | None:
    """Use exact rectangular clearance only as a cheap precheck."""
    original = plan["sheets"][sheet_index]
    pieces = list(original.get("pieces") or [])
    width, height = num(original.get("w")), num(original.get("h"))
    group = [p for p in pieces if int(p["id"]) in ids]
    fixed = [p for p in pieces if int(p["id"]) not in ids]
    for piece in group:
        x = num(piece["x"]) + (delta if axis == "x" else 0.0)
        y = num(piece["y"]) + (delta if axis == "y" else 0.0)
        w, h = num(piece["w"]), num(piece["h"])
        if x < -_EPS or y < -_EPS or x + w > width + _EPS or y + h > height + _EPS:
            return None
        for other in fixed:
            ox, oy, ow, oh = (num(other[k]) for k in ("x", "y", "w", "h"))
            dx = max(x - ox - ow, ox - x - w)
            dy = max(y - oy - oh, oy - y - h)
            if dx < kerf_cm - _EPS and dy < kerf_cm - _EPS:
                return None
    candidate = deepcopy(plan)
    sheet = candidate["sheets"][sheet_index]
    for piece in sheet["pieces"]:
        if int(piece["id"]) in ids:
            piece[axis] = num(piece[axis]) + delta
    for cache in ("free_rects", "skyline", "shelves"):
        sheet.pop(cache, None)
    return candidate


def align_regular_cut_lines(
    plan: dict[str, Any],
    sources: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    *,
    machine_type: str,
    mirroring_allowed: bool,
    metric_kwargs: dict[str, Any],
    deadline_monotonic: float | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded post-search improvement; never accept a worse real cut network.

    Axis coherence is a secondary goal only when actual cut length/fragmentation
    do not worsen. Protected pieces remain in their original position.
    """
    diag = diagnostics if diagnostics is not None else {}
    diag.update(reason="unchanged", candidate_count=0, tested=0, accepted=0)
    if machine_type not in {"Auto", "CNC Router"} or not sources or not plan.get("sheets"):
        diag["reason"] = "unsupported"
        return plan
    if plan.get("unplaced") or len(plan.get("industrial_rank") or ()) != 8:
        diag["reason"] = "incomplete"
        return plan
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        diag["reason"] = "deadline"
        return plan

    source_by_id = {int(s["id"]): s for s in sources}
    locked = _locked_piece_ids(plan)
    eligible = {index: _eligible_ids(sheet, source_by_id, locked)
                for index, sheet in enumerate(plan["sheets"])}
    diag["eligible_pieces"] = sum(len(v) for v in eligible.values())
    diag["protected_pieces"] = sum(len(s.get("pieces") or []) for s in plan["sheets"]) - diag["eligible_pieces"]
    diag["large_sheets_skipped"] = sum(
        len(s.get("pieces") or []) > _MAX_PIECES for s in plan["sheets"]
    )
    if all(len(ids) < 2 for ids in eligible.values()):
        diag["reason"] = "no_eligible_pair"
        return plan
    if validate_plan(plan, sources, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
        diag["reason"] = "invalid_initial"
        return plan

    best = plan
    # A rigid translation affects only one sheet: caching canonical metrics
    # avoids repeatedly rebuilding every other board's cutter-center network.
    sheet_profiles = {
        index: _rectangles({"sheets": [sheet]}, kerf_cm, regular_only=True)
        for index, sheet in enumerate(best["sheets"])
    }
    sheet_axes = {
        index: _axis_alignment_score({"sheets": [sheet]}, kerf_cm,
                                      {0: eligible[index]})
        for index, sheet in enumerate(best["sheets"])
    }
    sheet_remnants: dict[int, float] = {}
    best_profile = (sum(p[0] for p in sheet_profiles.values()),
                    sum(p[1] for p in sheet_profiles.values()))
    best_axis = sum(sheet_axes.values())
    attempts = 0
    for sweep_index in range(_MAX_SWEEPS):
        winner = None
        winner_profile = best_profile
        winner_axis = best_axis
        winner_key = None
        winner_sheet_profile = None
        winner_sheet_axis = None
        winner_sheet_remnant = None
        winner_sheet_index = None
        moves = _candidate_moves(best, kerf_cm, eligible, deadline_monotonic)
        diag["candidate_count"] += len(moves)
        # Reserve part of the existing fixed trial allowance for improvements
        # in subsequent sweeps. If no win is found in the prefix, continue
        # trying candidates up to the existing global cap.
        remaining_sweeps = _MAX_SWEEPS - sweep_index
        round_quota = max(1, math.ceil((_MAX_TRIALS - attempts) / remaining_sweeps))
        round_attempts = 0
        for sheet_index, axis, ids, delta in moves:
            if round_attempts >= round_quota and winner is not None:
                diag["reserved_for_followup"] = diag.get("reserved_for_followup", 0) + 1
                break
            if attempts >= _MAX_TRIALS:
                diag["reason"] = "trial_limit"
                return best
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                diag["reason"] = "deadline"
                return best
            candidate = _translate_if_clear(best, sheet_index, axis, ids, delta, kerf_cm)
            if candidate is None:
                diag["blocked_geometry"] = diag.get("blocked_geometry", 0) + 1
                continue
            attempts += 1
            round_attempts += 1
            diag["tested"] += 1

            # Exact cutter-center network of the changed sheet, plus cached
            # unaffected sheets. This is algebraically equivalent to a full
            # plan recalculation, which remains covered by regression tests.
            candidate_sheet_profile = _rectangles(
                {"sheets": [candidate["sheets"][sheet_index]]},
                kerf_cm, regular_only=True,
            )
            previous_sheet_profile = sheet_profiles[sheet_index]
            profile = (
                best_profile[0] - previous_sheet_profile[0] + candidate_sheet_profile[0],
                best_profile[1] - previous_sheet_profile[1] + candidate_sheet_profile[1],
            )
            same_length = abs(profile[0] - best_profile[0]) <= _NETWORK_EPS_MM
            if profile[0] > best_profile[0] + _NETWORK_EPS_MM or profile[1] > best_profile[1]:
                diag["rejected_network"] = diag.get("rejected_network", 0) + 1
                continue
            candidate_sheet_axis = _axis_alignment_score(
                {"sheets": [candidate["sheets"][sheet_index]]},
                kerf_cm, {0: eligible[sheet_index]},
            )
            alignment = best_axis - sheet_axes[sheet_index] + candidate_sheet_axis
            if same_length and profile[1] == best_profile[1] and alignment <= best_axis:
                diag["rejected_no_improvement"] = diag.get("rejected_no_improvement", 0) + 1
                continue

            if sheet_index not in sheet_remnants:
                sheet_remnants[sheet_index] = _largest_reusable_free_area(
                    {"sheets": [best["sheets"][sheet_index]]},
                    metric_kwargs["min_remnant_width_cm"],
                    metric_kwargs["min_remnant_length_cm"],
                    metric_kwargs["min_remnant_area_m2"],
                    machine_type=machine_type,
                )
            after_remnant = _largest_reusable_free_area(
                {"sheets": [candidate["sheets"][sheet_index]]},
                metric_kwargs["min_remnant_width_cm"],
                metric_kwargs["min_remnant_length_cm"],
                metric_kwargs["min_remnant_area_m2"],
                machine_type=machine_type,
            )
            if after_remnant + 1e-9 < sheet_remnants[sheet_index]:
                diag["rejected_remnant"] = diag.get("rejected_remnant", 0) + 1
                continue
            # Only promising candidates reach the independent FULL-plan
            # manufacturing validators; the final gate is not weakened.
            if validate_plan(candidate, sources, board_w_cm, board_h_cm, kerf_cm=kerf_cm,
                             deadline_monotonic=deadline_monotonic):
                diag["rejected_validation"] = diag.get("rejected_validation", 0) + 1
                continue
            if placement_permission_errors(candidate, sources, mirroring_allowed=mirroring_allowed):
                diag["rejected_permission"] = diag.get("rejected_permission", 0) + 1
                continue
            candidate = enrich_plan_metrics(
                candidate, str(best.get("method_key") or ""), machine_type,
                **metric_kwargs,
            )
            if tuple(candidate["industrial_rank"][:4]) > tuple(best["industrial_rank"][:4]):
                diag["rejected_rank"] = diag.get("rejected_rank", 0) + 1
                continue
            key = (round(profile[0], 5), profile[1], -alignment,
                   abs(delta), sheet_index, axis, ids, delta)
            if winner_key is None or key < winner_key:
                winner, winner_profile, winner_axis, winner_key = (
                    candidate, profile, alignment, key
                )
                winner_sheet_index = sheet_index
                winner_sheet_profile = candidate_sheet_profile
                winner_sheet_axis = candidate_sheet_axis
                winner_sheet_remnant = after_remnant
        if winner is None:
            return best
        best, best_profile, best_axis = winner, winner_profile, winner_axis
        sheet_profiles[winner_sheet_index] = winner_sheet_profile
        sheet_axes[winner_sheet_index] = winner_sheet_axis
        sheet_remnants[winner_sheet_index] = winner_sheet_remnant
        diag["accepted"] += 1
        diag["reason"] = "improved"
    return best
