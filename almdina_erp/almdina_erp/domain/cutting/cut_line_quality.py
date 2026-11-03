"""Final manufacturable cutter-center topology for System layout comparison.

One quality source for final alignment and the five-plan System gallery.
Unlike the fast search estimate, this models actual supported finished outlines
and Glass openings; it never joins gaps or counts a border as an internal cut.

No NC time, clamp/tool setup or machine-ready certification is inferred.
Unsupported contours return None rather than pretending to be rectangles.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from .cutter_center_paths import cutter_center_segments
from .glass_opening_nesting import _part_geometry
from .primitives import num
from .sheet_edge_trim import resolved_sheet_trim_cm

_TOL_MM = 0.05
_MAX_SHEET_PIECES = 64


def _inside_length(
    start: tuple[float, float], end: tuple[float, float],
    width_mm: float, height_mm: float,
) -> float:
    """Clip a *real* straight segment against the board for ranking only.

    The center may legally overhang when Trim=0. Only its internal portion can
    break a tie in favor of an in-board straight toolpath.
    """
    dx, dy = end[0] - start[0], end[1] - start[1]
    lower, upper = 0.0, 1.0
    for p, q in (
        (-dx, start[0]), (dx, width_mm - start[0]),
        (-dy, start[1]), (dy, height_mm - start[1]),
    ):
        if abs(p) < 1e-10:
            if q < 0:
                return 0.0
            continue
        t = q / p
        if p < 0:
            lower = max(lower, t)
        else:
            upper = min(upper, t)
        if lower > upper:
            return 0.0
    if upper - lower <= 0:
        return 0.0
    middle = (lower + upper) / 2
    x = start[0] + middle * dx
    y = start[1] + middle * dy
    if not (_TOL_MM < x < width_mm - _TOL_MM
            and _TOL_MM < y < height_mm - _TOL_MM):
        return 0.0
    return math.hypot(dx, dy) * (upper - lower)


def sheet_cut_line_quality(
    sheet: Mapping[str, Any],
    kerf_cm: float,
    *,
    piece_filter: Callable[[Mapping[str, Any]], bool] | None = None,
) -> tuple[float, int, float] | None:
    """(real mm, merged segments, longest internal straight center in mm).

    A complete sheet is required for final ranking. A filter is only for
    legacy/local bounded-search screening, never for authoritative comparison
    against protected shape contours.
    """
    pieces = list(sheet.get("pieces") or ())
    if len(pieces) > _MAX_SHEET_PIECES:
        return None
    shapes = []
    for piece in pieces:
        if piece_filter is not None and not piece_filter(piece):
            continue
        part = _part_geometry(piece)
        if part is None:
            return None
        outer = [(num(x) * 10, num(y) * 10) for x, y in part.outer]
        holes = [[(num(x) * 10, num(y) * 10) for x, y in ring]
                 for ring in part.holes]
        shapes.append((outer, holes))
    if not shapes:
        return (0.0, 0, 0.0)
    segments = cutter_center_segments(shapes, max(0.0, kerf_cm) * 5)
    try:
        trim_x = resolved_sheet_trim_cm(sheet, axis="x") * 10
        trim_y = resolved_sheet_trim_cm(sheet, axis="y") * 10
    except ValueError:
        return None
    w = (num(sheet["full_width_cm"]) * 10 if sheet.get("full_width_cm") is not None
         else num(sheet.get("w")) * 10 + 2 * trim_x)
    h = (num(sheet["full_length_cm"]) * 10 if sheet.get("full_length_cm") is not None
         else num(sheet.get("h")) * 10 + 2 * trim_y)
    if w <= 0 or h <= 0 or not all(map(math.isfinite, (w, h, trim_x, trim_y))):
        return None
    return (
        sum(math.dist(a, b) for a, b in segments),
        len(segments),
        max((_inside_length((a[0]+trim_x, a[1]+trim_y),
                           (b[0]+trim_x, b[1]+trim_y), w, h)
             for a, b in segments), default=0.0),
    )


def plan_cut_line_quality(
    plan: Mapping[str, Any], kerf_cm: float,
) -> tuple[float, int, float] | None:
    """True geometry of all board cutters, or unavailable (never a proxy)."""
    sheets = plan.get("sheets") or ()
    if not sheets:
        return None
    profiles = []
    for sheet in sheets:
        profile = sheet_cut_line_quality(sheet, kerf_cm)
        if profile is None:
            return None
        profiles.append(profile)
    return (
        sum(profile[0] for profile in profiles),
        sum(profile[1] for profile in profiles),
        sum(profile[2] for profile in profiles),
    )


def final_cut_quality_key(profile: tuple[float, int, float]) -> tuple[float, float, int]:
    """One lexicographic contract shared by post-alignment and final gallery.

    Length first; on equal length prefer a long actual internal continuous
    segment, then fewer disconnected centers. Hard geometry/remnant rules are
    applied *before* this key by the caller.
    """
    length, count, longest = profile
    return (round(length, 5), -round(longest, 3), count)


def final_system_sort_keys(plans: list[Mapping[str, Any]]) -> list[tuple]:
    """One final comparator for generation and cached preview continuation.

    All plans must have comparable, proven cutter geometry. Legacy/incomplete
    metadata, other machines or unsupported contours keep legacy order for the
    entire collection; an estimate is never mixed with a measured network.
    """
    legacy = [(tuple(plan.get("industrial_rank") or ()),) for plan in plans]
    profiles = []
    for plan in plans:
        if (plan.get("machine_type") not in {"Auto", "CNC Router"}
                or len(plan.get("industrial_rank") or ()) != 8
                or plan.get("kerf_cm") is None):
            return legacy
        try:
            kerf = float(plan["kerf_cm"])
        except (TypeError, ValueError, OverflowError):
            return legacy
        if not math.isfinite(kerf) or kerf < 0:
            return legacy
        profile = plan_cut_line_quality(plan, kerf)
        if profile is None:
            return legacy
        profiles.append(profile)
    return [(tuple(plan["industrial_rank"][:4]), final_cut_quality_key(profile),
             tuple(plan["industrial_rank"][4:]))
            for plan, profile in zip(plans, profiles)]
