"""Bounded pair repair with a private fragmentation objective.

Only ordinary, independent source instances move. Shape/nesting/machining
placements remain pinned. Search states may regress; only checked completed
improvements leave this module. No reference layout or additional stock enters.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import time

from .fragmentation import (envelope_profile, fragmentation_key,
    has_fragmentation_benefit, has_complete_identity, fragmentation_export_rejection)
from .same_count_layout_search import (_movable_sources, _remove, _repair,
    _valid, material_signature)

VARIANTS = (("area_desc", "best_short_side"),
            ("long_side_desc", "contact_point"),
            ("width_desc", "best_area"), ("length_desc", "bottom_left"))


def _plain(plan):
    # Never recursively copy stored galleries into private search states.
    return deepcopy({k: v for k, v in plan.items() if not k.startswith("smart_")})


def _pairs(plan, moving, kerf):
    pairs = []
    for a, b in combinations(range(len(plan["sheets"])), 2):
        sheets = [plan["sheets"][i] for i in (a, b)]
        ids = {p["id"] for s in sheets for p in s["pieces"] if p["id"] in moving}
        if not 2 <= len(ids) <= 48:
            continue
        profile = envelope_profile(dict(sheets=sheets), kerf)
        if profile is not None:
            pairs.append((-profile["levels"][0]["secondary_area_cm2"], a, b, ids))
    # Covers fragmented sheets first; pair variants are interleaved so a single
    # pair cannot consume the search. Regenerate after each accepted move.
    return sorted(pairs, key=lambda p: p[:3])[:24]


def search_fragmentation(seeds, sources, width, height, kerf, *, deadline,
                         machine_type, mirroring_allowed, metric_kwargs):
    """At most 96 repairs, eight passes, 24 diagnostic events, one alternative.

    A stalled pass can traverse its best distinct non-improving repair. This
    avoids imposing the native largest-remnant hill climb on the private path.
    Construction uses the existing kerf-aware MaxRects repair; the final whole
    plan still passes identity, geometry, permissions and export checks.
    """
    trace = dict(attempts=0, cap=96, passes=0, improvements=0,
                 exploratory_steps=0, rejections={}, events=[], event_cap=24,
                 pair_cap=24, active_pairs_per_pass=6, removed_cap=48, pass_cap=8)
    started = time.monotonic()
    if time.monotonic() >= deadline:
        trace["stop"] = "expired"
        return None, trace
    if (machine_type not in {"Auto", "CNC Router"} or not sources
            or any((p.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD" for p in sources)):
        trace["stop"] = "unsupported_cohort"
        return None, trace
    def reject(reason):
        trace["rejections"][reason] = trace["rejections"].get(reason, 0) + 1
        if len(trace["events"]) < 24:
            trace["events"].append(dict(attempt=trace["attempts"], result=reason))

    candidates = []
    for seed in seeds[:2]:
        plan = _plain(seed)
        profile = envelope_profile(plan, kerf)
        rejection = fragmentation_export_rejection(plan)
        if (profile is not None and has_complete_identity(plan, sources)
                and rejection in {None, "unproven_machining_parameters"}):
            candidates.append((plan, profile))
    if not candidates:
        trace["stop"] = "unsupported_cohort"
        return None, trace
    def key(item):
        return len(item[0]["sheets"]), fragmentation_key(item[1])
    best, original = min(candidates, key=key), min(candidates, key=key)
    trace["initial_proxy"] = original[1]
    current = best[0]
    movable = _movable_sources(current, sources, kerf)
    moving = {p["id"] for p in movable}
    pinned = {p["id"]: (i, p) for i, s in enumerate(current["sheets"])
              for p in s["pieces"] if p["id"] not in moving}
    trace.update(movable_pieces=len(movable), pinned_pieces=len(pinned))
    seen = {material_signature(current)}
    # Keep a quarter of this same allowance for atomic whole-plan validation.
    search_end = started + max(0.0, deadline-started)*.75
    for _ in range(8):
        if time.monotonic() >= search_end or trace["attempts"] >= 96:
            break
        trace["passes"] += 1
        pairs = _pairs(current, moving, kerf)[:6]
        improved, exploration = False, None
        pass_attempts = 0
        for order, heuristic in VARIANTS:
            for _, a, b, ids in pairs:
                if (time.monotonic() >= search_end or trace["attempts"] >= 96
                        or pass_attempts >= 24):
                    break
                trace["attempts"] += 1
                pass_attempts += 1
                trial = _remove(current, ids, kerf)
                if not _repair(trial, movable, ids, (a, b), kerf, order, heuristic,
                               search_end, allow_empty=True):
                    reject("repair_failed")
                    continue
                # Keep sheet indices stable while protected placements exist.
                # Empty sheets can be removed only when they carry no pinned id.
                if {p["id"]: (i, p) for i, s in enumerate(trial["sheets"])
                        for p in s["pieces"] if p["id"] in pinned} != pinned:
                    reject("changed_pinned_geometry")
                    continue
                signature = material_signature(trial)
                if signature in seen:
                    reject("duplicate_geometry")
                    continue
                seen.add(signature)
                profile = envelope_profile(trial, kerf)
                if profile is None:
                    reject("unsupported_profile")
                    continue
                state = (trial, profile)
                if key(state) < key(best) and has_fragmentation_benefit(profile, best[1]):
                    best, current, improved = state, trial, True
                    trace["improvements"] += 1
                    if len(trace["events"]) < 24:
                        trace["events"].append(dict(boards=[a, b], moved=len(ids),
                            ordering=order, heuristic=heuristic, result="proxy_improvement"))
                    break
                reject("no_proxy_improvement")
                if exploration is None or key(state) < key(exploration):
                    exploration = state
            if improved or pass_attempts >= 24:
                break
        if improved:
            continue
        if exploration is None:
            break
        current = exploration[0]
        trace["exploratory_steps"] += 1
    proposal = None
    if key(best) < key(original):
        trial = _plain(best[0])
        trial["sheets"] = [s for s in trial["sheets"] if s["pieces"]]
        checked = _valid(trial, sources, width, height, kerf, machine_type,
                         metric_kwargs, deadline, mirroring_allowed)
        rejection = fragmentation_export_rejection(checked) if checked is not None else None
        if rejection:
            reject(rejection)
        elif checked is not None and has_complete_identity(checked, sources):
            proposal = checked
        else:
            reject("final_validation_failed")
    trace.update(stop="deadline" if time.monotonic() >= search_end else "completed",
                 validated_proposals=int(proposal is not None),
                 best_proxy=best[1],
                 elapsed_sec=round(time.monotonic()-started, 3))
    return proposal, trace
