"""Bounded geometry-aware final System placement, never a packing constraint.

Contacts propose groups; they do not make all touching doors one rigid body.
Only proven regular pieces move. Protected contours remain in the complete
cutter network and manufacturing validation. Compound proposals are atomic.
"""
from __future__ import annotations

import time
from time import perf_counter
from itertools import combinations
from typing import Any

from .cut_line_quality import final_cut_quality_key, sheet_cut_line_quality
from .evaluation import placement_permission_errors, validate_plan
from .final_cut_line_alignment import (
    _MAX_PIECES, _MAX_SWEEPS, _MAX_TRIALS, _axis_alignment_score, _candidate_moves,
    _contact_preserving_groups, _eligible_ids, _groups, _is_movable_regular,
    _movement_range, _projected_axis_gain, _shares_cutter_center, _translate_group_moves_if_clear,
    _BaselineProof, _translation_validation_scope,
)
from .optimizer import _reusable_free_rectangles_for_sheet, enrich_plan_metrics
from .plan_portfolio import manufacturing_export_rejection
from .plan_search import _locked_piece_ids
from .plan_settings import EdgeProtectionPolicy
from .primitives import num
from .sheet_edge_trim import (
    _occupied_span, _projection_groups, physical_edge_margins_mm, resolved_sheet_trim_cm,
)

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


def _policy_events(sheet, goals, kerf, deadline):
    """Bounded policy endpoints; no matching-edge generation or pair ranking."""
    by_id = {int(p["id"]): p for p in sheet["pieces"]}
    events = set()
    counts = {"x":0,"y":0}
    for axis, ids, frame, target, centerable, center in sorted(goals,key=lambda g:(-len(g[1]),g)):
        if deadline is not None and time.monotonic() >= deadline:
            break
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
            if abs(shift) > _EPS_CM and counts[axis] < _MAX_TRIALS//2:
                event = (axis,ids,round(shift,6))
                if event not in events:
                    events.add(event)
                    counts[axis] += 1
                # Retain blocked targets for coupled trials; also try the
                # reachable endpoint, rather than treating all slack as usable.
                if interval is not None:
                    clipped = min(max(shift, interval[0]), interval[1])
                    event = (axis,ids,round(clipped,6))
                    if abs(clipped) > _EPS_CM and event not in events and counts[axis] < _MAX_TRIALS//2:
                        events.add(event)
                        counts[axis] += 1
    return events


def _proposals(plan, index, eligible, goals, kerf, deadline, align_cut_lines, anchor_positions, diagnostics=None):
    sheet = plan["sheets"][index]
    by_id = {int(p["id"]): p for p in sheet["pieces"]}
    events = (_timed(diagnostics,"policy_events",_policy_events,sheet,goals,kerf,deadline)
              if diagnostics is not None else _policy_events(sheet,goals,kerf,deadline))
    if align_cut_lines and (deadline is None or time.monotonic() < deadline):
        generation_started = perf_counter()
        events.update((axis, ids, delta) for _, axis, ids, delta in
                      _candidate_moves(plan, kerf, {index: eligible}, deadline, max_events=_MAX_TRIALS))
        if diagnostics is not None:
            diagnostics["seconds"]["alignment_events"] = diagnostics["seconds"].get("alignment_events",0)+perf_counter()-generation_started
    # Screen policy events before expensive pair scoring. This bound applies
    # only to positive protection; the zero-policy legacy search is untouched.
    events = sorted(events, key=lambda m: (-len(m[1]), abs(m[2]), m))[:_MAX_TRIALS]
    scoring_started, gains = perf_counter(), {}
    for move in events:
        if deadline is not None and time.monotonic() >= deadline:
            break
        gains[move] = _projected_axis_gain(sheet, *move, kerf, eligible)
    events = list(gains)
    if diagnostics is not None:
        diagnostics["seconds"]["event_score"] = diagnostics["seconds"].get("event_score",0)+perf_counter()-scoring_started
    def order(moves):
        deltas = _move_deltas(moves)
        debt, center = _placement_score(sheet, goals, deltas)
        motion = sum(abs(num(by_id[i][a])+deltas.get((i,a),0)-position)
                     for (a,i),position in anchor_positions.items())
        return (round(sum(debt), 6), -sum(gains[m] for m in moves), round(motion,6), center,
                -sum(len(m[1]) for m in moves), moves)
    sorting_started = perf_counter()
    def ranked(proposals):
        scored = []
        for moves in proposals:
            if _expired(deadline):
                break
            scored.append((order(moves),moves))
        return [moves for _,moves in sorted(scored)[:_MAX_TRIALS]]
    singles = ranked((move,) for move in events)
    # Reserve independent and coupled exploration within the existing caps.
    pairs = [(a[0], b[0]) for a, b in combinations(singles[:_MAX_TRIALS//2], 2)
             if _move_deltas((a[0], b[0])) is not None]
    pairs = ranked(pairs)
    if diagnostics is not None:
        diagnostics["seconds"]["sorting"] = diagnostics["seconds"].get("sorting",0)+perf_counter()-sorting_started
        diagnostics["generated"] = diagnostics.get("generated",0)+len(singles)+len(pairs)
    return singles,pairs



def _timed(diag, stage, function, *args, **kwargs):
    started = perf_counter()
    try:
        return function(*args, **kwargs)
    finally:
        elapsed = perf_counter()-started
        diag["seconds"][stage] = diag["seconds"].get(stage, 0.0)+elapsed
        diag["calls"][stage] = diag["calls"].get(stage,0)+1
        index = diag.get("_active_sheet_index")
        if index is not None:
            seconds = diag["sheets"][index]["seconds"]
            seconds[stage] = seconds.get(stage,0.0)+elapsed


def _expired(deadline):
    return deadline is not None and time.monotonic() >= deadline


class _SheetSearch:
    """One board's cached search state; safety gates are shared by both passes."""

    def __init__(self, index, sheet, eligible, goals, kerf, diag):
        self.index, self.original, self.eligible, self.goals = index, sheet, eligible, goals
        self.placed = {int(p["id"]): p for p in sheet["pieces"]}
        self.kerf, self.diag = kerf, diag
        self.before = None
        self.current_profile = None
        self.time_limited = False
        self.seen, self.accepted_moves = set(), []
        self.axes = {axis: dict(attempted=0, rejected={}, accepted=0) for axis in ("x", "y")}
        chains = {axis: set(_directional_contact_groups([self.placed[i] for i in eligible], axis, kerf))
                  for axis in ("x", "y")}
        centered = {(g[0], i) for g in goals if g[4] and g[1] in chains[g[0]] for i in g[1]}
        self.anchors = {(g[0], g[1][0]): num(self.placed[g[1][0]][g[0]])
                        for g in goals if len(g[1]) == 1 and not g[4] and (g[0], g[1][0]) not in centered}

    def key(self, plan, profile):
        sheet = plan["sheets"][self.index]
        debt, center = _placement_score(sheet, self.goals)
        current = {int(p["id"]): p for p in sheet["pieces"]}
        motion = sum(abs(num(current[i][a])-position) for (a,i),position in self.anchors.items())
        return (round(sum(debt),6), final_cut_quality_key(profile),
                -_axis_alignment_score(plan,self.kerf,{self.index:self.eligible}), round(motion,6),center)

    def reject(self, moves, reason):
        rejected = self.diag["rejected"]
        rejected[reason] = rejected.get(reason,0)+1
        for axis in {m[0] for m in moves}:
            counts = self.axes[axis]["rejected"]
            counts[reason] = counts.get(reason,0)+1

    def basic(self, plan, deadline):
        events = _policy_events(plan["sheets"][self.index],self.goals,self.kerf,deadline)
        def order(moves):
            deltas = _move_deltas(moves)
            sheet = plan["sheets"][self.index]
            by_id = {int(p["id"]):p for p in sheet["pieces"]}
            debt,center = _placement_score(sheet,self.goals,deltas)
            motion = sum(abs(num(by_id[i][a])+deltas.get((i,a),0)-position)
                         for (a,i),position in self.anchors.items())
            return (round(sum(debt),6),round(motion,6),center,-sum(len(m[1]) for m in moves),moves)
        singles = sorted(((m,) for m in events),key=order)
        first = {axis: next((m[0] for m in singles if m[0][0] == axis),None) for axis in ("x","y")}
        joint = tuple(m for m in first.values() if m is not None)
        # Try one atomic X/Y protection event before arbitrary alignment or
        # unequal-group combinations. Failed rectangle prechecks may fall back.
        return (([joint] if len(joint)>1 else [])+singles)[:_MAX_TRIALS]

    def trial(self, best, moves, sources, width, height, options, mirroring):
        signature = (tuple((p["id"],p["x"],p["y"]) for p in best["sheets"][self.index]["pieces"]),moves)
        if signature in self.seen:
            return None
        self.seen.add(signature)
        for axis in {m[0] for m in moves}:
            self.axes[axis]["attempted"] += 1
        candidate = _timed(self.diag,"translation",_translate_group_moves_if_clear,
                           best,self.index,moves,self.kerf,check_swept=True)
        if candidate is None:
            self.reject(moves,"bounds_kerf_or_swept_clearance")
            return None
        self.diag["tested"] += 1
        self.diag["sheets"][self.index]["tested"] += 1
        moved = candidate["sheets"][self.index]
        debt = _placement_score(moved,self.goals)[0]
        current_debt = _placement_score(best["sheets"][self.index],self.goals)[0]
        if any(a>b+_EPS_CM for a,b in zip(debt,current_debt)):
            self.reject(moves,"other_axis_protection")
            return None
        after = _timed(self.diag,"cutter",sheet_cut_line_quality,moved,self.kerf)
        if (after is None or after[0]>self.before[0]+_NETWORK_TOL_MM
                or (abs(after[0]-self.before[0])<=_NETWORK_TOL_MM and after[2]+_NETWORK_TOL_MM<self.before[2])):
            self.reject(moves,"shared_cutter_network")
            return None
        if self.key(candidate,after)>=self.key(best,self.current_profile):
            self.reject(moves,"no_improvement")
            return None
        allowances = {}
        for axis in ("x","y"):
            cap = max((max(g[3],g[5] if g[4] else 0) for g in self.goals if g[0]==axis),default=0)
            distance = max(abs(num(p[axis])-num(self.placed[int(p["id"])][axis])) for p in moved["pieces"])
            allowances[axis] = min(distance,cap)
        if not _timed(self.diag,"remnants",_remnants_preserved,self.original,moved,
                      allowances=allowances,options=options):
            self.reject(moves,"useful_remnant")
            return None
        # The complete baseline was proved once. Reuse only byte-for-byte
        # unchanged boards and identical source identities, as legacy alignment
        # does. The final Application adapter still validates the entire plan.
        scope, scoped_sources, _ = _translation_validation_scope(candidate,best,sources,self.index)
        if (_timed(self.diag,"geometry",validate_plan,scope,scoped_sources,width,height,kerf_cm=self.kerf)
                or _timed(self.diag,"permissions",placement_permission_errors,scope,scoped_sources,
                          mirroring_allowed=mirroring)
                or _timed(self.diag,"export_check",manufacturing_export_rejection,scope)):
            self.reject(moves,"manufacturing_validation")
            return None
        self.accepted_moves.extend(moves)
        self.current_profile = after
        self.diag["accepted"] += 1
        self.diag["sheets"][self.index]["accepted"] += 1
        for axis in {m[0] for m in moves}:
            self.axes[axis]["accepted"] += 1
        return candidate


def protect_plan_edges(
    plan: dict[str, Any], sources: list[dict[str, Any]],
    width_cm: float, length_cm: float, kerf_cm: float, *,
    policy: EdgeProtectionPolicy, max_centerable_edge_gap_cm: float,
    machine_type: str, mirroring_allowed: bool, metric_options: dict[str, Any],
    deadline_monotonic: float | None = None, align_cut_lines: bool = True,
    diagnostics: dict[str, Any] | None = None, baseline_proof: _BaselineProof | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Cover boards with basic protection before bounded round-robin refinement.

    All phases use the caller's existing absolute deadline and 24 expensive
    trials. No new budget is created here. Atomic validation may finish after
    its slice; never discard its completed safe result or start another trial.
    """
    if not (policy.horizontal_mm or policy.vertical_mm):
        return plan, []
    started = perf_counter()
    diag = diagnostics if diagnostics is not None else {}
    diag.update(tested=0,accepted=0,rejected={},sheets=[],seconds={},calls={})
    best, decisions, states = plan, [], []
    options = {**metric_options,"machine_type":machine_type}
    by_id,locked = {int(p["id"]):p for p in sources},_locked_piece_ids(plan)
    records_by_sheet = []
    for index,sheet in enumerate(plan.get("sheets") or []):
        records = {a:dict(sheet_no=sheet.get("sheet_no",index+1),axis=a,
                         reason="NOT_EVALUATED_TIME_BUDGET",shift_mm=0.0)
                   for a,p in (("x",policy.horizontal_mm),("y",policy.vertical_mm)) if p}
        records_by_sheet.append(records)
        decisions.extend(records.values())
        diag["sheets"].append(dict(sheet_no=sheet.get("sheet_no",index+1),tested=0,accepted=0,seconds={}))
        placed = {int(p["id"]):p for p in sheet.get("pieces") or []}
        eligible = {i for i in _eligible_ids(sheet,by_id,locked)
                    if _is_movable_regular({**placed[i],**by_id[i]}) and not any(
                        by_id[i].get(k) or placed[i].get(k) for k in _ATTACHED_GEOMETRY_KEYS)}
        detail = None
        if (machine_type not in {"Auto","CNC Router"} or not eligible
                or any(owner.get(k) for owner in (plan,sheet) for k in _ATTACHED_GEOMETRY_KEYS)):
            detail = "piece_limit" if len(placed)>_MAX_PIECES else "protected_geometry"
        if detail:
            for record in records.values():
                record.update(reason="GEOMETRY_REJECTED",detail=detail)
        else:
            states.append((index,sheet,eligible))
    proof_matches = isinstance(baseline_proof,_BaselineProof) and baseline_proof.matches(
        plan,sources,width_cm,length_cm,kerf_cm,mirroring_allowed)
    diag["baseline_validation_reused"] = proof_matches
    if states and not _expired(deadline_monotonic) and _timed(diag,"export_check",manufacturing_export_rejection,plan):
        for records in records_by_sheet:
            for record in records.values():
                record.update(reason="GEOMETRY_REJECTED",detail="manufacturing_export")
        diag["elapsed_sec"] = perf_counter()-started
        return plan,decisions
    if states and not _expired(deadline_monotonic) and not proof_matches:
        if (_timed(diag,"baseline_geometry",validate_plan,plan,sources,width_cm,length_cm,kerf_cm=kerf_cm)
                or _timed(diag,"permissions",placement_permission_errors,plan,sources,mirroring_allowed=mirroring_allowed)):
            for records in records_by_sheet:
                for record in records.values():
                    record.update(reason="GEOMETRY_REJECTED",detail="baseline_validation")
            return plan,decisions
    searches = []
    # A fair share of the remaining time funds each board's cheap first pass;
    # unused capacity returns to later boards/refinement. No alignment-event
    # generator can run until the last board has had this first opportunity.
    basic_deadline = deadline_monotonic
    for position,(index,sheet,eligible) in enumerate(states):
        if _expired(basic_deadline) or diag["tested"]>=_MAX_TRIALS:
            continue
        local_deadline = (time.monotonic()+max(0,basic_deadline-time.monotonic())/(len(states)-position)
                          if basic_deadline is not None else None)
        diag["_active_sheet_index"] = index
        goals = _timed(diag,"groups",_placement_goals,sheet,eligible,policy,max_centerable_edge_gap_cm,kerf_cm)
        if _expired(local_deadline):
            continue
        search = _SheetSearch(index,sheet,eligible,goals,kerf_cm,diag)
        searches.append(search)
        search.before = _timed(diag,"cutter",sheet_cut_line_quality,sheet,kerf_cm)
        search.current_profile = search.before
        if search.before is None or not goals:
            for record in records_by_sheet[index].values():
                record.update(reason="GEOMETRY_REJECTED",detail="cut_line_quality" if search.before is None else "physical_frame")
            continue
        count_before = diag["tested"]
        proposals = _timed(diag,"basic_generation",search.basic,best,local_deadline)
        for moves in proposals:
            if _expired(local_deadline) or diag["tested"]>=_MAX_TRIALS or diag["tested"]>count_before:
                break
            candidate = search.trial(best,moves,sources,width_cm,length_cm,options,mirroring_allowed)
            if candidate is not None:
                best = candidate
        search.time_limited = _expired(local_deadline)
    active = [s for s in searches if s.before is not None and s.goals]
    for sweep in range(_MAX_SWEEPS):
        if _expired(deadline_monotonic) or diag["tested"]>=_MAX_TRIALS:
            break
        for position,search in enumerate(active):
            if _expired(deadline_monotonic) or diag["tested"]>=_MAX_TRIALS:
                break
            # One fair slice and one expensive trial per board per round.
            local_deadline = (time.monotonic()+max(0,deadline_monotonic-time.monotonic())/(len(active)-position)
                              if deadline_monotonic is not None else None)
            diag["_active_sheet_index"] = search.index
            pools = _timed(diag,"generation_sort",_proposals,best,search.index,search.eligible,search.goals,
                           kerf_cm,local_deadline,align_cut_lines,search.anchors,diag)
            count_before = diag["tested"]
            # Alternate single/compound first, retaining both search directions.
            for pool in (pools if sweep%2 else reversed(pools)):
                for moves in pool:
                    if _expired(local_deadline) or diag["tested"]>=_MAX_TRIALS or diag["tested"]>count_before:
                        break
                    candidate = search.trial(best,moves,sources,width_cm,length_cm,options,mirroring_allowed)
                    if candidate is not None:
                        best = candidate
            search.time_limited |= _expired(local_deadline)
    diag.pop("_active_sheet_index",None)
    if best is not plan:
        best = _timed(diag,"metrics",enrich_plan_metrics,best,str(plan.get("method_key") or ""),**options)
    for search in searches:
        records = records_by_sheet[search.index]
        for axis,counts in search.axes.items():
            net = {}
            for moved_axis,ids,delta in search.accepted_moves:
                if moved_axis==axis:
                    for piece_id in ids:
                        net[piece_id] = net.get(piece_id,0)+delta
            net = {i:round(d*10,6) for i,d in net.items() if abs(d)>_EPS_CM}
            if axis not in records and net:
                records[axis] = dict(sheet_no=search.original.get("sheet_no",search.index+1),axis=axis,
                                     reason="ALIGNED",shift_mm=0.0)
                decisions.append(records[axis])
            if axis not in records:
                continue
            record = records[axis]
            record.update(attempted=counts["attempted"],rejected=counts["rejected"])
            record["search_status"] = ("TRIAL_BUDGET" if diag["tested"]>=_MAX_TRIALS
                                       else "NOT_EVALUATED_TIME_BUDGET" if search.time_limited or _expired(deadline_monotonic)
                                       else "COMPLETE")
            if net:
                record.update(reason="ALIGNED" if record["reason"]=="ALIGNED" else "EDGE_PROTECTED",
                    piece_shifts_mm=net,shift_mm=next(iter(net.values())) if len(set(net.values()))==1 else 0.0)
                continue
            if record["reason"]=="GEOMETRY_REJECTED":
                continue
            axis_goals = [g for g in search.goals if g[0]==axis]
            debt,center = _placement_score(best["sheets"][search.index],axis_goals)
            if axis_goals and sum(debt)<=_EPS_CM:
                record["reason"] = "CENTERED" if any(g[4] for g in axis_goals) and center<=_EPS_CM else "ALREADY_PROTECTED"
            elif counts["attempted"]:
                if "useful_remnant" in counts["rejected"]:
                    record.update(reason="REMNANT_PRESERVED",detail="useful_remnant")
                else:
                    record["reason"] = "NO_IMPROVEMENT" if "no_improvement" in counts["rejected"] else "GEOMETRY_REJECTED"
                    record["detail"] = max(counts["rejected"],key=counts["rejected"].get) if counts["rejected"] else "no_admissible_event"
            elif diag["tested"]>=_MAX_TRIALS:
                record["reason"] = "TRIAL_BUDGET"
            else:
                impossible = any(g[3]>g[5]+_EPS_CM and not g[4] for g in axis_goals)
                record["reason"] = ("NOT_EVALUATED_TIME_BUDGET" if search.time_limited or _expired(deadline_monotonic)
                                    else "GEOMETRY_REJECTED" if impossible else "NO_IMPROVEMENT")
                if impossible:
                    record["detail"] = "protection_interval"
        diag["sheets"][search.index]["before"] = search.before
        diag["sheets"][search.index]["after"] = search.current_profile
    for records in records_by_sheet:
        for record in records.values():
            if record["reason"]=="NOT_EVALUATED_TIME_BUDGET" and diag["tested"]>=_MAX_TRIALS:
                record["reason"] = "TRIAL_BUDGET"
    diag["elapsed_sec"] = perf_counter()-started
    diag["trials_rejected"] = diag["tested"]-diag["accepted"]
    diag["sheets_reached"] = sum(s["tested"]>0 for s in diag["sheets"])
    for index,entry in enumerate(diag["sheets"]):
        entry["margins_mm"] = physical_edge_margins_mm(best["sheets"][index])
    return best,decisions
