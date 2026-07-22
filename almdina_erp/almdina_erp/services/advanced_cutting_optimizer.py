from __future__ import annotations

import hashlib
import math
import random
import time
from copy import deepcopy
from typing import Any, Iterable

from almdina_erp.almdina_erp.services.cutting_engine import (
    PACKING_OPTIONS,
    evaluate_plan,
    num,
    pack_guillotine,
    pack_maxrects,
    pack_shelf_first_fit,
    pack_shelf_horizontal,
    pack_shelf_next_fit,
    pack_shelf_vertical,
    pack_skyline,
    prune_free_rects,
    run_single_method,
    split_free_rect,
    validate_plan,
)

AUTO_FAST = "Auto"
AUTO_PRO = "Auto Pro"
DEEP_SEARCH = "Deep Search"
OPTIMAL_SEARCH = "Optimal Search"
ADVANCED_MODES = (AUTO_FAST, AUTO_PRO, DEEP_SEARCH, OPTIMAL_SEARCH)
MACHINE_TYPES = ("Auto", "CNC Router", "Panel Saw")

ORDERING_STRATEGIES = (
    "area_desc",
    "long_side_desc",
    "width_desc",
    "length_desc",
    "perimeter_desc",
    "short_side_desc",
    "square_first",
    "elongated_first",
    "area_asc",
)

METHOD_CONFIGS: dict[str, tuple[str, Any, tuple[Any, ...], int]] = {
    "MaxRects Best Short Side": ("MaxRects - Best Short Side", pack_maxrects, ("best_short_side",), 3),
    "MaxRects Best Area": ("MaxRects - Best Area", pack_maxrects, ("best_area",), 4),
    "MaxRects Bottom Left": ("MaxRects - Bottom Left", pack_maxrects, ("bottom_left",), 5),
    "MaxRects Contact Point": ("MaxRects - Contact Point", pack_maxrects, ("contact_point",), 4),
    "MaxRects Width": ("MaxRects - الأعرض أولاً", pack_maxrects, ("best_short_side",), 3),
    "MaxRects Length": ("MaxRects - الأطول أولاً", pack_maxrects, ("best_short_side",), 3),
    "Shelf Horizontal": ("Shelf Packing - صفوف أفقية", pack_shelf_horizontal, (), 20),
    "Shelf Vertical": ("Shelf Packing - أعمدة عمودية", pack_shelf_vertical, (), 20),
    "Shelf First Fit": ("Shelf Packing - First Fit", pack_shelf_first_fit, (), 18),
    "Shelf Next Fit": ("Shelf Packing - Next Fit", pack_shelf_next_fit, (), 22),
    "Guillotine Short Axis": ("Guillotine - Short Axis Split", pack_guillotine, ("short_axis", "best_area"), 10),
    "Guillotine Long Axis": ("Guillotine - Long Axis Split", pack_guillotine, ("long_axis", "best_area"), 10),
    "Guillotine Best Area Fit": ("Guillotine - Best Area Fit", pack_guillotine, ("short_axis", "best_area"), 9),
    "Guillotine Best Short Side Fit": ("Guillotine - Best Short Side Fit", pack_guillotine, ("short_axis", "best_short_side"), 9),
    "Guillotine Best Long Side Fit": ("Guillotine - Best Long Side Fit", pack_guillotine, ("long_axis", "best_long_side"), 9),
    "Skyline Bottom Left": ("Skyline - Bottom Left", pack_skyline, ("bottom_left",), 12),
    "Skyline Best Fit": ("Skyline - Best Fit", pack_skyline, ("best_fit",), 12),
}

GUILLOTINE_METHODS = tuple(method for method in PACKING_OPTIONS[1:] if method.startswith("Guillotine"))


def _piece_area(piece: dict[str, Any]) -> float:
    return num(piece.get("width_cm")) * num(piece.get("length_cm"))


def _piece_perimeter(piece: dict[str, Any]) -> float:
    return 2 * (num(piece.get("width_cm")) + num(piece.get("length_cm")))


def order_pieces(pieces: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    items = deepcopy(pieces)
    if strategy == "area_desc":
        items.sort(key=_piece_area, reverse=True)
    elif strategy == "area_asc":
        items.sort(key=_piece_area)
    elif strategy == "long_side_desc":
        items.sort(key=lambda p: max(num(p.get("width_cm")), num(p.get("length_cm"))), reverse=True)
    elif strategy == "short_side_desc":
        items.sort(key=lambda p: min(num(p.get("width_cm")), num(p.get("length_cm"))), reverse=True)
    elif strategy == "width_desc":
        items.sort(key=lambda p: num(p.get("width_cm")), reverse=True)
    elif strategy == "length_desc":
        items.sort(key=lambda p: num(p.get("length_cm")), reverse=True)
    elif strategy == "perimeter_desc":
        items.sort(key=_piece_perimeter, reverse=True)
    elif strategy == "square_first":
        items.sort(
            key=lambda p: (
                abs(num(p.get("width_cm")) - num(p.get("length_cm"))),
                -_piece_area(p),
            )
        )
    elif strategy == "elongated_first":
        items.sort(
            key=lambda p: (
                max(num(p.get("width_cm")), num(p.get("length_cm")))
                / max(0.001, min(num(p.get("width_cm")), num(p.get("length_cm")))),
                _piece_area(p),
            ),
            reverse=True,
        )
    return items


def _run_preordered_method(
    ordered_pieces: list[dict[str, Any]],
    original_pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    method_key: str,
    ordering_label: str,
) -> dict[str, Any]:
    label, packer, args, complexity = METHOD_CONFIGS[method_key]
    raw = packer(deepcopy(ordered_pieces), board_w_cm, board_h_cm, kerf_cm, *args)
    plan = evaluate_plan(raw, original_pieces, board_w_cm, board_h_cm, label, method_key, complexity)
    plan["ordering_strategy"] = ordering_label
    return plan


def _free_rectangles_for_sheet(sheet: dict[str, Any]) -> list[dict[str, float]]:
    board_w = num(sheet.get("w"))
    board_h = num(sheet.get("h"))
    free_rects: list[dict[str, float]] = [{"x": 0.0, "y": 0.0, "w": board_w, "h": board_h}]
    for piece in sheet.get("pieces") or []:
        used = {
            "x": num(piece.get("x")),
            "y": num(piece.get("y")),
            "w": num(piece.get("w")),
            "h": num(piece.get("h")),
        }
        next_rects: list[dict[str, float]] = []
        for free in free_rects:
            next_rects.extend(split_free_rect(free, used))
        free_rects = prune_free_rects(next_rects)
    return free_rects


def _largest_reusable_free_area(
    plan: dict[str, Any],
    min_remnant_width_cm: float,
    min_remnant_length_cm: float,
    min_remnant_area_m2: float,
) -> float:
    best = 0.0
    for sheet in plan.get("sheets") or []:
        for rect in _free_rectangles_for_sheet(sheet):
            w = num(rect.get("w"))
            h = num(rect.get("h"))
            area = w * h / 10000
            dimension_ok = (
                (w >= min_remnant_width_cm and h >= min_remnant_length_cm)
                or (h >= min_remnant_width_cm and w >= min_remnant_length_cm)
            )
            if dimension_ok and area >= min_remnant_area_m2:
                best = max(best, area)
    return best


def _cut_metrics(plan: dict[str, Any]) -> tuple[int, float]:
    """Estimate distinct straight cut lines and their total span.

    This is intentionally a production heuristic rather than CNC toolpath CAM.
    It rewards layouts with fewer repeated cut coordinates and shorter overall
    straight-line cutting effort while keeping board count as the primary goal.
    """

    total_lines = 0
    total_length = 0.0
    precision = 4
    for sheet in plan.get("sheets") or []:
        board_w = num(sheet.get("w"))
        board_h = num(sheet.get("h"))
        vertical: dict[float, list[tuple[float, float]]] = {}
        horizontal: dict[float, list[tuple[float, float]]] = {}
        for piece in sheet.get("pieces") or []:
            x = num(piece.get("x"))
            y = num(piece.get("y"))
            w = num(piece.get("w"))
            h = num(piece.get("h"))
            for xx in (x, x + w):
                if 1e-7 < xx < board_w - 1e-7:
                    vertical.setdefault(round(xx, precision), []).append((y, y + h))
            for yy in (y, y + h):
                if 1e-7 < yy < board_h - 1e-7:
                    horizontal.setdefault(round(yy, precision), []).append((x, x + w))

        total_lines += len(vertical) + len(horizontal)
        for spans in vertical.values():
            total_length += max(end for _, end in spans) - min(start for start, _ in spans)
        for spans in horizontal.values():
            total_length += max(end for _, end in spans) - min(start for start, _ in spans)
    return total_lines, total_length


def enrich_plan_metrics(
    plan: dict[str, Any],
    method_key: str,
    machine_type: str = "Auto",
    min_remnant_width_cm: float = 30.0,
    min_remnant_length_cm: float = 30.0,
    min_remnant_area_m2: float = 0.09,
) -> dict[str, Any]:
    result = deepcopy(plan)
    cut_count, cut_length = _cut_metrics(result)
    rotations = sum(
        1
        for sheet in result.get("sheets") or []
        for piece in sheet.get("pieces") or []
        if piece.get("rotated")
    )
    reusable = _largest_reusable_free_area(
        result,
        min_remnant_width_cm,
        min_remnant_length_cm,
        min_remnant_area_m2,
    )
    panel_saw_penalty = 0
    if machine_type == "Panel Saw" and not method_key.startswith("Guillotine"):
        panel_saw_penalty = 1

    result["industrial_metrics"] = {
        "unplaced_count": len(result.get("unplaced") or []),
        "board_count": len(result.get("sheets") or []),
        "waste_area_m2": num(result.get("waste_area_m2")),
        "largest_reusable_free_area_m2": reusable,
        "estimated_cut_count": cut_count,
        "estimated_cut_length_cm": cut_length,
        "rotation_count": rotations,
        "panel_saw_non_guillotine_penalty": panel_saw_penalty,
    }
    result["industrial_rank"] = (
        len(result.get("unplaced") or []),
        len(result.get("sheets") or []),
        panel_saw_penalty,
        -round(reusable, 6),
        cut_count,
        round(cut_length, 3),
        rotations,
        int(result.get("complexity") or 0),
    )
    # Numeric compatibility score. Lexicographic industrial_rank remains the
    # authoritative comparator for advanced modes.
    result["score"] = (
        len(result.get("unplaced") or []) * 10**15
        + len(result.get("sheets") or []) * 10**12
        + panel_saw_penalty * 10**11
        + cut_count * 10**6
        + cut_length * 10**2
        + rotations * 10
        - reusable * 10**5
        + int(result.get("complexity") or 0)
    )
    return result


def _candidate_methods(machine_type: str) -> tuple[str, ...]:
    if machine_type == "Panel Saw":
        return GUILLOTINE_METHODS
    return tuple(PACKING_OPTIONS[1:])


def _candidate_is_better(candidate: dict[str, Any], best: dict[str, Any] | None) -> bool:
    if best is None:
        return True
    return tuple(candidate.get("industrial_rank") or ()) < tuple(best.get("industrial_rank") or ())


def _seed_for_problem(pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float, kerf_cm: float) -> int:
    payload = [f"{board_w_cm:.4f}|{board_h_cm:.4f}|{kerf_cm:.4f}"]
    payload.extend(
        f"{p.get('id')}:{num(p.get('width_cm')):.4f}:{num(p.get('length_cm')):.4f}:{int(bool(p.get('allow_rotation')))}"
        for p in pieces
    )
    digest = hashlib.sha256(";".join(payload).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _alternating_large_small(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = order_pieces(pieces, "area_desc")
    result: list[dict[str, Any]] = []
    left, right = 0, len(ordered) - 1
    while left <= right:
        result.append(ordered[left])
        left += 1
        if left <= right:
            result.append(ordered[right])
            right -= 1
    return result


def _placement_order(plan: dict[str, Any], pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {int(piece["id"]): piece for piece in pieces}
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    sheets = sorted(
        plan.get("sheets") or [],
        key=lambda sheet: sum(num(piece.get("area_m2")) for piece in sheet.get("pieces") or []),
        reverse=True,
    )
    for sheet in sheets:
        for placed in sheet.get("pieces") or []:
            piece_id = int(placed.get("id"))
            if piece_id in by_id and piece_id not in seen:
                result.append(deepcopy(by_id[piece_id]))
                seen.add(piece_id)
    result.extend(deepcopy(piece) for piece in pieces if int(piece["id"]) not in seen)
    return result


def _local_sequences(best: dict[str, Any], pieces: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    placement = _placement_order(best, pieces)
    sequences: list[tuple[str, list[dict[str, Any]]]] = [
        ("placement_dense_first", placement),
        ("placement_reverse", list(reversed(deepcopy(placement)))),
        ("alternating_large_small", _alternating_large_small(pieces)),
    ]
    # Deterministic small neighborhood: rotate the current placement order and
    # reverse short blocks. This is a practical local search in permutation space.
    n = len(placement)
    if n > 2:
        steps = sorted({1, max(1, n // 5), max(1, n // 3)})
        for step in steps:
            sequences.append((f"rotate_{step}", deepcopy(placement[step:] + placement[:step])))
        block = max(2, min(8, n // 4 or 2))
        for start in range(0, min(n, block * 3), block):
            seq = deepcopy(placement)
            seq[start : start + block] = reversed(seq[start : start + block])
            sequences.append((f"reverse_block_{start}", seq))
    return sequences


def auto_fast(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    machine_type: str = "Auto",
    **metric_kwargs: Any,
) -> dict[str, Any]:
    methods = _candidate_methods(machine_type)
    best: dict[str, Any] | None = None
    for method in methods:
        candidate = run_single_method(pieces, board_w_cm, board_h_cm, kerf_cm, method)
        candidate = enrich_plan_metrics(candidate, method, machine_type, **metric_kwargs)
        if _candidate_is_better(candidate, best):
            best = candidate
    assert best is not None
    best["optimization_mode"] = AUTO_FAST
    best["method_label"] = "Auto اختار: " + best["method_label"]
    best["attempts"] = len(methods)
    return best


def auto_pro(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    machine_type: str = "Auto",
    **metric_kwargs: Any,
) -> dict[str, Any]:
    methods = _candidate_methods(machine_type)
    best: dict[str, Any] | None = None
    attempts = 0
    for method in methods:
        for strategy in ORDERING_STRATEGIES:
            ordered = order_pieces(pieces, strategy)
            candidate = _run_preordered_method(
                ordered,
                pieces,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                method,
                strategy,
            )
            candidate = enrich_plan_metrics(candidate, method, machine_type, **metric_kwargs)
            attempts += 1
            if _candidate_is_better(candidate, best):
                best = candidate

    assert best is not None
    # Local-improvement pass around the best placement, focusing on collapsing
    # lightly used final sheets and producing larger reusable leftovers.
    local_methods = [best["method_key"]] + [m for m in methods if m != best["method_key"]][:3]
    for sequence_name, sequence in _local_sequences(best, pieces):
        for method in local_methods:
            candidate = _run_preordered_method(
                sequence,
                pieces,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                method,
                sequence_name,
            )
            candidate = enrich_plan_metrics(candidate, method, machine_type, **metric_kwargs)
            attempts += 1
            if _candidate_is_better(candidate, best):
                best = candidate

    best["optimization_mode"] = AUTO_PRO
    best["method_label"] = "Auto Pro اختار: " + best["method_label"]
    best["attempts"] = attempts
    return best


def deep_search(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    machine_type: str = "Auto",
    time_limit_sec: float = 10.0,
    max_attempts: int = 500,
    **metric_kwargs: Any,
) -> dict[str, Any]:
    started = time.monotonic()
    best = auto_pro(pieces, board_w_cm, board_h_cm, kerf_cm, machine_type, **metric_kwargs)
    attempts = int(best.get("attempts") or 0)
    methods = _candidate_methods(machine_type)
    rng = random.Random(_seed_for_problem(pieces, board_w_cm, board_h_cm, kerf_cm))
    deadline = started + max(0.5, float(time_limit_sec or 10.0))

    while attempts < max_attempts and time.monotonic() < deadline:
        method = methods[attempts % len(methods)]
        sequence = deepcopy(pieces)
        rng.shuffle(sequence)
        # Preserve some structure in random restarts: every third attempt keeps
        # the largest pieces in the first quarter and shuffles the remainder.
        if attempts % 3 == 0 and len(sequence) > 4:
            large = order_pieces(sequence, "area_desc")
            split = max(1, len(large) // 4)
            head = large[:split]
            tail = large[split:]
            rng.shuffle(tail)
            sequence = head + tail
        candidate = _run_preordered_method(
            sequence,
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            method,
            f"seeded_restart_{attempts}",
        )
        candidate = enrich_plan_metrics(candidate, method, machine_type, **metric_kwargs)
        attempts += 1
        if _candidate_is_better(candidate, best):
            best = candidate

    best["optimization_mode"] = DEEP_SEARCH
    best["method_label"] = "بحث معمق اختار: " + best["method_label"].split("اختار: ", 1)[-1]
    best["attempts"] = attempts
    best["search_elapsed_sec"] = round(time.monotonic() - started, 3)
    best["search_time_limit_sec"] = float(time_limit_sec or 10.0)
    return best


def _cp_sat_available() -> bool:
    try:
        from ortools.sat.python import cp_model  # noqa: F401

        return True
    except Exception:
        return False


def _solve_cp_sat(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    upper_bound_bins: int,
    time_limit_sec: float,
) -> dict[str, Any] | None:
    from ortools.sat.python import cp_model

    board_w = max(1, int(round(board_w_cm * 10)))
    board_h = max(1, int(round(board_h_cm * 10)))
    kerf = max(0, int(round(kerf_cm * 10)))
    max_bins = max(1, int(upper_bound_bins))

    model = cp_model.CpModel()
    used_bins = [model.new_bool_var(f"bin_used_{b}") for b in range(max_bins)]
    placements: list[dict[str, Any]] = []
    x_intervals: list[list[Any]] = [[] for _ in range(max_bins)]
    y_intervals: list[list[Any]] = [[] for _ in range(max_bins)]

    for index, piece in enumerate(pieces):
        w0 = max(1, int(round(num(piece.get("width_cm")) * 10)))
        h0 = max(1, int(round(num(piece.get("length_cm")) * 10)))
        allow_rotation = bool(piece.get("allow_rotation")) and w0 != h0

        if allow_rotation:
            rotate = model.new_bool_var(f"rot_{index}")
            width = model.new_int_var(min(w0, h0), max(w0, h0), f"width_{index}")
            height = model.new_int_var(min(w0, h0), max(w0, h0), f"height_{index}")
            model.add_allowed_assignments([rotate, width, height], [(0, w0, h0), (1, h0, w0)])
        else:
            rotate = None
            width = model.new_constant(w0)
            height = model.new_constant(h0)

        packed_width = model.new_int_var(min(w0, h0) + kerf if allow_rotation else w0 + kerf, max(w0, h0) + kerf if allow_rotation else w0 + kerf, f"packed_width_{index}")
        packed_height = model.new_int_var(min(w0, h0) + kerf if allow_rotation else h0 + kerf, max(w0, h0) + kerf if allow_rotation else h0 + kerf, f"packed_height_{index}")
        model.add(packed_width == width + kerf)
        model.add(packed_height == height + kerf)

        presence: list[Any] = []
        xs: list[Any] = []
        ys: list[Any] = []
        for b in range(max_bins):
            present = model.new_bool_var(f"present_{index}_{b}")
            x = model.new_int_var(0, board_w, f"x_{index}_{b}")
            y = model.new_int_var(0, board_h, f"y_{index}_{b}")
            x_end = model.new_int_var(0, board_w + kerf, f"x_end_{index}_{b}")
            y_end = model.new_int_var(0, board_h + kerf, f"y_end_{index}_{b}")
            xi = model.new_optional_interval_var(x, packed_width, x_end, present, f"xi_{index}_{b}")
            yi = model.new_optional_interval_var(y, packed_height, y_end, present, f"yi_{index}_{b}")
            model.add(x + width <= board_w).only_enforce_if(present)
            model.add(y + height <= board_h).only_enforce_if(present)
            model.add(x_end <= board_w + kerf).only_enforce_if(present)
            model.add(y_end <= board_h + kerf).only_enforce_if(present)
            model.add_implication(present, used_bins[b])
            presence.append(present)
            xs.append(x)
            ys.append(y)
            x_intervals[b].append(xi)
            y_intervals[b].append(yi)

        model.add(sum(presence) == 1)
        placements.append(
            {
                "piece": piece,
                "presence": presence,
                "xs": xs,
                "ys": ys,
                "width": width,
                "height": height,
                "rotate": rotate,
            }
        )

    for b in range(max_bins):
        model.add_no_overlap_2d(x_intervals[b], y_intervals[b])
        model.add(sum(p["presence"][b] for p in placements) >= used_bins[b])
        if b + 1 < max_bins:
            model.add(used_bins[b] >= used_bins[b + 1])

    # Symmetry breaker: first piece always belongs to first used sheet.
    if placements:
        model.add(placements[0]["presence"][0] == 1)

    model.minimize(sum(used_bins))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.5, float(time_limit_sec))
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    sheets_by_bin: dict[int, list[dict[str, Any]]] = {}
    for data in placements:
        piece = data["piece"]
        chosen = None
        for b, present in enumerate(data["presence"]):
            if solver.boolean_value(present):
                chosen = b
                break
        if chosen is None:
            continue
        width_mm = solver.value(data["width"])
        height_mm = solver.value(data["height"])
        rotated = bool(data["rotate"] is not None and solver.boolean_value(data["rotate"]))
        placed = {
            "id": piece["id"],
            "label": piece["label"],
            "source_piece_no": piece["source_piece_no"],
            "copy_no": piece["copy_no"],
            "group_qty": piece["group_qty"],
            "x": solver.value(data["xs"][chosen]) / 10,
            "y": solver.value(data["ys"][chosen]) / 10,
            "w": width_mm / 10,
            "h": height_mm / 10,
            "original_w": num(piece.get("width_cm")),
            "original_h": num(piece.get("length_cm")),
            "rotated": rotated,
            "area_m2": num(piece.get("area_m2")),
            "notes": piece.get("notes") or "",
            "edge_long_right": 1 if piece.get("edge_long_right") else 0,
            "edge_long_left": 1 if piece.get("edge_long_left") else 0,
            "edge_width_top": 1 if piece.get("edge_width_top") else 0,
            "edge_width_bottom": 1 if piece.get("edge_width_bottom") else 0,
            "edge_type": piece.get("edge_type") or "",
            "edge_rate_usd": num(piece.get("edge_rate_usd")),
            "edge_cost_usd": num(piece.get("edge_cost_usd")),
        }
        sheets_by_bin.setdefault(chosen, []).append(placed)

    sheets: list[dict[str, Any]] = []
    for new_no, bin_no in enumerate(sorted(sheets_by_bin), start=1):
        sheets.append(
            {
                "sheet_no": new_no,
                "w": board_w_cm,
                "h": board_h_cm,
                "pieces": sheets_by_bin[bin_no],
            }
        )

    raw = {"sheets": sheets, "unplaced": []}
    plan = evaluate_plan(raw, pieces, board_w_cm, board_h_cm, "CP-SAT 2D", "Optimal Search", 50)
    plan["solver_status"] = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
    plan["solver_wall_time_sec"] = round(solver.wall_time, 3)
    return plan


def optimal_search(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    machine_type: str = "Auto",
    time_limit_sec: float = 15.0,
    exact_piece_limit: int = 40,
    **metric_kwargs: Any,
) -> dict[str, Any]:
    started = time.monotonic()
    # Panel saw requires guillotine-separable plans. The generic NoOverlap2D
    # CP-SAT model below is non-guillotine, so preserve machine feasibility by
    # using the strongest guillotine-only deep search instead of pretending an
    # exact panel-saw optimum was proven.
    if machine_type == "Panel Saw":
        best = deep_search(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type=machine_type,
            time_limit_sec=time_limit_sec,
            **metric_kwargs,
        )
        best["optimization_mode"] = OPTIMAL_SEARCH
        best["solver_status"] = "GUILLOTINE_DEEP_SEARCH"
        best["method_label"] = "بحث أمثل للمنشار اللوحي: " + best["method_label"].split(": ", 1)[-1]
        return best

    heuristic_budget = min(max(1.0, float(time_limit_sec) * 0.35), 5.0)
    heuristic = deep_search(
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type=machine_type,
        time_limit_sec=heuristic_budget,
        max_attempts=260,
        **metric_kwargs,
    )
    best = heuristic
    remaining = max(0.5, float(time_limit_sec) - (time.monotonic() - started))

    if len(pieces) <= max(1, int(exact_piece_limit)) and _cp_sat_available() and not heuristic.get("unplaced"):
        exact = _solve_cp_sat(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            max(1, len(heuristic.get("sheets") or [])),
            remaining,
        )
        if exact is not None:
            validation_errors = validate_plan(exact, pieces, board_w_cm, board_h_cm)
            if not validation_errors:
                exact = enrich_plan_metrics(exact, "Optimal Search", machine_type, **metric_kwargs)
                # CP-SAT is authoritative when it proves fewer boards. For equal
                # board count, retain the industrially better layout.
                if len(exact.get("sheets") or []) < len(best.get("sheets") or []) or _candidate_is_better(exact, best):
                    best = exact

    best["optimization_mode"] = OPTIMAL_SEARCH
    best["attempts"] = int(best.get("attempts") or 0)
    best["search_elapsed_sec"] = round(time.monotonic() - started, 3)
    best["search_time_limit_sec"] = float(time_limit_sec)
    if best.get("method_key") == "Optimal Search":
        status_ar = "مثبت كحل أمثل" if best.get("solver_status") == "OPTIMAL" else "أفضل حل وجده المحرك ضمن المهلة"
        best["method_label"] = f"CP-SAT - {status_ar}"
    elif not best.get("solver_status"):
        best["solver_status"] = "HEURISTIC_FALLBACK"
        best["method_label"] = "بحث أمثل - أفضل حل ضمن المهلة: " + best["method_label"].split(": ", 1)[-1]
    return best


def optimize_plan(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
    selected_mode: str | None = AUTO_FAST,
    machine_type: str = "Auto",
    time_limit_sec: float = 10.0,
    exact_piece_limit: int = 40,
    min_remnant_width_cm: float = 30.0,
    min_remnant_length_cm: float = 30.0,
    min_remnant_area_m2: float = 0.09,
) -> dict[str, Any]:
    mode = selected_mode or AUTO_FAST
    metric_kwargs = {
        "min_remnant_width_cm": min_remnant_width_cm,
        "min_remnant_length_cm": min_remnant_length_cm,
        "min_remnant_area_m2": min_remnant_area_m2,
    }

    if mode == AUTO_FAST:
        return auto_fast(pieces, board_w_cm, board_h_cm, kerf_cm, machine_type, **metric_kwargs)
    if mode == AUTO_PRO:
        return auto_pro(pieces, board_w_cm, board_h_cm, kerf_cm, machine_type, **metric_kwargs)
    if mode == DEEP_SEARCH:
        return deep_search(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type,
            time_limit_sec,
            **metric_kwargs,
        )
    if mode == OPTIMAL_SEARCH:
        return optimal_search(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type,
            time_limit_sec,
            exact_piece_limit,
            **metric_kwargs,
        )

    # Manual algorithm selection remains available exactly as before, but now
    # receives the industrial metrics used by reports and plan explanations.
    manual = run_single_method(pieces, board_w_cm, board_h_cm, kerf_cm, mode)
    manual = enrich_plan_metrics(manual, mode, machine_type, **metric_kwargs)
    manual["optimization_mode"] = "Manual"
    manual["attempts"] = 1
    return manual
