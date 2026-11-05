"""Isolated ALNS prototype. Nothing in production imports this module.

Whole-board destruction deliberately trades fine partial movement for reuse of
the native stable-Kerf packers. Six *selection* hypotheses share one repair
matrix, so an ablation changes selection rather than also changing the packer.
Protected sheets remain untouched. This is not a new packing implementation.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
import random
import time

from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan, placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import _run_preordered_method, order_pieces, enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature, manufacturing_export_rejection
from almdina_erp.almdina_erp.domain.cutting.plan_search import _locked_piece_ids, _free_rectangles, _regular_layout_quality

OPERATORS = ("board", "repeated", "gap", "disruptive", "cross", "geometry")
METHODS = ("MaxRects Contact Point", "MaxRects Best Short Side", "MaxRects Best Area", "MaxRects Bottom Left")
ORDERS = ("original", "area_desc", "long_side_desc", "width_desc", "length_desc", "family", "reverse", "spatial")
METRICS = dict(min_remnant_width_cm=30, min_remnant_length_cm=30, min_remnant_area_m2=.09)


@dataclass(frozen=True)
class Policy:
    operators: tuple[str, ...] = OPERATORS
    adaptive: bool = False
    seed: int = 110526
    max_attempts: int = 96
    max_pieces: int = 64
    segment: int = 12
    reaction: float = .2
    exploration: float = .2
    max_boards: int = 3
    area_first: bool = False
    screen_prefix: bool = False

    def __post_init__(self):
        if not self.operators or any(op not in OPERATORS for op in self.operators):
            raise ValueError("Unknown/empty operator list")
        if len(set(self.operators)) != len(self.operators):
            raise ValueError("Duplicate operator")
        if not 0 < self.max_attempts <= 512 or not 0 < self.max_pieces <= 64 or self.segment <= 0:
            raise ValueError("Work caps out of bounds")
        if not 0 < self.reaction <= 1 or not 0 < self.exploration <= 1:
            raise ValueError("Invalid adaptive parameters")
        if not 3 <= self.max_boards <= 8:
            raise ValueError("Board neighborhood cap out of bounds")


def family(piece):
    return tuple(sorted((round(piece.get("w", piece.get("width_cm", 0)), 6),
                         round(piece.get("h", piece.get("length_cm", 0)), 6))))


def material_signature(plan):
    """Physical geometry, ignoring swaps of indistinguishable copy identities.

    Identities still pass the separate whole-plan validation. Host references
    remain intact: the prototype never modifies their protected sheets.
    """
    canonical = deepcopy(plan)
    for sheet in canonical.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            for key in ("id", "piece_instance_id", "copy_no", "source_piece_no"):
                piece.pop(key, None)
    return geometry_signature(canonical)


def eligible_sheets(plan, sources):
    locked = _locked_piece_ids(plan)
    source = {p["id"]: p for p in sources}
    eligible = []
    for i, sheet in enumerate(plan.get("sheets") or []):
        if (sheet.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD" or not sheet.get("pieces"):
            continue
        if all(p["id"] in source and p["id"] not in locked and all(
            (item.get("piece_type") or "Regular") == "Regular"
            and (item.get("resource_kind") or "FULL_BOARD") == "FULL_BOARD"
            and not any(item.get(k) for k in ("geometry", "overlays", "placement_outline_cm", "special_shape_geometry_json"))
            for item in (p, source[p["id"]])) for p in sheet["pieces"]):
            eligible.append(i)
    return eligible


def neighborhoods(plan, sources, width, height, kerf, policy, rng):
    eligible = eligible_sheets(plan, sources)
    sheets = plan["sheets"]
    # Bounded by eight boards, chosen by sparse material load, not display ID.
    eligible.sort(key=lambda i: (sum(p["w"]*p["h"] for p in sheets[i]["pieces"]), i))
    eligible = eligible[:8]
    combos = [c for count in (2, 3) for c in combinations(eligible, count)
              if sum(len(sheets[i]["pieces"]) for i in c) <= policy.max_pieces]
    cancellation = [c for count in range(2, min(len(eligible), policy.max_boards)+1)
                    for c in combinations(eligible, count)
                    if sum(len(sheets[i]["pieces"]) for i in c) <= policy.max_pieces]
    areas = {i: sum(p["w"]*p["h"] for p in sheets[i]["pieces"]) for i in eligible}
    families = {i: Counter(family(p) for p in sheets[i]["pieces"]) for i in eligible}
    quality = {i: _regular_layout_quality(dict(sheets=[sheets[i]]), kerf) for i in eligible}
    gaps = {i: _free_rectangles(sheets[i])[:8] for i in eligible}

    def shared(c):
        return sum(sum((families[i] & families[j]).values()) for i, j in combinations(c, 2))

    def fit(c):
        # Compatibility with actual free dimensions, including a conservative
        # Kerf allowance. This selects a board; it does not certify insertion.
        return sum(any((p["w"]+kerf <= r["w"]+1e-8 and p["h"]+kerf <= r["h"]+1e-8)
                   or (p["h"]+kerf <= r["w"]+1e-8 and p["w"]+kerf <= r["h"]+1e-8
                       and next(s for s in sources if s["id"] == p["id"]).get("allow_rotation"))
                   for r in gaps[j])
                   for i in c for j in c if i != j for p in sheets[i]["pieces"])

    random_combos = list(combos)
    rng.shuffle(random_combos)
    # No changes to feasibility/ranking: these are neighborhood priorities.
    return dict(
        board=sorted([c for c in cancellation if sum(areas[i] for i in c) <= (len(c)-1)*width*height+1e-8],
                     key=lambda c: (sum(areas[i] for i in c)/(len(c)-1), c)),
        repeated=sorted([c for c in combos if shared(c)], key=lambda c: (-shared(c), len(c), c)),
        gap=sorted(combos, key=lambda c: (-fit(c), len(c), c)),
        disruptive=sorted(combos, key=lambda c: (sum(quality[i][0]/quality[i][1] for i in c)/len(c), -shared(c), c)),
        cross=random_combos,
        geometry=sorted(combos, key=lambda c: (sum(quality[i][0]/quality[i][1] for i in c)/len(c), -shared(c), len(c), c)))


def repair_order(subset, plan, indices, ordering, rng):
    if ordering == "family":
        counts = Counter(family(p) for p in subset)
        return sorted(subset, key=lambda p: (-counts[family(p)], family(p), p["id"]))
    if ordering == "reverse":
        return list(reversed(subset))
    if ordering == "spatial":
        positions = {p["id"]: (i, p["y"], p["x"]) for i in indices for p in plan["sheets"][i]["pieces"]}
        return sorted(subset, key=lambda p: positions[p["id"]])
    return order_pieces(subset, ordering)


def replace_boards(plan, indices, packed):
    candidate = deepcopy(plan)
    # Clear stale portfolios/phase diagnostics from a changed geometry.
    for key in ("smart_candidates", "smart_research_candidates", "smart_search"):
        candidate.pop(key, None)
    replacements = []
    for i, new in zip(indices, packed["sheets"]):
        old = deepcopy(plan["sheets"][i])
        for cache in ("free_rects", "skyline", "shelves"):
            old.pop(cache, None)
        old.update(deepcopy(new))
        replacements.append(old)
    candidate["sheets"] = [s for i, s in enumerate(candidate["sheets"]) if i not in indices] + replacements
    for i, sheet in enumerate(candidate["sheets"], 1):
        sheet["sheet_no"] = i
    return candidate


def checked(candidate, sources, width, height, kerf, machine, deadline):
    if candidate.get("unplaced") or manufacturing_export_rejection(candidate):
        return None, "incomplete_or_export_contract"
    faults = validate_plan(candidate, sources, width, height, kerf_cm=kerf, deadline_monotonic=deadline)
    if faults:
        return None, "geometry:" + str(faults[0])[:160]
    if placement_permission_errors(candidate, sources, mirroring_allowed=False):
        return None, "permission"
    candidate.update(used_area_m2=sum(p["area_m2"] for p in sources),
        total_board_area_m2=len(candidate["sheets"])*width*height/10000)
    candidate["waste_area_m2"] = candidate["total_board_area_m2"]-candidate["used_area_m2"]
    candidate = enrich_plan_metrics(candidate, str(candidate.get("method_key") or ""), machine, **METRICS)
    candidate.update(kerf_cm=kerf, machine_type=machine)
    return candidate, None


def run_alns(plan, sources, width, height, kerf, *, deadline, policy=Policy(),
             machine="CNC Router", cancelled=lambda: False):
    """Return native plus at most four unique research proposals and trace.

    One caller-owned deadline covers selection/packing/validation/evaluation.
    Packing is atomic/cooperative. A completed accepted candidate is retained
    even if the next deadline check/cancellation stops further work.
    """
    trace = dict(attempts=0, stop="exhausted", operators={}, weights={}, events=[])
    if machine not in {"Auto", "CNC Router"} or time.monotonic() >= deadline or cancelled():
        trace["stop"] = "unsupported_machine_or_stopped"
        return [deepcopy(plan)], trace
    baseline, reason = checked(deepcopy(plan), sources, width, height, kerf, machine, deadline)
    if baseline is None:
        trace.update(stop="invalid_baseline", baseline_rejection=reason)
        return [deepcopy(plan)], trace
    best, portfolio = baseline, [baseline]
    seen = {material_signature(baseline)}
    rng = random.Random(policy.seed)
    orders = (("area_desc", "long_side_desc", "family", "original", "width_desc", "length_desc", "reverse", "spatial")
              if policy.area_first else ORDERS)
    selection = time.monotonic()
    queues = {op: values[:4] for op, values in neighborhoods(best, sources, width, height, kerf, policy, rng).items()}
    trace["selection_seconds"] = time.monotonic()-selection
    active = [op for op in policy.operators if queues[op]]
    used = {op: 0 for op in active}
    weights = {op: 1.0 for op in active}
    scores, counts = Counter(), Counter()
    for op in active:
        trace["operators"][op] = dict(attempts=0, packed=0, valid=0, novel=0, improvements=0,
            board_gain=0, seconds=0.0, packing_seconds=0.0, validation_seconds=0.0, rejects={})
    for iteration in range(policy.max_attempts):
        if cancelled() or time.monotonic() >= deadline:
            trace["stop"] = "cancelled" if cancelled() else "deadline"
            break
        if not active:
            trace["stop"] = "no_eligible_neighborhood"
            break
        if not policy.adaptive or iteration < 2*len(active):
            op = active[iteration % len(active)]
        else:
            total = sum(weights[x] for x in active)
            probabilities = [(1-policy.exploration)*weights[x]/total+policy.exploration/len(active) for x in active]
            op = rng.choices(active, weights=probabilities, k=1)[0]
        start = time.monotonic()
        stat = trace["operators"][op]
        turn = used[op]
        # Move through neighborhoods before changing the repair recipe. All
        # recipes eventually visit every selected neighborhood, without repeats.
        choices = queues[op]
        recipe = turn // len(choices)
        if recipe >= len(METHODS)*len(orders):
            active.remove(op)
            continue
        indices = choices[turn % len(choices)]
        ordering = orders[(recipe // len(METHODS)) % len(orders)]
        method = METHODS[recipe % len(METHODS)]
        used[op] += 1
        stat["attempts"] += 1
        trace["attempts"] += 1
        counts[op] += 1
        ids = {p["id"] for i in indices for p in best["sheets"][i]["pieces"]}
        subset = [p for p in sources if p["id"] in ids]
        sequence = repair_order(subset, best, indices, ordering, rng)
        packing = time.monotonic()
        packed = _run_preordered_method(sequence, subset, width, height, kerf, method, ordering)
        stat["packing_seconds"] += time.monotonic()-packing
        reason, improved, gain = None, False, 0
        if packed.get("unplaced") or len(packed["sheets"]) > len(indices):
            reason = "repair_needs_more_boards"
        else:
            stat["packed"] += 1
            candidate = replace_boards(best, indices, packed)
            if policy.screen_prefix:
                # Safe one-way rejection, reusing the native metric. A worse
                # protected prefix cannot win our acceptance contract, so no
                # independent validation proof is claimed for screened work.
                screened = enrich_plan_metrics(candidate, str(candidate.get("method_key") or ""), machine, **METRICS)
                if tuple(screened["industrial_rank"][:4]) > tuple(best["industrial_rank"][:4]):
                    reason = "screened_industrial_prefix"
                    candidate = None
            validation = time.monotonic()
            if candidate is not None:
                candidate, reason = checked(candidate, sources, width, height, kerf, machine, deadline)
            stat["validation_seconds"] += time.monotonic()-validation
            if candidate is not None:
                stat["valid"] += 1
                signature = material_signature(candidate)
                if signature in seen:
                    reason = "duplicate_geometry"
                else:
                    seen.add(signature)
                    stat["novel"] += 1
                    keys = final_system_sort_keys([best, candidate])
                    improved = keys[1] < keys[0]
                    # Nonimproving exploration cannot spend another board or
                    # damage the protected industrial prefix in the portfolio.
                    if tuple(candidate["industrial_rank"][:4]) <= tuple(best["industrial_rank"][:4]):
                        portfolio.append(candidate)
                        portfolio.sort(key=lambda p: final_system_sort_keys([p])[0])
                        portfolio = portfolio[:5]
                    else:
                        reason = "industrial_prefix_regression"
                    if improved:
                        gain = len(best["sheets"])-len(candidate["sheets"])
                        stat["improvements"] += 1
                        stat["board_gain"] += gain
                        scores[op] += 5 if gain else 2
                        best = candidate
                        # Indices refer to the new topology after cancellation.
                        selection = time.monotonic()
                        queues = {x: values[:4] for x, values in neighborhoods(best, sources, width, height, kerf, policy, rng).items()}
                        trace["selection_seconds"] += time.monotonic()-selection
                        active = [x for x in active if queues[x]]
                    elif reason is None:
                        scores[op] += .25  # Novel admissible layout, not a rank weight.
        if reason:
            stat["rejects"][reason] = stat["rejects"].get(reason, 0)+1
        stat["seconds"] += time.monotonic()-start
        trace["events"].append(dict(operator=op, indices=indices, method=method, ordering=ordering,
            rejected=reason, improved=improved, board_gain=gain))
        if policy.adaptive and (iteration+1) % policy.segment == 0:
            for x in weights:
                if counts[x]:
                    weights[x] = max(.05, (1-policy.reaction)*weights[x]+policy.reaction*scores[x]/counts[x])
            scores.clear()
            counts.clear()
    trace["weights"] = weights
    # Native checkpoint is always available even if all nominees are rejected
    # during actual Application projection. No automatic persistence exists.
    return [deepcopy(plan), *[p for p in portfolio if material_signature(p) != material_signature(plan)][:4]], trace
