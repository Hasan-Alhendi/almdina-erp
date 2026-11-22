"""Deterministic whole-sheet positioning after final System gallery selection.

Coordinates and offsets are centimetres. Trim belongs to the usable frame;
protection is a physical margin and includes that trim exactly once.
"""
from __future__ import annotations

from copy import deepcopy
import math
from time import perf_counter

from .cut_line_quality import sheet_cut_line_quality
from .evaluation import placement_permission_errors, validate_plan
from .optimizer import _reusable_free_rectangles_for_sheet, enrich_plan_metrics
from .plan_portfolio import manufacturing_export_rejection
from .plan_settings import EdgeProtectionPolicy
from .shape_aware_nesting import _translate_pieces
from .sheet_edge_trim import _occupied_span, resolved_sheet_trim_cm

_EPS = 1e-7
# These representations are not emitted by native packing and have no shared
# translation contract. Never move only their owning rectangles.
_UNSUPPORTED = (
    "geometry", "overlays", "toolpaths", "cnc_toolpaths", "attached_geometry",
    "outline_mm", "base_outline_mm", "pivot_mm", "reservation_mm",
    "base_reservation_mm", "base_hole_mm", "blank_reservation_cm", "cut_paths", "machining_paths",
)


def axis_offset(a: float, b: float, trim: float, protection: float,
                center_limit: float) -> tuple[float, float, str]:
    """Return preferred offset, protection-only fallback and policy, once.

    a/b exclude mandatory trim. All five arguments use the same unit.
    Eligibility always refers to the original final geometry.
    """
    if not all(math.isfinite(v) and v >= -_EPS
               for v in (a, b, trim, protection, center_limit)):
        raise ValueError("invalid final sheet positioning dimensions")
    a, b = max(0.0, a), max(0.0, b)
    slack = a + b
    extra = max(0.0, protection - trim)
    possible = slack + _EPS >= 2 * extra
    protected = min(max(a, extra), slack - extra) - a if possible else 0.0
    if max(a, b) <= center_limit + _EPS:
        return slack / 2 - a, protected, "CENTERED"
    return protected, protected, "EDGE_PROTECTED" if possible else "INSUFFICIENT_SLACK"


def translate_sheet(sheet, dx, dy):
    """One rigid translation for every native piece and absolute outline.

    Glass holes, special-shape definitions and machining specifications are
    piece-local; their consumers derive world coordinates from x/y. Preserve
    those definitions, host identities and orientations verbatim.
    """
    moved = deepcopy(sheet)
    moved["pieces"] = _translate_pieces(moved["pieces"], dx, dy)
    for key in ("free_rects", "skyline", "shelves"):
        moved.pop(key, None)
    return moved


def _remnants_preserved(before, after, dx, dy, options):
    """Each qualified rectangle keeps one connected qualified successor.

    Only the strips consumed by the accepted rigid offset may be lost.
    Overlapping maximal rectangles are never added to manufacture a successor.
    """
    previous = _reusable_free_rectangles_for_sheet(before, **options)
    current = _reusable_free_rectangles_for_sheet(after, **options)
    for rect in previous:
        required = max(0.0, rect["w"] - abs(dx)) * max(0.0, rect["h"] - abs(dy))
        if required <= _EPS or not any(
            max(0.0, min(rect["x"] + rect["w"], other["x"] + other["w"])
                - max(rect["x"], other["x"]))
            * max(0.0, min(rect["y"] + rect["h"], other["y"] + other["h"])
                - max(rect["y"], other["y"])) >= required - _EPS
            for other in current
        ):
            return False
    return True


def position_final_sheets(plan, sources, width, height, kerf, *,
                          policy: EdgeProtectionPolicy, center_limit,
                          machine_type, mirroring_allowed, metric_options):
    """Position every selected board without a search deadline or repacking.

    A rejected combined move falls back to safe whole-sheet axes. On each axis
    a rejected centering endpoint may fall back to minimum physical protection.
    No intermediate movement is exposed and original inputs remain untouched.
    """
    started = perf_counter()
    result = deepcopy(plan)
    reports = []
    by_id = {int(p["id"]): p for p in sources}
    options = {**metric_options, "machine_type": machine_type}
    complete = all(
        all(isinstance(sheet.get(k), (int, float)) and math.isfinite(sheet[k]) and sheet[k] > 0
            for k in ("w", "h"))
        and all(all(isinstance(p.get(k), (int, float)) and math.isfinite(p[k])
                    for k in ("x", "y", "w", "h")) for p in sheet.get("pieces") or [])
        for sheet in plan.get("sheets") or []
    )
    baseline_errors = []
    if complete:
        baseline_errors = validate_plan(plan, sources, width, height, kerf_cm=kerf)
        baseline_errors += placement_permission_errors(plan, sources, mirroring_allowed=mirroring_allowed)
    for index, sheet in enumerate(plan.get("sheets") or []):
        report = dict(sheet_no=sheet.get("sheet_no", index + 1), dx_mm=0.0,
                      dy_mm=0.0, rejected=[])
        reports.append(report)
        pieces = sheet.get("pieces") or []
        reason = None
        if not complete:
            reason = "INCOMPLETE_GEOMETRY"
        elif baseline_errors:
            reason = "INVALID_BASELINE"
        elif machine_type not in {"Auto", "CNC Router"}:
            reason = "UNSUPPORTED_MACHINE"
        elif (str(sheet.get("resource_kind") or "FULL_BOARD").upper() != "FULL_BOARD"
              or str(sheet.get("source_type") or "Full Board").lower() not in {"full board", "full_board"}
              or any(str(p.get("resource_kind") or "FULL_BOARD").upper() != "FULL_BOARD" for p in pieces)):
            reason = "OFFCUT"
        elif not pieces:
            reason = "EMPTY_SHEET"
        elif (any(sheet.get(key) for key in _UNSUPPORTED)
              or any(p.get(key) for p in pieces for key in _UNSUPPORTED)):
            reason = "UNSUPPORTED_ATTACHED_GEOMETRY"
        before_profile = sheet_cut_line_quality(sheet, kerf, max_pieces=None) if reason is None else None
        if reason is None and before_profile is None:
            reason = "UNSUPPORTED_CUTTER_GEOMETRY"
        if reason:
            report["reason"] = reason
            continue
        decisions = []
        for axis, size, protection in (("x", "w", policy.horizontal_mm),
                                       ("y", "h", policy.vertical_mm)):
            start, end = _occupied_span(pieces, axis)
            decisions.append(axis_offset(start, float(sheet[size]) - end,
                resolved_sheet_trim_cm(sheet, plan, axis=axis), protection / 10, center_limit))
        report["policies"] = [d[2] for d in decisions]
        sheet_sources = [by_id[int(p["id"])] for p in pieces]

        def accepted(dx, dy):
            if abs(dx) < _EPS and abs(dy) < _EPS:
                return sheet
            moved = translate_sheet(sheet, dx, dy)
            local = dict(sheets=[moved], unplaced=[])
            errors = validate_plan(local, sheet_sources, width, height, kerf_cm=kerf)
            errors += placement_permission_errors(local, sheet_sources, mirroring_allowed=mirroring_allowed)
            rejection = "GEOMETRY_OR_PERMISSION" if errors else manufacturing_export_rejection(local)
            profile = sheet_cut_line_quality(moved, kerf, max_pieces=None)
            if not rejection and (profile is None or abs(profile[0] - before_profile[0]) > .05
                                  or profile[1] != before_profile[1]):
                rejection = "CUTTER_TOPOLOGY_CHANGED"
            if not rejection and not _remnants_preserved(sheet, moved, dx, dy, options):
                rejection = "QUALIFIED_REMNANT_LOST"
            if rejection:
                report["rejected"].append(dict(dx_mm=dx * 10, dy_mm=dy * 10,
                                               reason=rejection, errors=errors))
                return None
            return moved

        preferred_x, protection_x, _ = decisions[0]
        preferred_y, protection_y, _ = decisions[1]
        # Only the prescribed center/protection endpoints, then a valid axis
        # alone. Keep centering on the other axis when just one center fails.
        # Zero is the final fallback, never a reason to skip a safe axis.
        offsets = dict.fromkeys((
            (preferred_x, preferred_y), (preferred_x, protection_y),
            (protection_x, preferred_y), (protection_x, protection_y),
            (preferred_x, 0.0), (protection_x, 0.0),
            (0.0, preferred_y), (0.0, protection_y),
        ))
        moved, dx, dy = sheet, 0.0, 0.0
        for trial_x, trial_y in offsets:
            if abs(trial_x) + abs(trial_y) < _EPS:
                continue
            trial = accepted(trial_x, trial_y)
            if trial is not None:
                moved, dx, dy = trial, trial_x, trial_y
                break
        result["sheets"][index] = moved
        report.update(dx_mm=round(dx * 10, 6), dy_mm=round(dy * 10, 6),
                      reason="POSITIONED" if abs(dx) + abs(dy) > _EPS else "UNCHANGED")
    if complete:
        result = enrich_plan_metrics(result, str(plan.get("method_key") or ""), **options)
    return result, dict(sheets=reports, sheets_processed=len(reports),
                       elapsed_sec=round(perf_counter() - started, 6))
