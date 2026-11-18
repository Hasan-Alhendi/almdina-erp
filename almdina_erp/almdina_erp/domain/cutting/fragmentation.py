"""Bounded free-space screening and a separate, multi-scale alternative policy.

The search proxy subtracts kerf-expanded placement envelopes. Exact material
measurements belong to the geometry port after projection. Neither metric is
a manufacturing-validation result or changes the industrial winner.
"""

from __future__ import annotations

from functools import lru_cache
import math
from statistics import median


def analysis_scales_cm(plan, kerf):
    """Scales follow the tool and the input size distribution, in centimetres."""
    sides = sorted(
        min(float(p.get("original_w") or p["w"]), float(p.get("original_h") or p["h"]))
        for s in plan.get("sheets") or ()
        for p in s.get("pieces") or ()
    )
    if not sides:
        return ()
    lower_quartile = sides[(len(sides) - 1) // 4]
    return tuple(
        sorted(
            {
                0.0,
                round(2 * kerf, 6),
                round(lower_quartile / 4, 6),
                round(median(sides) / 2, 6),
            }
        )
    )


@lru_cache(maxsize=512)
def _envelope_regions(width, height, rectangles, kerf, scale):
    """Exact rectangle-union complement areas using disjoint vertical strips.

    Positive shared edges connect strips. A corner contact cannot connect two
    offcuts. The query is the clearance core of the envelope free space.
    """
    inset, grow = scale / 2, kerf + scale / 2
    left, right, bottom, top = inset, width - inset, inset, height - inset
    if right <= left or top <= bottom:
        return ()
    obstacles = [
        (
            max(left, x - grow),
            max(bottom, y - grow),
            min(right, x + w + grow),
            min(top, y + h + grow),
        )
        for x, y, w, h in rectangles
    ]
    obstacles = [r for r in obstacles if r[2] > r[0] and r[3] > r[1]]
    xs = sorted({left, right, *(x for r in obstacles for x in (r[0], r[2]))})
    parents, areas, previous = [], [], []

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for x1, x2 in zip(xs, xs[1:]):
        mid = (x1 + x2) / 2
        intervals = sorted((y1, y2) for a, y1, b, y2 in obstacles if a < mid < b)
        free, cursor = [], bottom
        for y1, y2 in intervals:
            if y1 > cursor + 1e-8:
                free.append((cursor, y1))
            cursor = max(cursor, y2)
        if cursor < top - 1e-8:
            free.append((cursor, top))
        current = []
        for y1, y2 in free:
            index = len(parents)
            parents.append(index)
            areas.append((x2 - x1) * (y2 - y1))
            for a, b, other in previous:
                if min(y2, b) - max(y1, a) > 1e-8:
                    p, q = root(index), root(other)
                    if p != q:
                        parents[q] = p
                        areas[p] += areas[q]
            current.append((y1, y2, index))
        previous = current
    return tuple(
        sorted((areas[i] for i in range(len(parents)) if root(i) == i), reverse=True)
    )


def envelope_profile(plan, kerf):
    """Cheap screening only. Unknown contours retain their conservative blank."""
    if (
        plan.get("unplaced")
        or not plan.get("sheets")
        or not math.isfinite(kerf)
        or kerf < 0
    ):
        return None
    sheets = plan["sheets"]
    if len(sheets) > 32 or any(
        len(s.get("pieces") or ()) > 64
        or (s.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
        or any(
            (p.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
            for p in s["pieces"]
        )
        for s in sheets
    ):
        return None
    scales = analysis_scales_cm(plan, kerf)
    if not scales:
        return None
    levels = []
    for scale in scales:
        total, primary, count = 0.0, 0.0, 0
        for sheet in sheets:
            rectangles = tuple(
                sorted(
                    tuple(round(float(p[k]), 7) for k in ("x", "y", "w", "h"))
                    for p in sheet["pieces"]
                )
            )
            regions = _envelope_regions(
                float(sheet["w"]), float(sheet["h"]), rectangles, kerf, scale
            )
            # Tool-sized specks are excluded from both the numerator and denominator.
            meaningful = [area for area in regions if area > max(1e-8, kerf * kerf)]
            total += sum(meaningful)
            primary += max(meaningful, default=0.0)
            count += len(meaningful)
        levels.append(
            dict(
                scale_cm=scale,
                free_area_cm2=total,
                primary_area_cm2=primary,
                secondary_area_cm2=total - primary,
                regions=count,
            )
        )
    return dict(
        version=1, tier="envelope_core", levels=levels, scope="all", kerf_cm=kerf
    )


def fragmentation_key(profile):
    """Minimax secondary fractions across scales, with no fitted weights."""
    levels = profile["levels"]
    # Use the same tool-cleared area at every scale. Dividing by an eroded
    # core would make a nearly empty large-scale core dominate the comparison.
    available = max(levels[0]["free_area_cm2"], 1e-8)
    fractions = sorted(
        (round(p["secondary_area_cm2"] / available, 6) for p in levels), reverse=True
    )
    return (
        tuple(fractions),
        tuple(sorted((p["regions"] for p in levels), reverse=True)),
        -sum(p["primary_area_cm2"] for p in levels),
    )


def has_fragmentation_benefit(candidate, incumbent):
    """Require comparable geometry coverage and a tool-resolved area benefit."""
    if (
        candidate is None
        or incumbent is None
        or candidate["tier"] != incumbent["tier"]
        or tuple(candidate["scope"]) != tuple(incumbent["scope"])
        or [p["scale_cm"] for p in candidate["levels"]]
        != [p["scale_cm"] for p in incumbent["levels"]]
    ):
        return False
    margin = max(1e-6, candidate["kerf_cm"] ** 2)
    return fragmentation_key(candidate) < fragmentation_key(incumbent) and any(
        a["secondary_area_cm2"] + margin < b["secondary_area_cm2"]
        for a, b in zip(candidate["levels"], incumbent["levels"])
    )


class FragmentationNominee:
    """One checked completed proposal, independent of native winner retention."""

    def __init__(self, kerf):
        self.kerf = kerf
        self.plan = None
        self.profile = None
        self.observed = 0

    def offer(self, plan):
        profile = envelope_profile(plan, self.kerf)
        self.observed += 1
        if profile is not None and (
            self.profile is None
            or (len(plan["sheets"]), fragmentation_key(profile))
            < (len(self.plan["sheets"]), fragmentation_key(self.profile))
        ):
            from copy import deepcopy

            self.plan, self.profile = deepcopy(plan), profile


def has_complete_identity(plan, sources):
    """Prove each physical copy's binding, beyond a matching numeric id count."""

    def identity(piece):
        return (
            str(piece.get("piece_instance_id") or ""),
            piece.get("source_piece_no"),
            piece.get("copy_no"),
        )

    expected = {piece["id"]: identity(piece) for piece in sources}
    stable = [value[0] for value in expected.values()]
    placed = [piece for sheet in plan.get("sheets") or () for piece in sheet["pieces"]]
    return (
        bool(expected)
        and all(stable)
        and len(set(stable)) == len(sources)
        and len(placed) == len(sources)
        and {piece["id"]: identity(piece) for piece in placed} == expected
    )


def fragmentation_export_rejection(plan):
    """Keep side proposals within the strict importer's provable shape cohort."""
    from .plan_portfolio import manufacturing_export_rejection
    from .finished_piece_geometry import resolve_finished_geometry_mm
    from .dxf_geometry import is_axis_aligned_rectangle

    rejection = manufacturing_export_rejection(plan)
    if rejection:
        return rejection
    for sheet in plan.get("sheets") or ():
        for piece in sheet["pieces"]:
            if piece.get("piece_type") != "Special":
                continue
            geometry = resolve_finished_geometry_mm(
                stored_geometry=piece.get("geometry"), stored_piece=piece
            )
            if geometry is None:
                return "unproven_special_outline"
            if is_axis_aligned_rectangle(geometry["outer"], 0.25):
                return "rectangular_special_outline"
    return None


def regroup_fragmentation(
    plan,
    sources,
    width,
    height,
    kerf,
    *,
    deadline,
    machine_type,
    mirroring_allowed,
    metric_kwargs,
):
    """Screen bounded native 2/3-board packs and validate the best alternative.

    The existing generator only replaces independent Regular FULL_BOARD sheets.
    All protected sheets and material identities remain in the whole-plan gate.
    Its private proposals may have a worse industrial remnant. Only a completed
    checked proposal is returned for Application projection as an alternative.
    """
    import time
    from .plan_search import _regrouped_board_candidates
    from .same_count_layout_search import _valid

    pool = FragmentationNominee(kerf)
    pool.offer(plan)
    if pool.profile is None or machine_type not in {"Auto", "CNC Router"}:
        return None, dict(attempts=0, cap=24, rejections={}, stop="unsupported_cohort")
    attempts, rejected = 0, {}
    for candidate in _regrouped_board_candidates(
        plan, sources, width, height, kerf, deadline, yield_attempts=True
    ):
        attempts += 1
        reason = None
        if candidate is None:
            reason = "packing_failed"
        else:
            profile = envelope_profile(candidate, kerf)
            fewer_boards = len(candidate["sheets"]) < len(pool.plan["sheets"])
            if len(candidate["sheets"]) > len(pool.plan["sheets"]):
                reason = "more_boards"
            elif not fewer_boards and not has_fragmentation_benefit(
                profile, pool.profile
            ):
                reason = "no_proxy_benefit"
            else:
                checked = _valid(
                    candidate,
                    sources,
                    width,
                    height,
                    kerf,
                    machine_type,
                    metric_kwargs,
                    deadline,
                    mirroring_allowed,
                )
                if checked is None or not has_complete_identity(checked, sources):
                    reason = "validation_failed"
                else:
                    pool.offer(checked)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
        if time.monotonic() >= deadline:
            break
    from .plan_portfolio import geometry_signature

    changed = pool.plan is not None and geometry_signature(
        pool.plan
    ) != geometry_signature(plan)
    return (pool.plan if changed else None), dict(
        attempts=attempts,
        cap=24,
        rejections=rejected,
        proxy_improvement=changed,
        stop="deadline" if time.monotonic() >= deadline else "completed",
    )
