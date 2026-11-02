"""Bounded, non-packing final alignment of regular System cutter-center lines.

This module is deliberately not called from plan validation or imported DXF.
Only rigid translations within an existing FULL_BOARD are considered.
"""

from __future__ import annotations

import math
import time
from copy import deepcopy
from typing import Any

from .cutter_center_paths import cutter_center_segments
from .evaluation import placement_permission_errors, validate_plan
from .optimizer import _largest_reusable_free_area, enrich_plan_metrics
from .plan_search import _locked_piece_ids
from .primitives import num

_MAX_PIECES = 64
_MAX_SHIFT_CM = 1.0  # search radius, NOT an imposed translation
_MAX_TRIALS = 24
_MAX_SWEEPS = 4
_EPS = 1e-7
_NETWORK_EPS_MM = 0.05


def _rectangles(plan: dict[str, Any], kerf_cm: float) -> tuple[float, int]:
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
        ]
        segments = cutter_center_segments(shapes, max(0.0, kerf_cm) * 5)
        length += sum(math.dist(a, b) for a, b in segments)
        count += len(segments)
    return length, count


def _safe_regular_only(plan: dict[str, Any], sources: list[dict[str, Any]]) -> bool:
    sheets = plan.get("sheets") or []
    if (
        not sources or len(sources) > _MAX_PIECES or not sheets
        or plan.get("unplaced") or len(plan.get("industrial_rank") or ()) != 8
        or _locked_piece_ids(plan)
    ):
        return False
    for source in sources:
        if (source.get("piece_type") or "Regular") != "Regular" or (
            source.get("resource_kind") or "FULL_BOARD"
        ) != "FULL_BOARD":
            return False
    for sheet in sheets:
        if (sheet.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD":
            return False
        for piece in sheet.get("pieces") or []:
            if (
                (piece.get("piece_type") or "Regular") != "Regular"
                or (piece.get("resource_kind") or "FULL_BOARD") != "FULL_BOARD"
                or any(piece.get(key) for key in (
                    "geometry", "overlays", "special_shape_geometry_json",
                    "placement_outline_cm", "glass_host_piece_id",
                ))
                or any(piece.get(key) is None for key in ("x", "y", "w", "h"))
            ):
                return False
    return True


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


def _candidate_moves(plan: dict[str, Any], kerf_cm: float):
    """Geometry-derived edge/kerf anchors; cheap filtering precedes validation."""
    targets = set()
    for sheet_index, sheet in enumerate(plan["sheets"]):
        pieces = list(sheet.get("pieces") or [])
        for axis in ("x", "y"):
            size = "w" if axis == "x" else "h"
            cross, cross_size = ("y", "h") if axis == "x" else ("x", "w")
            for ids in _groups(sheet, axis):
                members = [p for p in pieces if int(p["id"]) in ids]
                fixed = [p for p in pieces if int(p["id"]) not in ids]
                for a in members:
                    for b in fixed:
                        gap = max(
                            num(a[cross]) - num(b[cross]) - num(b[cross_size]),
                            num(b[cross]) - num(a[cross]) - num(a[cross_size]),
                        )
                        if gap > kerf_cm + _EPS:
                            continue
                        a0, a1 = num(a[axis]), num(a[axis]) + num(a[size])
                        b0, b1 = num(b[axis]), num(b[axis]) + num(b[size])
                        for delta in (b0 - a0, b1 - a1, b1 + kerf_cm - a0, b0 - kerf_cm - a1):
                            if _EPS < abs(delta) <= _MAX_SHIFT_CM + _EPS:
                                targets.add((sheet_index, axis, ids, round(delta, 6)))
    return sorted(targets, key=lambda m: (abs(m[3]), m[0], m[1], m[2], m[3]))


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
) -> dict[str, Any]:
    """Improve only proven network length or fragmentation, preserving the source.

    No improvement, unsupported geometry or expired budget returns the *same*
    input object. Every accepted trial is independently manufacturing-validated.
    """
    if machine_type not in {"Auto", "CNC Router"} or not _safe_regular_only(plan, sources):
        return plan
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        return plan
    if validate_plan(plan, sources, board_w_cm, board_h_cm, kerf_cm=kerf_cm):
        return plan

    best = plan
    best_profile = _rectangles(best, kerf_cm)
    attempts = 0
    for _ in range(_MAX_SWEEPS):
        winner = None
        winner_profile = best_profile
        winner_key = None
        for sheet_index, axis, ids, delta in _candidate_moves(best, kerf_cm):
            if attempts >= _MAX_TRIALS or (
                deadline_monotonic is not None and time.monotonic() >= deadline_monotonic
            ):
                return best
            candidate = _translate_if_clear(best, sheet_index, axis, ids, delta, kerf_cm)
            if candidate is None:
                continue
            attempts += 1
            before_remnant = _largest_reusable_free_area(
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
            if after_remnant + 1e-9 < before_remnant:
                continue
            if validate_plan(candidate, sources, board_w_cm, board_h_cm, kerf_cm=kerf_cm,
                             deadline_monotonic=deadline_monotonic):
                continue
            if placement_permission_errors(candidate, sources, mirroring_allowed=mirroring_allowed):
                continue
            profile = _rectangles(candidate, kerf_cm)
            if (profile[0] > best_profile[0] + _NETWORK_EPS_MM
                    or profile[1] > best_profile[1]
                    or (profile[0] >= best_profile[0] - _NETWORK_EPS_MM
                        and profile[1] >= best_profile[1])):
                continue
            candidate = enrich_plan_metrics(
                candidate, str(best.get("method_key") or ""), machine_type,
                **metric_kwargs,
            )
            if tuple(candidate["industrial_rank"][:4]) > tuple(best["industrial_rank"][:4]):
                continue
            key = (round(profile[0], 5), profile[1], abs(delta),
                   sheet_index, axis, ids, delta)
            if winner_key is None or key < winner_key:
                winner, winner_profile, winner_key = candidate, profile, key
        if winner is None:
            return best
        best, best_profile = winner, winner_profile
    return best
