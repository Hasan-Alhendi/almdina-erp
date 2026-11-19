"""Bounded geometry-aware final System placement, never a packing constraint.

Contacts propose groups; they do not make all touching doors one rigid body.
Only proven regular pieces move. Protected contours remain in the complete
cutter network and manufacturing validation. Compound proposals are atomic.
"""
from __future__ import annotations

import time
from itertools import combinations
from typing import Any

from .cut_line_quality import final_cut_quality_key, sheet_cut_line_quality
from .evaluation import placement_permission_errors, validate_plan
from .final_cut_line_alignment import (
    _MAX_PIECES, _MAX_SWEEPS, _MAX_TRIALS, _axis_alignment_score, _candidate_moves,
    _contact_preserving_groups, _eligible_ids, _groups, _is_movable_regular,
    _movement_range, _projected_axis_gain, _shares_cutter_center, _translate_group_moves_if_clear,
)
from .optimizer import _reusable_free_rectangles_for_sheet, enrich_plan_metrics
from .plan_portfolio import manufacturing_export_rejection
from .plan_search import _locked_piece_ids
from .plan_settings import EdgeProtectionPolicy
from .primitives import num
from .sheet_edge_trim import _occupied_span, _projection_groups, resolved_sheet_trim_cm

_EPS_CM = 1e-7
_NETWORK_TOL_MM = 0.05
_ATTACHED_GEOMETRY_KEYS = (
    "geometry", "overlays", "special_shape_geometry_json", "placement_outline_cm",
    "toolpaths", "cnc_toolpaths", "attached_geometry",
)


def _remnants_preserved(before, after, *, allowances, options):
    """One connected eligible successor per old useful rectangle, less margin strips.

    Maximal free rectangles overlap: total free area or a collection of fragments
    cannot substitute for the connected, factory-eligible successor.
    """
    previous = _reusable_free_rectangles_for_sheet(before, **options)
    current = _reusable_free_rectangles_for_sheet(after, **options)
    for rect in previous:
        required = (rect["w"] * rect["h"] - allowances["x"] * rect["h"]
                    - allowances["y"] * rect["w"])
        if required <= _EPS_CM or not any(
            max(0.0, min(rect["x"] + rect["w"], other["x"] + other["w"])
                - max(rect["x"], other["x"]))
            * max(0.0, min(rect["y"] + rect["h"], other["y"] + other["h"])
                - max(rect["y"], other["y"])) >= required - _EPS_CM
            for other in current
        ):
            return False
    return True


def _movement_groups(sheet, axis, eligible, kerf):
    """Projection hints, real contacts, directional chains and independent pieces.

    Each candidate is rigid internally. A contact with another group is a cut
    relationship to remeasure, not a mandatory mechanical dependency.
    """
    pieces = [p for p in sheet["pieces"] if int(p["id"]) in eligible]
    groups = set(_groups(sheet, axis))
    cross = "y" if axis == "x" else "x"
    groups.update(tuple(sorted(int(p["id"]) for p in group))
                  for group in _projection_groups(pieces, axis=cross))
    groups.update(_contact_preserving_groups(sheet, kerf, eligible))
    groups.add(tuple(sorted(eligible)))
    groups.update(_directional_contact_groups(pieces, axis, kerf))
    return sorted((ids for ids in groups if ids and set(ids).issubset(eligible)),
                  key=lambda ids: (len(ids), ids))


def _directional_contact_groups(pieces, axis, kerf):
    """Chains along the movement axis, independent of staggered T neighbors."""
    size = "w" if axis == "x" else "h"
    neighbors = {int(p["id"]): set() for p in pieces}
    for first, second in combinations(pieces, 2):
        gap = max(num(first[axis])-num(second[axis])-num(second[size]),
                  num(second[axis])-num(first[axis])-num(first[size]))
        if abs(gap-kerf) <= _EPS_CM and _shares_cutter_center(first, second, kerf):
            neighbors[int(first["id"])].add(int(second["id"]))
            neighbors[int(second["id"])].add(int(first["id"]))
    visited, groups = set(), []
    for piece_id in sorted(neighbors):
        if piece_id in visited:
            continue
        stack, members = [piece_id], set()
        while stack:
            current = stack.pop()
            if current not in members:
                members.add(current)
                stack.extend(neighbors[current]-members)
        if len(members) > 1:
            groups.append(tuple(sorted(members)))
        visited.update(members)
    return groups


def _placement_goals(sheet, eligible, policy, threshold, kerf):
    goals = []
    for axis, protection in (("x", policy.horizontal_mm), ("y", policy.vertical_mm)):
        if not protection:
            continue
        trim = resolved_sheet_trim_cm(sheet, axis=axis)
        frame = num(sheet["w" if axis == "x" else "h"])
        full = num(sheet.get("full_width_cm" if axis == "x" else "full_length_cm"))
        if frame <= 0 or abs(full-2*trim-frame) > _EPS_CM:
            continue
        for ids in _movement_groups(sheet, axis, eligible, kerf):
            members = [p for p in sheet["pieces"] if int(p["id"]) in ids]
            start, end = _occupied_span(members, axis)
            slack = max(0.0, frame-(end-start))
            centerable = max(start, frame-end) <= threshold+_EPS_CM
            target = max(0.0, protection/10-trim)
            goals.append((axis, ids, frame, target, centerable, slack/2))
    return goals


def _placement_score(sheet, goals, deltas=None):
    """Subgroup protection debt per axis, then eligible centering error."""
    deltas = deltas or {}
    debt, centering = {"x": 0.0, "y": 0.0}, 0.0
    by_id = {int(p["id"]): p for p in sheet["pieces"]}
    for axis, ids, frame, target, centerable, center in goals:
        size = "w" if axis == "x" else "h"
        start = min(num(by_id[i][axis])+deltas.get((i, axis), 0) for i in ids)
        end = max(num(by_id[i][axis])+num(by_id[i][size])+deltas.get((i, axis), 0) for i in ids)
        center = max(0.0, frame-(end-start))/2
        if centerable:
            target = min(target, center)
        debt[axis] += max(0.0, target-start)+max(0.0, target-(frame-end))
        if centerable:
            centering += abs(start-center)
    return tuple(round(debt[a], 6) for a in ("x", "y")), round(centering, 6)


def _move_deltas(moves):
    result = {}
    for axis, ids, delta in moves:
        for piece_id in ids:
            if (piece_id, axis) in result:
                return None
            result[piece_id, axis] = delta
    return result


def _proposals(plan, index, eligible, goals, kerf, deadline, align_cut_lines, anchor_positions):
    sheet = plan["sheets"][index]
    by_id = {int(p["id"]): p for p in sheet["pieces"]}
    events = set()
    for axis, ids, frame, target, centerable, center in goals:
        if deadline is not None and time.monotonic() >= deadline:
            return []
        members = [by_id[i] for i in ids]
        start, end = _occupied_span(members, axis)
        center = max(0.0, frame-(end-start))/2
        if centerable:
            target = min(target, center)
        lower, upper = target-start, frame-target-end
        if lower > upper+_EPS_CM:
            continue
        shifts = [min(max(0.0, lower), upper)]
        if centerable:
            shifts.extend((center-start, lower, upper))
        fixed = [p for p in sheet["pieces"] if int(p["id"]) not in ids]
        interval = _movement_range(members, fixed, sheet, axis, kerf)
        for shift in shifts:
            if abs(shift) > _EPS_CM:
                events.add((axis, ids, round(shift, 6)))
                # Retain blocked targets for coupled trials; also try the
                # reachable endpoint, rather than treating all slack as usable.
                if interval is not None:
                    clipped = min(max(shift, interval[0]), interval[1])
                    if abs(clipped) > _EPS_CM:
                        events.add((axis, ids, round(clipped, 6)))
    if align_cut_lines:
        events.update((axis, ids, delta) for _, axis, ids, delta in
                      _candidate_moves(plan, kerf, {index: eligible}, deadline))
    gains = {move: _projected_axis_gain(sheet, *move, kerf, eligible) for move in events}
    def order(moves):
        deltas = _move_deltas(moves)
        debt, center = _placement_score(sheet, goals, deltas)
        motion = sum(abs(num(by_id[i][a])+deltas.get((i,a),0)-position)
                     for (a,i),position in anchor_positions.items())
        return (round(sum(debt), 6), -sum(gains[m] for m in moves), round(motion,6), center,
                -sum(len(m[1]) for m in moves), moves)
    singles = sorted(((move,) for move in events), key=order)[:_MAX_TRIALS]
    # Reserve independent and coupled exploration within the existing caps.
    pairs = [(a[0], b[0]) for a, b in combinations(singles[:_MAX_TRIALS//2], 2)
             if _move_deltas((a[0], b[0])) is not None]
    pairs.sort(key=order)
    return singles, pairs[:_MAX_TRIALS]


def protect_plan_edges(
    plan: dict[str, Any], sources: list[dict[str, Any]],
    width_cm: float, length_cm: float, kerf_cm: float, *,
    policy: EdgeProtectionPolicy, max_centerable_edge_gap_cm: float,
    machine_type: str, mirroring_allowed: bool, metric_options: dict[str, Any],
    deadline_monotonic: float | None = None, align_cut_lines: bool = True,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Best proven atomic final placement; disabled policy is an exact no-op.

    Complete canonical cutter length includes every offset finished edge, even
    outside a zero-trim board. Moving inside can add *internal* cutting without
    increasing this full network. An increased full union instead loses shared
    cutting: individual perimeter lengths are unchanged by these translations.
    """
    if not (policy.horizontal_mm or policy.vertical_mm):
        return plan, []
    diag = diagnostics if diagnostics is not None else {}
    diag.update(tested=0, accepted=0, rejected={}, sheets=[])
    decisions, best = [], plan
    options = {**metric_options, "machine_type": machine_type}
    by_id, locked = {int(p["id"]): p for p in sources}, _locked_piece_ids(plan)
    def reject(reason):
        diag["rejected"][reason] = diag["rejected"].get(reason, 0)+1
    for index, original in enumerate(plan.get("sheets") or []):
        records = {}
        for axis, protection in (("x", policy.horizontal_mm), ("y", policy.vertical_mm)):
            if protection:
                records[axis] = dict(sheet_no=original.get("sheet_no", index+1), axis=axis,
                                     reason="UNSAFE_MOVE", shift_mm=0.0)
                decisions.append(records[axis])
        placed = {int(p["id"]): p for p in original.get("pieces") or []}
        eligible = {i for i in _eligible_ids(original, by_id, locked)
                    if _is_movable_regular({**placed[i], **by_id[i]})
                    and not any(by_id[i].get(k) or placed[i].get(k) for k in _ATTACHED_GEOMETRY_KEYS)}
        if (machine_type not in {"Auto", "CNC Router"} or not eligible
                or any(owner.get(k) for owner in (plan, original) for k in _ATTACHED_GEOMETRY_KEYS)):
            detail = "piece_limit" if len(placed) > _MAX_PIECES else "protected_geometry"
            for record in records.values():
                record["detail"] = detail
            continue
        if diag["tested"] >= _MAX_TRIALS or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic):
            for record in records.values():
                record["detail"] = "trial_budget" if diag["tested"] >= _MAX_TRIALS else "time_budget"
            continue
        goals = _placement_goals(original, eligible, policy, max_centerable_edge_gap_cm, kerf_cm)
        before = sheet_cut_line_quality(original, kerf_cm)
        if before is None or not goals:
            for record in records.values():
                record["detail"] = "cut_line_quality" if before is None else "physical_frame"
            continue
        if (validate_plan(best, sources, width_cm, length_cm, kerf_cm=kerf_cm)
                or placement_permission_errors(best, sources, mirroring_allowed=mirroring_allowed)
                or manufacturing_export_rejection(best)):
            continue
        chains = {axis: set(_directional_contact_groups([placed[i] for i in eligible], axis, kerf_cm))
                  for axis in ("x", "y")}
        centerable_members = {(g[0], i) for g in goals if g[4] and g[1] in chains[g[0]] for i in g[1]}
        anchors = [(g[0], g[1][0]) for g in goals if len(g[1]) == 1 and not g[4]
                   and (g[0], g[1][0]) not in centerable_members]
        anchor_positions = {(axis, i): num(placed[i][axis]) for axis, i in anchors}
        def key(candidate, profile):
            debt, center = _placement_score(candidate["sheets"][index], goals)
            current = {int(p["id"]): p for p in candidate["sheets"][index]["pieces"]}
            # Preserve large remnants with minimum displacement; moving an
            # independent anchor further needs a real cut or alignment gain.
            anchor_motion = sum(abs(num(current[i][a])-num(placed[i][a])) for a, i in anchors)
            return (round(sum(debt), 6), final_cut_quality_key(profile),
                    -_axis_alignment_score(candidate, kerf_cm, {index: eligible}),
                    round(anchor_motion, 6), center)
        best_key, accepted_moves, tested = key(best, before), [], 0
        # Fair remaining shares, like the gallery budget: one intricate board
        # must not consume every trial before the next board is considered.
        sheet_limit = diag["tested"] + max(1, (_MAX_TRIALS-diag["tested"])//
                                          max(1, len(plan["sheets"])-index))
        for _ in range(_MAX_SWEEPS):
            if diag["tested"] >= sheet_limit or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic):
                break
            pools = _proposals(best, index, eligible, goals, kerf_cm, deadline_monotonic,
                               align_cut_lines, anchor_positions)
            if not pools:
                break
            current_debt = _placement_score(best["sheets"][index], goals)[0]
            winner, winner_key, winner_moves = None, best_key, None
            for pool in pools:
                spent = 0
                for moves in pool:
                    if (diag["tested"] >= sheet_limit or spent >= _MAX_TRIALS//_MAX_SWEEPS//2
                            or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic)):
                        break
                    candidate = _translate_group_moves_if_clear(best, index, moves, kerf_cm, check_swept=True)
                    if candidate is None:
                        reject("bounds_kerf_or_swept_clearance")
                        continue
                    tested += 1
                    spent += 1
                    diag["tested"] += 1
                    moved = candidate["sheets"][index]
                    debt = _placement_score(moved, goals)[0]
                    if any(a > b+_EPS_CM for a, b in zip(debt, current_debt)):
                        reject("other_axis_protection")
                        continue
                    after = sheet_cut_line_quality(moved, kerf_cm)
                    if (after is None or after[0] > before[0]+_NETWORK_TOL_MM
                            or (abs(after[0]-before[0]) <= _NETWORK_TOL_MM
                                and after[2]+_NETWORK_TOL_MM < before[2])):
                        reject("shared_cutter_network")
                        continue
                    candidate_key = key(candidate, after)
                    if candidate_key >= winner_key:
                        reject("no_improvement")
                        continue
                    # Bound free-area loss by policy inset or eligible centering,
                    # never by an arbitrary alignment jump.
                    allowances = {}
                    for axis in ("x", "y"):
                        cap = max((max(g[3], g[5] if g[4] else 0) for g in goals if g[0] == axis), default=0)
                        distance = max((abs(num(p[axis])-num(placed[int(p["id"])][axis]))
                                        for p in moved["pieces"]), default=0)
                        allowances[axis] = min(distance, cap)
                    if not _remnants_preserved(original, moved, allowances=allowances, options=options):
                        reject("useful_remnant")
                        for axis, _, _ in moves:
                            if axis in records:
                                records[axis].update(reason="REMNANT_PRESERVED", detail="useful_remnant")
                        continue
                    if (validate_plan(candidate, sources, width_cm, length_cm, kerf_cm=kerf_cm)
                            or placement_permission_errors(candidate, sources, mirroring_allowed=mirroring_allowed)
                            or manufacturing_export_rejection(candidate)):
                        reject("manufacturing_validation")
                        continue
                    winner, winner_key, winner_moves = candidate, candidate_key, moves
            if winner is None:
                break
            best = enrich_plan_metrics(winner, str(plan.get("method_key") or ""), **options)
            best_key = winner_key
            accepted_moves.extend(winner_moves)
            diag["accepted"] += 1
        for axis, _, _ in accepted_moves:
            if axis not in records:
                records[axis] = dict(sheet_no=original.get("sheet_no", index+1), axis=axis,
                                     reason="ALIGNED", shift_mm=0.0)
                decisions.append(records[axis])
        # Report net displacements, never intermediate trials or hypothetical safety.
        for axis, record in records.items():
            net = {}
            for moved_axis, ids, delta in accepted_moves:
                if moved_axis == axis:
                    for piece_id in ids:
                        net[piece_id] = net.get(piece_id, 0)+delta
            net = {i: round(d*10, 6) for i, d in net.items() if abs(d) > _EPS_CM}
            if net:
                record.update(reason="ALIGNED" if record["reason"] == "ALIGNED" else "EDGE_PROTECTED",
                              piece_shifts_mm=net,
                              shift_mm=next(iter(net.values())) if len(set(net.values())) == 1 else 0.0)
                record.pop("detail", None)
            elif record["reason"] != "REMNANT_PRESERVED":
                axis_goals = [g for g in goals if g[0] == axis]
                debt, center = _placement_score(best["sheets"][index], axis_goals)
                if sum(debt) <= _EPS_CM:
                    centered = any(g[4] for g in axis_goals) and center <= _EPS_CM
                    record["reason"] = "CENTERED" if centered else "ALREADY_PROTECTED"
        diag["sheets"].append(dict(sheet_no=original.get("sheet_no", index+1), before=before,
                                   after=sheet_cut_line_quality(best["sheets"][index], kerf_cm), tested=tested))
    return best, decisions
