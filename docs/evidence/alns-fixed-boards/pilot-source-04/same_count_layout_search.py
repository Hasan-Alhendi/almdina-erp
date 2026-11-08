"""Opt-in ALNS neighborhoods for remnants and layout at a fixed board count.

Not wired into any production optimizer mode. Partial repair delegates position
selection and placement to native MaxRects; no dummy piece or new stock exists.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
import math
import random
import time

from .cut_line_quality import final_system_sort_keys, plan_cut_line_quality
from .evaluation import validate_plan, placement_permission_errors
from .optimizer import (_free_rectangles_for_sheet, _remnant_is_separable,
                        _run_preordered_method, enrich_plan_metrics, order_pieces)
from .plan_portfolio import geometry_signature, manufacturing_export_rejection
from .primitives import num, prune_free_rects, rect_intersects, rects_have_clearance, split_free_rect
from .regular_templates import _unprotected_regular, grid_specs
from .strategies.maxrects import find_best_position_maxrects, place_piece_maxrects

OPERATORS = ("exchange", "frontier", "grid", "repack")


@dataclass(frozen=True)
class FixedBoardSearchPolicy:
    operators: tuple[str, ...] = OPERATORS
    adaptive: bool = True
    seed: int = 110526
    max_attempts: int = 96
    max_removed: int = 24
    max_pair_pieces: int = 64
    segment: int = 12
    refine_seconds: float = 0.0

    def __post_init__(self):
        if not self.operators or len(set(self.operators)) != len(self.operators) or any(x not in OPERATORS for x in self.operators):
            raise ValueError("Unknown, duplicate or empty operator set")
        if not 0 < self.max_attempts <= 512 or not 0 < self.max_removed <= 32 or not 0 < self.max_pair_pieces <= 64 or self.segment < 1:
            raise ValueError("Invalid work caps")
        if not math.isfinite(self.refine_seconds) or not 0 <= self.refine_seconds <= .5:
            raise ValueError("Invalid refinement allowance")


@dataclass(frozen=True)
class RemnantRegion:
    sheet_index: int
    x: float
    y: float
    w: float
    h: float

    @property
    def area_m2(self):
        return self.w*self.h/10000

    def rectangle(self):
        return dict(x=self.x, y=self.y, w=self.w, h=self.h)


def largest_remnant_region(plan, *, machine_type, metric_kwargs):
    """Locate exactly the geometry used by the existing remnant metric."""
    regions = []
    for index, sheet in enumerate(plan.get("sheets") or []):
        for rect in _free_rectangles_for_sheet(sheet):
            w, h = rect["w"], rect["h"]
            mw, mh = metric_kwargs["min_remnant_width_cm"], metric_kwargs["min_remnant_length_cm"]
            if (((w+1e-9 >= mw and h+1e-9 >= mh) or (w+1e-9 >= mh and h+1e-9 >= mw))
                    and w*h/10000 >= metric_kwargs["min_remnant_area_m2"]
                    and _remnant_is_separable(rect, sheet["w"], sheet["h"], machine_type=machine_type)):
                regions.append(RemnantRegion(index, **rect))
    return min(regions, key=lambda r: (-r.area_m2, r.sheet_index, r.x, r.y, r.w, r.h), default=None)


def material_signature(plan):
    canonical = deepcopy(plan)
    for sheet in canonical.get("sheets") or []:
        for p in sheet.get("pieces") or []:
            for key in ("id", "piece_instance_id", "copy_no", "source_piece_no"):
                p.pop(key, None)
    return geometry_signature(canonical)


def _cache(sheet, kerf, reserved=None):
    """Native free-space subtraction around pinned physical placements."""
    free = [dict(x=0.0, y=0.0, w=sheet["w"], h=sheet["h"])]
    obstacles = []
    for p in sheet["pieces"]:
        x, y = max(0.0, p["x"]-kerf), max(0.0, p["y"]-kerf)
        obstacles.append(dict(x=x, y=y, w=min(sheet["w"], p["x"]+p["w"]+kerf)-x,
                              h=min(sheet["h"], p["y"]+p["h"]+kerf)-y))
    if reserved is not None:
        obstacles.append(reserved)
    for used in obstacles:
        free = prune_free_rects([part for rect in free for part in split_free_rect(rect, used)])
    sheet["free_rects"] = free
    for key in ("skyline", "shelves"):
        sheet.pop(key, None)


def _remove(plan, ids, kerf, region=None):
    trial = deepcopy(plan)
    for key in ("smart_candidates", "smart_research_candidates", "smart_search"):
        trial.pop(key, None)
    for i, sheet in enumerate(trial["sheets"]):
        sheet["pieces"] = [p for p in sheet["pieces"] if p["id"] not in ids]
        _cache(sheet, kerf, region.rectangle() if region is not None and i == region.sheet_index else None)
    return trial


def _repair(trial, sources, ids, receivers, kerf, ordering, heuristic, deadline):
    pending = [p for p in sources if p["id"] in ids]
    if ordering == "family":
        pending.sort(key=lambda p: (p["width_cm"], p["length_cm"], p["id"]))
    else:
        pending = order_pieces(pending, ordering)
    for piece in pending:
        if time.monotonic() >= deadline:
            return False
        options = []
        for i in receivers:
            spot = find_best_position_maxrects(trial["sheets"][i], piece, heuristic, kerf)
            if spot is not None:
                options.append((spot["score"], i, spot))
        if not options:
            return False
        _, index, spot = min(options, key=lambda v: (v[0], receivers.index(v[1])))
        place_piece_maxrects(trial["sheets"][index], piece, spot, kerf)
    return all(sheet["pieces"] for sheet in trial["sheets"])


def _exchange(plan, sources, kerf, region, policy, deadline):
    if region is None:
        return
    owner = region.sheet_index
    outgoing = {p["id"] for p in plan["sheets"][owner]["pieces"]}
    if len(outgoing) >= policy.max_removed:
        return
    families = {}
    for i, sheet in enumerate(plan["sheets"]):
        if i == owner:
            continue
        for p in sheet["pieces"]:
            families.setdefault(tuple(sorted((p["w"], p["h"]))), []).append(p["id"])
    seeds = sorted(families.values(), key=lambda ids: (
        min(next(p["area_m2"] for p in sources if p["id"] == item) for item in ids), ids))[:6]
    receivers = tuple(i for i in range(len(plan["sheets"])) if i != owner)
    for members in seeds:
        for count in dict.fromkeys((1, min(2, len(members)), min(4, len(members)))):
            incoming = set(members[:count])
            if len(outgoing | incoming) > policy.max_removed:
                continue
            subset = [p for p in sources if p["id"] in incoming]
            for method in ("MaxRects Contact Point", "MaxRects Best Short Side"):
                if time.monotonic() >= deadline:
                    return
                packed = _run_preordered_method(order_pieces(subset, "area_desc"), subset,
                    plan["sheets"][owner]["w"], plan["sheets"][owner]["h"], kerf, method, "area_desc")
                if packed.get("unplaced") or len(packed["sheets"]) != 1:
                    yield None, dict(reason="seed_does_not_fit")
                    continue
                trial = _remove(plan, outgoing | incoming, kerf)
                trial["sheets"][owner]["pieces"] = deepcopy(packed["sheets"][0]["pieces"])
                _cache(trial["sheets"][owner], kerf)
                for ordering in ("area_desc", "long_side_desc"):
                    candidate = deepcopy(trial)
                    complete = _repair(candidate, sources, outgoing, receivers, kerf, ordering, "contact_point", deadline)
                    yield candidate if complete else None, dict(removed=sorted(outgoing | incoming), ordering=ordering)


def _frontier(plan, sources, kerf, region, policy, deadline):
    if region is None:
        return
    index = region.sheet_index
    sheet = plan["sheets"][index]
    r = region.rectangle()
    # Event coordinates only: no millimetre scan or fabricated piece.
    targets = []
    for p in sheet["pieces"]:
        for axis, extent in (("x", "w"), ("y", "h")):
            for edge in (p[axis], p[axis]+p[extent]):
                left, right = min(r[axis], edge), max(r[axis]+r[extent], edge)
                if right-left > r[extent]+1e-8:
                    target = dict(r)
                    target.update({axis:left, extent:right-left})
                    targets.append(target)
    seen = set()
    for target in sorted(targets, key=lambda t: t["w"]*t["h"]):
        key = tuple(round(target[k], 8) for k in ("x", "y", "w", "h"))
        if key in seen:
            continue
        seen.add(key)
        removed = {p["id"] for p in sheet["pieces"] if rect_intersects(p, target)}
        if not removed or len(removed) > policy.max_removed or len(removed) == len(sheet["pieces"]):
            continue
        protected = RemnantRegion(index, **target)
        for order in ("area_desc", "long_side_desc", "family"):
            if time.monotonic() >= deadline:
                return
            trial = _remove(plan, removed, kerf, protected)
            complete = _repair(trial, sources, removed, tuple(i for i in range(len(plan["sheets"])) if i != index),
                               kerf, order, "contact_point", deadline)
            yield trial if complete else None, dict(removed=sorted(removed), target=target, ordering=order)


def _grid(plan, sources, kerf, region, policy, deadline):
    owner = region.sheet_index if region is not None else -1
    eligible = [i for i in range(len(plan["sheets"])) if i != owner]
    located = {p["id"]: (i, p) for i, s in enumerate(plan["sheets"]) for p in s["pieces"]}
    subset = [p for p in sources if located[p["id"]][0] in eligible]
    if not eligible:
        return
    width, height = plan["sheets"][eligible[0]]["w"], plan["sheets"][eligible[0]]["h"]
    families = {}
    for source in subset:
        key = (source["width_cm"], source["length_cm"], bool(source.get("allow_rotation")))
        families.setdefault(key, []).append(source)
    specs = sorted([spec for members in families.values() for spec in grid_specs(members, width, height, kerf)], key=lambda s: (
        -s[2]*s[3]*s[0][0]["width_cm"]*s[0][0]["length_cm"],
        s[1]["rotated"], -s[2], s[3]))
    # Cover every repeated family. Two native templates per orientation suffice
    # for this bounded cohort; round-robin below prevents one family starving all
    # others with its heuristic/order variants.
    chosen, counts = [], Counter()
    for spec in specs:
        key = (spec[0][0]["width_cm"], spec[0][0]["length_cm"], spec[1]["rotated"])
        if counts[key] < 2:
            chosen.append(spec)
            counts[key] += 1
    def proposals(spec):
        family, orientation, columns, rows = spec
        members = family[:columns*rows]
        ids = {p["id"] for p in members}
        gw = columns*orientation["w"]+(columns-1)*kerf
        gh = rows*orientation["h"]+(rows-1)*kerf
        boards = sorted(eligible, key=lambda i: -sum(located[p["id"]][0] == i for p in members))[:2]
        for index in boards:
            for x, y in dict.fromkeys(((0.0, 0.0), (0.0, height-gh), (width-gw, 0.0), (width-gw, height-gh))):
                target = dict(x=x, y=y, w=gw, h=gh)
                blockers = {p["id"] for p in plan["sheets"][index]["pieces"]
                            if p["id"] not in ids and not rects_have_clearance(p, target, kerf)}
                removed = ids | blockers
                if len(removed) > policy.max_removed:
                    continue
                for ordering in ("long_side_desc", "area_desc", "family"):
                    for heuristic in ("contact_point", "best_short_side", "best_area", "bottom_left"):
                        if time.monotonic() >= deadline:
                            return
                        trial = _remove(plan, removed, kerf, region)
                        for j, piece in enumerate(members):
                            spot = dict(x=x+(j % columns)*(orientation["w"]+kerf),
                                        y=y+(j // columns)*(orientation["h"]+kerf), **orientation)
                            place_piece_maxrects(trial["sheets"][index], piece, spot, kerf)
                        complete = _repair(trial, sources, blockers, tuple(eligible), kerf, ordering, heuristic, deadline)
                        yield trial if complete else None, dict(removed=sorted(removed), grid=[index, x, y, columns, rows], ordering=ordering, heuristic=heuristic)
    pending = deque(iter(proposals(spec)) for spec in chosen[:32])
    while pending and time.monotonic() < deadline:
        stream = pending.popleft()
        try:
            yield next(stream)
            pending.append(stream)
        except StopIteration:
            pass


def _repack(plan, sources, kerf, region, policy, deadline):
    owner = region.sheet_index if region is not None else -1
    eligible = [i for i in range(len(plan["sheets"])) if i != owner]
    source = {p["id"]: p for p in sources}
    for pair in combinations(eligible, 2):
        subset = [source[p["id"]] for i in pair for p in plan["sheets"][i]["pieces"]]
        if len(subset) > policy.max_pair_pieces:
            continue
        width, height = plan["sheets"][pair[0]]["w"], plan["sheets"][pair[0]]["h"]
        for ordering in ("area_desc", "long_side_desc", "width_desc", "length_desc", "short_side_desc"):
            for method in ("MaxRects Contact Point", "MaxRects Best Short Side", "MaxRects Best Area", "MaxRects Bottom Left"):
                if time.monotonic() >= deadline:
                    return
                packed = _run_preordered_method(order_pieces(subset, ordering), subset, width, height, kerf, method, ordering)
                trial = None
                if not packed.get("unplaced") and len(packed["sheets"]) == len(pair):
                    trial = deepcopy(plan)
                    for old_index, new in zip(pair, packed["sheets"]):
                        trial["sheets"][old_index]["pieces"] = deepcopy(new["pieces"])
                        _cache(trial["sheets"][old_index], kerf)
                yield trial, dict(pair=pair, ordering=ordering, method=method)


def _valid(candidate, sources, width, height, kerf, machine, metrics, deadline):
    if candidate.get("unplaced") or manufacturing_export_rejection(candidate):
        return None
    if validate_plan(candidate, sources, width, height, kerf_cm=kerf, deadline_monotonic=deadline):
        return None
    if placement_permission_errors(candidate, sources, mirroring_allowed=False):
        return None
    expected = Counter(p.get("piece_instance_id") for p in sources)
    actual = Counter(p.get("piece_instance_id") for s in candidate["sheets"] for p in s["pieces"])
    if actual != expected:
        return None
    candidate = enrich_plan_metrics(candidate, str(candidate.get("method_key") or ""), machine, **metrics)
    candidate.update(kerf_cm=kerf, machine_type=machine)
    return candidate


def improve_fixed_board_layout(plan, sources, width, height, kerf, *, deadline,
        policy=FixedBoardSearchPolicy(), machine_type="CNC Router", metric_kwargs=None,
        cancelled=lambda: False):
    """Best plus up to four physical alternatives, trace; never auto-persist."""
    metrics = metric_kwargs or dict(min_remnant_width_cm=30., min_remnant_length_cm=30., min_remnant_area_m2=.09)
    trace = dict(attempts=0, stop="exhausted", operators={}, events=[])
    if (machine_type not in {"Auto", "CNC Router"} or not sources or plan.get("unplaced")
            or not all(_unprotected_regular(p) for p in sources)
            or not all(_unprotected_regular(p) and (s.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
                       for s in plan.get("sheets") or [] for p in s["pieces"])):
        trace["stop"] = "unsupported_cohort"
        return [deepcopy(plan)], trace
    if cancelled() or time.monotonic() >= deadline:
        trace["stop"] = "stopped"
        return [deepcopy(plan)], trace
    best = _valid(deepcopy(plan), sources, width, height, kerf, machine_type, metrics, deadline)
    if best is None or not best.get("sheets"):
        trace["stop"] = "invalid_incumbent"
        return [deepcopy(plan)], trace
    count = len(best["sheets"])
    portfolio, seen = [best], {material_signature(best)}
    rng = random.Random(policy.seed)
    weights = {op: 1. for op in policy.operators}
    scores, uses = Counter(), Counter()
    generators = dict(exchange=_exchange, frontier=_frontier, grid=_grid, repack=_repack)

    def streams():
        region = largest_remnant_region(best, machine_type=machine_type, metric_kwargs=metrics)
        return {op: iter(generators[op](best, sources, kerf, region, policy, deadline)) for op in policy.operators}

    pending = streams()
    for op in policy.operators:
        trace["operators"][op] = dict(attempts=0, repaired=0, valid=0, improvements=0, seconds=0., rejects={})
    for iteration in range(policy.max_attempts):
        if cancelled() or time.monotonic() >= deadline:
            trace["stop"] = "cancelled" if cancelled() else "deadline"
            break
        if not pending:
            trace["stop"] = "neighborhoods_exhausted"
            break
        active = list(pending)
        if not policy.adaptive or iteration < 2*len(policy.operators):
            op = active[iteration % len(active)]
        else:
            total = sum(weights[x] for x in active)
            op = rng.choices(active, weights=[.2/len(active)+.8*weights[x]/total for x in active], k=1)[0]
        start = time.monotonic()
        try:
            candidate, event = next(pending[op])
        except StopIteration:
            del pending[op]
            continue
        stat = trace["operators"][op]
        stat["attempts"] += 1
        trace["attempts"] += 1
        uses[op] += 1
        reason = None
        if candidate is None:
            reason = "repair_failed"
        elif len(candidate["sheets"]) != count or any(not s["pieces"] for s in candidate["sheets"]):
            reason = "changed_board_count"
        else:
            stat["repaired"] += 1
            ranked = enrich_plan_metrics(candidate, str(best.get("method_key") or ""), machine_type, **metrics)
            ranked.update(kerf_cm=kerf, machine_type=machine_type)
            if tuple(ranked["industrial_rank"][:4]) > tuple(best["industrial_rank"][:4]):
                reason = "remnant_regression"
            elif material_signature(ranked) in seen:
                reason = "duplicate_geometry"
            else:
                if policy.refine_seconds > 0:
                    from .final_cut_line_alignment import align_regular_cut_lines
                    ranked = _valid(ranked, sources, width, height, kerf, machine_type, metrics, deadline)
                    if ranked is not None:
                        ranked = align_regular_cut_lines(ranked, sources, width, height, kerf,
                            machine_type=machine_type, mirroring_allowed=False, metric_kwargs=metrics,
                            deadline_monotonic=min(deadline, time.monotonic()+policy.refine_seconds))
                if ranked is None:
                    stat["rejects"]["pre_refinement_validation"] = stat["rejects"].get("pre_refinement_validation", 0)+1
                    stat["seconds"] += time.monotonic()-start
                    trace["events"].append(dict(operator=op, rejection="pre_refinement_validation", **event))
                    continue
                before, after = plan_cut_line_quality(best, kerf), plan_cut_line_quality(ranked, kerf)
                equal_remnant = ranked["industrial_rank"][3] == best["industrial_rank"][3]
                keys = final_system_sort_keys([best, ranked])
                if keys[1] >= keys[0]:
                    reason = "no_final_improvement"
                elif equal_remnant and (before is None or after is None or after[0] > before[0]+1e-5 or after[1] > before[1]):
                    reason = "organization_network_regression"
                else:
                    checked = _valid(ranked, sources, width, height, kerf, machine_type, metrics, deadline)
                    if checked is None:
                        reason = "validation_failed"
                    else:
                        stat["valid"] += 1
                        seen.add(material_signature(checked))
                        best = checked
                        portfolio.append(best)
                        portfolio.sort(key=lambda p: final_system_sort_keys([p])[0])
                        portfolio = portfolio[:5]
                        stat["improvements"] += 1
                        scores[op] += 5 if not equal_remnant else 2
                        pending = streams()
        if reason:
            stat["rejects"][reason] = stat["rejects"].get(reason, 0)+1
        stat["seconds"] += time.monotonic()-start
        trace["events"].append(dict(operator=op, rejection=reason, **event))
        if policy.adaptive and (iteration+1) % policy.segment == 0:
            for operator in weights:
                if uses[operator]:
                    weights[operator] = max(.05, .8*weights[operator]+.2*scores[operator]/uses[operator])
            scores.clear()
            uses.clear()
    trace["weights"] = weights
    return [deepcopy(plan), *[p for p in portfolio if material_signature(p) != material_signature(plan)][:4]], trace
