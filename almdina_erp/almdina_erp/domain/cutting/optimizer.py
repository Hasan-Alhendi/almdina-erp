from __future__ import annotations

import hashlib
import json
import random
import time
from collections import deque
from copy import deepcopy
from typing import Any

from .evaluation import evaluate_plan, validate_plan
from .kerf_layout import pack_with_stable_kerf
from .glass_opening_dxf import record_glass_opening
from .primitives import (
    _edge_metadata,
    double_edge_metadata,
    liner_metadata,
    num,
    prune_free_rects,
    sort_pieces,
    split_free_rect,
)
from .registry import METHOD_CONFIGS, PACKING_OPTIONS, STRATEGY_BY_KEY, run_single_method

AUTO_FAST = "Auto"
AUTO_PRO = "Auto Pro"
DEEP_SEARCH = "Deep Search"
OPTIMAL_SEARCH = "Optimal Search"
SMART_SEARCH = "Smart Search"
ADVANCED_MODES = (AUTO_FAST, AUTO_PRO, DEEP_SEARCH, OPTIMAL_SEARCH, SMART_SEARCH)
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

GUILLOTINE_METHODS = tuple(
    method for method in PACKING_OPTIONS[1:] if method.startswith("Guillotine")
)


def _piece_area(piece: dict[str, Any]) -> float:
    return num(piece.get("width_cm")) * num(piece.get("length_cm"))


def _piece_perimeter(piece: dict[str, Any]) -> float:
    return 2 * (num(piece.get("width_cm")) + num(piece.get("length_cm")))


def order_pieces(
    pieces: list[dict[str, Any]],
    strategy: str,
) -> list[dict[str, Any]]:
    items = deepcopy(pieces)
    if strategy == "area_desc":
        items.sort(key=_piece_area, reverse=True)
    elif strategy == "area_asc":
        items.sort(key=_piece_area)
    elif strategy == "long_side_desc":
        items.sort(
            key=lambda piece: max(
                num(piece.get("width_cm")),
                num(piece.get("length_cm")),
            ),
            reverse=True,
        )
    elif strategy == "short_side_desc":
        items.sort(
            key=lambda piece: min(
                num(piece.get("width_cm")),
                num(piece.get("length_cm")),
            ),
            reverse=True,
        )
    elif strategy == "width_desc":
        items.sort(key=lambda piece: num(piece.get("width_cm")), reverse=True)
    elif strategy == "length_desc":
        items.sort(key=lambda piece: num(piece.get("length_cm")), reverse=True)
    elif strategy == "perimeter_desc":
        items.sort(key=_piece_perimeter, reverse=True)
    elif strategy == "square_first":
        items.sort(
            key=lambda piece: (
                abs(
                    num(piece.get("width_cm"))
                    - num(piece.get("length_cm"))
                ),
                -_piece_area(piece),
            )
        )
    elif strategy == "elongated_first":
        items.sort(
            key=lambda piece: (
                max(
                    num(piece.get("width_cm")),
                    num(piece.get("length_cm")),
                )
                / max(
                    0.001,
                    min(
                        num(piece.get("width_cm")),
                        num(piece.get("length_cm")),
                    ),
                ),
                _piece_area(piece),
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
    raw = pack_with_stable_kerf(
        packer,
        ordered_pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        args,
    )
    plan = evaluate_plan(
        raw,
        original_pieces,
        board_w_cm,
        board_h_cm,
        label,
        method_key,
        complexity,
    )
    plan["ordering_strategy"] = ordering_label
    return plan


def _free_rectangles_for_sheet(
    sheet: dict[str, Any],
) -> list[dict[str, float]]:
    board_w = num(sheet.get("w"))
    board_h = num(sheet.get("h"))
    free_rects: list[dict[str, float]] = [
        {"x": 0.0, "y": 0.0, "w": board_w, "h": board_h}
    ]
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
    machine_type: str = "Auto",
) -> float:
    """Largest remnant that can actually be separated from the board.

    An enclosed void is not a remnant. A panel saw can separate only a
    through-cut strip. Fewer boards remain a higher priority than this area.
    """

    best = 0.0
    for sheet in plan.get("sheets") or []:
        board_w = num(sheet.get("w"))
        board_h = num(sheet.get("h"))
        for rect in _free_rectangles_for_sheet(sheet):
            width = num(rect.get("w"))
            height = num(rect.get("h"))
            if not _remnant_is_separable(
                rect, board_w, board_h, machine_type=machine_type
            ):
                continue
            area = width * height / 10000
            dimension_ok = (
                width >= min_remnant_width_cm
                and height >= min_remnant_length_cm
            ) or (
                height >= min_remnant_width_cm
                and width >= min_remnant_length_cm
            )
            if dimension_ok and area >= min_remnant_area_m2:
                best = max(best, area)
    return best


def _remnant_is_separable(
    rect: dict[str, float],
    board_w: float,
    board_h: float,
    *,
    machine_type: str,
) -> bool:
    width = num(rect.get("w"))
    height = num(rect.get("h"))
    if machine_type == "Panel Saw":
        spans_width = width >= board_w - 1e-6
        spans_height = height >= board_h - 1e-6
        return spans_width or spans_height
    return (
        num(rect.get("x")) <= 1e-6
        or num(rect.get("y")) <= 1e-6
        or num(rect.get("x")) + width >= board_w - 1e-6
        or num(rect.get("y")) + height >= board_h - 1e-6
    )


def _cut_metrics(plan: dict[str, Any]) -> tuple[int, float]:
    """Estimate distinct straight cut lines and their total span.

    Pieces nested inside a Glass opening are cut from the opening waste, not as
    additional free-board saw lines, so they are excluded from this estimate.
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
            if piece.get("glass_host_piece_id") not in (None, ""):
                continue
            x = num(piece.get("x"))
            y = num(piece.get("y"))
            width = num(piece.get("w"))
            height = num(piece.get("h"))
            for xx in (x, x + width):
                if 1e-7 < xx < board_w - 1e-7:
                    vertical.setdefault(round(xx, precision), []).append(
                        (y, y + height)
                    )
            for yy in (y, y + height):
                if 1e-7 < yy < board_h - 1e-7:
                    horizontal.setdefault(round(yy, precision), []).append(
                        (x, x + width)
                    )

        total_lines += len(vertical) + len(horizontal)
        for spans in vertical.values():
            total_length += max(end for _, end in spans) - min(
                start for start, _ in spans
            )
        for spans in horizontal.values():
            total_length += max(end for _, end in spans) - min(
                start for start, _ in spans
            )
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
        machine_type=machine_type,
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
    result["score"] = (
        len(result.get("unplaced") or []) * 10**9
        + len(result.get("sheets") or []) * 10**6
        + panel_saw_penalty * 10**5
        + cut_count
        + cut_length * 10**-4
        + rotations * 10**-5
        - reusable * 10**-1
        + int(result.get("complexity") or 0) * 10**-6
    )
    return result


def _candidate_methods(machine_type: str) -> tuple[str, ...]:
    if machine_type == "Panel Saw":
        return GUILLOTINE_METHODS
    return tuple(PACKING_OPTIONS[1:])


def _candidate_is_better(
    candidate: dict[str, Any],
    best: dict[str, Any] | None,
) -> bool:
    if best is None:
        return True
    return tuple(candidate.get("industrial_rank") or ()) < tuple(
        best.get("industrial_rank") or ()
    )


def _seed_for_problem(
    pieces: list[dict[str, Any]],
    board_w_cm: float,
    board_h_cm: float,
    kerf_cm: float,
) -> int:
    # Keep the random order stream stable across trim settings: usable board
    # dimensions change with the requested margin, but should not independently
    # reshuffle which heuristic candidates receive the bounded search budget.
    payload = [f"{kerf_cm:.4f}"]
    payload.extend(
        f"{piece.get('id')}:{num(piece.get('width_cm')):.4f}:"
        f"{num(piece.get('length_cm')):.4f}:"
        f"{int(bool(piece.get('allow_rotation')))}"
        for piece in pieces
    )
    digest = hashlib.sha256(";".join(payload).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _alternating_large_small(
    pieces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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


def _placement_order(
    plan: dict[str, Any],
    pieces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {int(piece["id"]): piece for piece in pieces}
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    sheets = sorted(
        plan.get("sheets") or [],
        key=lambda sheet: sum(
            num(piece.get("area_m2"))
            for piece in sheet.get("pieces") or []
        ),
        reverse=True,
    )
    for sheet in sheets:
        for placed in sheet.get("pieces") or []:
            piece_id = int(placed.get("id"))
            if piece_id in by_id and piece_id not in seen:
                result.append(deepcopy(by_id[piece_id]))
                seen.add(piece_id)
    result.extend(
        deepcopy(piece)
        for piece in pieces
        if int(piece["id"]) not in seen
    )
    return result


def _local_sequences(
    best: dict[str, Any],
    pieces: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    placement = _placement_order(best, pieces)
    sequences: list[tuple[str, list[dict[str, Any]]]] = [
        ("placement_dense_first", placement),
        ("placement_reverse", list(reversed(deepcopy(placement)))),
        ("alternating_large_small", _alternating_large_small(pieces)),
    ]
    count = len(placement)
    if count > 2:
        steps = sorted({1, max(1, count // 5), max(1, count // 3)})
        for step in steps:
            sequences.append(
                (
                    f"rotate_{step}",
                    deepcopy(placement[step:] + placement[:step]),
                )
            )
        block = max(2, min(8, count // 4 or 2))
        for start in range(0, min(count, block * 3), block):
            sequence = deepcopy(placement)
            sequence[start : start + block] = reversed(
                sequence[start : start + block]
            )
            sequences.append((f"reverse_block_{start}", sequence))
    # Repeated rectangular sizes can consume the useful gaps in batches.
    # Interleave those sizes with at most three starting groups, keeping the
    # existing packers, per-piece permissions and industrial ranking intact.
    if all((piece.get("piece_type") or "Regular") == "Regular" for piece in pieces):
        sizes: dict[tuple[float, float], list[dict[str, Any]]] = {}
        for piece in order_pieces(pieces, "area_desc"):
            sizes.setdefault((num(piece.get("width_cm")), num(piece.get("length_cm"))), []).append(piece)
        groups = list(sizes.values())
        if 1 < len(groups) < len(pieces):
            for start in range(min(3, len(groups))):
                pending = deque(deque(group) for group in groups[start:] + groups[:start])
                sequence = []
                while pending:
                    group = pending.popleft()
                    sequence.append(group.popleft())
                    if group:
                        pending.append(group)
                sequences.append((f"dimension_cycle_{start}", sequence))
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
        candidate = run_single_method(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            method,
        )
        candidate = enrich_plan_metrics(
            candidate,
            method,
            machine_type,
            **metric_kwargs,
        )
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
    seen_orders: set[tuple[str, tuple[int, ...]]] = set()
    for method in methods:
        for strategy in ORDERING_STRATEGIES:
            ordered = order_pieces(pieces, strategy)
            signature = (method, tuple(int(piece["id"]) for piece in ordered))
            if signature in seen_orders:
                continue
            seen_orders.add(signature)
            candidate = _run_preordered_method(
                ordered,
                pieces,
                board_w_cm,
                board_h_cm,
                kerf_cm,
                method,
                strategy,
            )
            candidate = enrich_plan_metrics(
                candidate,
                method,
                machine_type,
                **metric_kwargs,
            )
            attempts += 1
            if _candidate_is_better(candidate, best):
                best = candidate

    assert best is not None
    local_methods = [best["method_key"]] + [
        method for method in methods if method != best["method_key"]
    ][:3]
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
            candidate = enrich_plan_metrics(
                candidate,
                method,
                machine_type,
                **metric_kwargs,
            )
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
    initial_plan: dict[str, Any] | None = None,
    candidate_callback: Any = None,
    known_orders: set | None = None,
    signature_key: Any = None,
    **metric_kwargs: Any,
) -> dict[str, Any]:
    started = time.monotonic()
    best = deepcopy(initial_plan) if initial_plan is not None else auto_pro(
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type,
        **metric_kwargs,
    )
    attempts = int(best.get("attempts") or 0)
    methods = _candidate_methods(machine_type)
    rng = random.Random(
        _seed_for_problem(pieces, board_w_cm, board_h_cm, kerf_cm)
    )
    deadline = started + (max(0.0,float(time_limit_sec)) if initial_plan is not None else max(0.5,float(time_limit_sec or 10.0)))

    seen_orders = known_orders if known_orders is not None else set()
    while attempts < max_attempts and time.monotonic() < deadline:
        method = methods[attempts % len(methods)]
        sequence = deepcopy(pieces)
        rng.shuffle(sequence)
        signature = (method, tuple(int(piece["id"]) for piece in sequence))
        if signature in seen_orders:
            attempts += 1
            continue
        seen_orders.add(signature)
        if attempts % 3 == 0 and len(sequence) > 4:
            large = order_pieces(sequence, "area_desc")
            split = max(1, len(large) // 4)
            head = large[:split]
            tail = large[split:]
            rng.shuffle(tail)
            sequence = head + tail
        if signature_key is not None:
            actual_signature = signature_key(method,sequence)
            if actual_signature in seen_orders:
                attempts += 1
                continue
            seen_orders.add(actual_signature)
        candidate = _run_preordered_method(
            sequence,
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            method,
            f"seeded_restart_{attempts}",
        )
        candidate = enrich_plan_metrics(
            candidate,
            method,
            machine_type,
            **metric_kwargs,
        )
        attempts += 1
        if _candidate_is_better(candidate, best):
            best = candidate
            if candidate_callback is not None:
                candidate_callback(candidate)

    best["optimization_mode"] = DEEP_SEARCH
    best["method_label"] = "بحث معمق اختار: " + best["method_label"].split(
        "اختار: ", 1
    )[-1]
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
    used_bins = [model.new_bool_var(f"bin_used_{index}") for index in range(max_bins)]
    placements: list[dict[str, Any]] = []
    x_intervals: list[list[Any]] = [[] for _ in range(max_bins)]
    y_intervals: list[list[Any]] = [[] for _ in range(max_bins)]

    for index, piece in enumerate(pieces):
        width_value = max(1, int(round(num(piece.get("width_cm")) * 10)))
        height_value = max(1, int(round(num(piece.get("length_cm")) * 10)))
        allow_rotation = bool(piece.get("allow_rotation")) and width_value != height_value

        if allow_rotation:
            rotate = model.new_bool_var(f"rot_{index}")
            width = model.new_int_var(
                min(width_value, height_value),
                max(width_value, height_value),
                f"width_{index}",
            )
            height = model.new_int_var(
                min(width_value, height_value),
                max(width_value, height_value),
                f"height_{index}",
            )
            model.add_allowed_assignments(
                [rotate, width, height],
                [
                    (0, width_value, height_value),
                    (1, height_value, width_value),
                ],
            )
        else:
            rotate = None
            width = model.new_constant(width_value)
            height = model.new_constant(height_value)

        packed_width = model.new_int_var(
            min(width_value, height_value) + kerf
            if allow_rotation
            else width_value + kerf,
            max(width_value, height_value) + kerf
            if allow_rotation
            else width_value + kerf,
            f"packed_width_{index}",
        )
        packed_height = model.new_int_var(
            min(width_value, height_value) + kerf
            if allow_rotation
            else height_value + kerf,
            max(width_value, height_value) + kerf
            if allow_rotation
            else height_value + kerf,
            f"packed_height_{index}",
        )
        model.add(packed_width == width + kerf)
        model.add(packed_height == height + kerf)

        presence: list[Any] = []
        xs: list[Any] = []
        ys: list[Any] = []
        for bin_index in range(max_bins):
            present = model.new_bool_var(f"present_{index}_{bin_index}")
            x = model.new_int_var(0, board_w, f"x_{index}_{bin_index}")
            y = model.new_int_var(0, board_h, f"y_{index}_{bin_index}")
            x_end = model.new_int_var(
                0,
                board_w + kerf,
                f"x_end_{index}_{bin_index}",
            )
            y_end = model.new_int_var(
                0,
                board_h + kerf,
                f"y_end_{index}_{bin_index}",
            )
            x_interval = model.new_optional_interval_var(
                x,
                packed_width,
                x_end,
                present,
                f"xi_{index}_{bin_index}",
            )
            y_interval = model.new_optional_interval_var(
                y,
                packed_height,
                y_end,
                present,
                f"yi_{index}_{bin_index}",
            )
            model.add(x + width <= board_w).only_enforce_if(present)
            model.add(y + height <= board_h).only_enforce_if(present)
            model.add(x_end <= board_w + kerf).only_enforce_if(present)
            model.add(y_end <= board_h + kerf).only_enforce_if(present)
            model.add_implication(present, used_bins[bin_index])
            presence.append(present)
            xs.append(x)
            ys.append(y)
            x_intervals[bin_index].append(x_interval)
            y_intervals[bin_index].append(y_interval)

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

    for bin_index in range(max_bins):
        model.add_no_overlap_2d(
            x_intervals[bin_index],
            y_intervals[bin_index],
        )
        model.add(
            sum(placement["presence"][bin_index] for placement in placements)
            >= used_bins[bin_index]
        )
        if bin_index + 1 < max_bins:
            model.add(used_bins[bin_index] >= used_bins[bin_index + 1])

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
        for bin_index, present in enumerate(data["presence"]):
            if solver.boolean_value(present):
                chosen = bin_index
                break
        if chosen is None:
            continue
        width_mm = solver.value(data["width"])
        height_mm = solver.value(data["height"])
        rotated = bool(
            data["rotate"] is not None
            and solver.boolean_value(data["rotate"])
        )
        placed = {
            "id": piece["id"],
            "label": piece["label"],
            "source_piece_no": piece["source_piece_no"],
            "copy_no": piece["copy_no"],
            "piece_instance_id": str(piece.get("piece_instance_id") or "").strip(),
            "resource_kind": piece.get("resource_kind") or "FULL_BOARD",
            "offcut_source_party": piece.get("offcut_source_party") or "UNASSIGNED",
            "offcut_execution_party": piece.get("offcut_execution_party") or "UNASSIGNED",
            "group_qty": piece["group_qty"],
            "x": solver.value(data["xs"][chosen]) / 10,
            "y": solver.value(data["ys"][chosen]) / 10,
            "w": width_mm / 10,
            "h": height_mm / 10,
            "original_w": num(piece.get("width_cm")),
            "original_h": num(piece.get("length_cm")),
            "piece_type": piece.get("piece_type") or "Regular",
            "clipped_corner_position": piece.get("clipped_corner_position") or "",
            "clipped_corner_width_cm": num(piece.get("clipped_corner_width_cm")),
            "clipped_corner_length_cm": num(piece.get("clipped_corner_length_cm")),
            "special_shape_geometry_json": piece.get("special_shape_geometry_json") or "",
            "rotated": rotated,
            "area_m2": num(piece.get("area_m2")),
            "notes": piece.get("notes") or "",
            **liner_metadata(piece),
            **double_edge_metadata(piece),
            **_edge_metadata(piece),
        }
        record_glass_opening(placed, piece, rotated=rotated)
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
    plan = evaluate_plan(
        raw,
        pieces,
        board_w_cm,
        board_h_cm,
        "CP-SAT 2D",
        "Optimal Search",
        50,
    )
    plan["solver_status"] = (
        "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
    )
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
        best["method_label"] = "بحث أمثل للمنشار اللوحي: " + best[
            "method_label"
        ].split(": ", 1)[-1]
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
    remaining = max(
        0.5,
        float(time_limit_sec) - (time.monotonic() - started),
    )

    if (
        len(pieces) <= max(1, int(exact_piece_limit))
        and _cp_sat_available()
        and not heuristic.get("unplaced")
    ):
        exact = _solve_cp_sat(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            max(1, len(heuristic.get("sheets") or [])),
            remaining,
        )
        if exact is not None:
            validation_errors = validate_plan(
                exact,
                pieces,
                board_w_cm,
                board_h_cm,
            )
            if not validation_errors:
                exact = enrich_plan_metrics(
                    exact,
                    "Optimal Search",
                    machine_type,
                    **metric_kwargs,
                )
                if len(exact.get("sheets") or []) < len(
                    best.get("sheets") or []
                ) or _candidate_is_better(exact, best):
                    best = exact

    best["optimization_mode"] = OPTIMAL_SEARCH
    best["attempts"] = int(best.get("attempts") or 0)
    best["search_elapsed_sec"] = round(time.monotonic() - started, 3)
    best["search_time_limit_sec"] = float(time_limit_sec)
    if best.get("method_key") == "Optimal Search":
        status_ar = (
            "مثبت كحل أمثل"
            if best.get("solver_status") == "OPTIMAL"
            else "أفضل حل وجده المحرك ضمن المهلة"
        )
        best["method_label"] = f"CP-SAT - {status_ar}"
    elif not best.get("solver_status"):
        best["solver_status"] = "HEURISTIC_FALLBACK"
        best["method_label"] = (
            "بحث أمثل - أفضل حل ضمن المهلة: "
            + best["method_label"].split(": ", 1)[-1]
        )
    return best


def _layout_signature(plan: dict[str, Any]) -> str:
    from .plan_portfolio import geometry_signature
    return geometry_signature(plan)


def smart_search(
    pieces: list[dict[str, Any]], board_w_cm: float, board_h_cm: float,
    kerf_cm: float, machine_type: str = "Auto", time_limit_sec: float = 10.0,
    exact_piece_limit: int = 40, mirroring_allowed: bool = False,
    seed_plans: tuple[dict[str, Any], ...] = (), search_round: int = 0,
    **metric_kwargs: Any,
) -> dict[str, Any]:
    """Finish diverse seeds before selection; retain five distinct valid finals.

    Pro orders and deterministic Deep restarts share one deadline. Short batches
    promote a rectangular leader and a different layout, rather than discarding
    all but a rectangular winner before shape/Glass passes. Warm finals survive
    every continuation even if the next search produces no improvement.
    """
    from .evaluation import placement_permission_errors
    started = time.monotonic()
    budget = max(0.0, float(time_limit_sec))
    deadline = started + budget
    metric_kwargs = {"min_remnant_width_cm":30.0,"min_remnant_length_cm":30.0,
                     "min_remnant_area_m2":.09, **metric_kwargs}
    from .plan_portfolio import retain_diverse_finals, nesting_coverage
    accepted_ranks = {}
    rejected_finals = {}
    finals: list[dict[str, Any]] = []
    def offer(candidate):
        from .plan_portfolio import manufacturing_export_rejection
        rejection = manufacturing_export_rejection(candidate)
        if rejection:
            rejected_finals[rejection] = rejected_finals.get(rejection,0)+1
            return
        if validate_plan(candidate,pieces,board_w_cm,board_h_cm,kerf_cm=kerf_cm) or placement_permission_errors(
            candidate,pieces,mirroring_allowed=mirroring_allowed):
            rejected_finals['validation_or_permission'] = rejected_finals.get('validation_or_permission',0)+1
            return
        signature = _layout_signature(candidate)
        rank=tuple(candidate['industrial_rank'])
        accepted_ranks[signature] = min(accepted_ranks.get(signature,rank),rank)
        existing = next((p for p in finals if _layout_signature(p)==signature),None)
        if existing is not None:
            if not _candidate_is_better(candidate,existing):
                return
            finals.remove(existing)
        finals.append(candidate)
        finals[:] = retain_diverse_finals(finals)

    for plan in seed_plans[:5]:
        if all(abs(float(sh.get('w',0))-board_w_cm)<1e-8 and abs(float(sh.get('h',0))-board_h_cm)<1e-8
               for sh in plan.get('sheets') or []):
            offer(enrich_plan_metrics(plan,str(plan.get('method_key') or ''),machine_type,**metric_kwargs))
    seed = (deepcopy(finals[0]) if finals else
            auto_fast(pieces,board_w_cm,board_h_cm,kerf_cm,machine_type,**metric_kwargs))
    completed, attempts, trials = 0, int(seed.get('attempts') or 0), 0
    def finish(raw, share):
        nonlocal completed
        end = min(deadline,time.monotonic()+max(0,share))
        result = _finish_plan_search(raw,pieces,board_w_cm,board_h_cm,kerf_cm,machine_type,
            max(0,end-time.monotonic()),mirroring_allowed,metric_kwargs,
            search_deadline=end,require_importable_geometry=True,final_candidate_callback=offer)
        completed += 1
        offer(result)
        return result
    initial = finish(seed,min(budget*.2,max(0,deadline-time.monotonic())))
    seed_rank = list(initial.get('industrial_rank') or [])
    from .joint_nesting import has_joint_sources, joint_nesting_candidates
    joint_diagnostics = None
    if finals and has_joint_sources(pieces, machine_type) and time.monotonic() < deadline:
        joint, joint_diagnostics = joint_nesting_candidates(seed, initial, pieces,
            board_w_cm, board_h_cm, kerf_cm, machine_type=machine_type,
            mirroring_allowed=mirroring_allowed,
            deadline=min(deadline, time.monotonic()+min(1.5, budget*.2)), metric_kwargs=metric_kwargs)
        for candidate in joint:
            offer(candidate)
    from .geometry_nesting import geometry_first_candidates, has_shape_sources
    shape_diagnostics = None
    if has_shape_sources(pieces,machine_type) and time.monotonic()<deadline:
        shaped,shape_diagnostics = geometry_first_candidates(seed,pieces,board_w_cm,board_h_cm,kerf_cm,
            machine_type=machine_type,mirroring_allowed=mirroring_allowed,
            deadline=min(deadline,time.monotonic()+min(3.0,budget*.35)),metric_kwargs=metric_kwargs)
        for candidate in shaped:
            offer(candidate)
    late_completions = 0
    completed_topologies = {_layout_signature(p) for p in finals if nesting_coverage(p)}
    methods = _candidate_methods(machine_type)
    def packing_signature(method,sequence):
        _,packer,args,_ = METHOD_CONFIGS[method]
        return packer.__name__,args,tuple(int(p['id']) for p in sequence)
    seen_orders = set() if seed_plans else {
        packing_signature(m,sort_pieces(pieces,STRATEGY_BY_KEY[m].sort_method)) for m in methods}
    seen_layouts = {_layout_signature(seed)}
    rng = random.Random(_seed_for_problem(pieces,board_w_cm,board_h_cm,kerf_cm)+int(search_round)*104729)
    def sequences():
        local = _local_sequences(finals[0] if finals else initial,pieces)
        cycles = [entry for entry in local if entry[0].startswith('dimension_cycle_')]
        yield from cycles[1:]+cycles[:1]
        for strategy in ORDERING_STRATEGIES:
            yield strategy,order_pieces(pieces,strategy)
        yield from (entry for entry in local if not entry[0].startswith('dimension_cycle_'))
        for index in range(500):
            sequence = list(pieces)
            rng.shuffle(sequence)
            yield f'seeded_restart_{index}',sequence
    batch = []
    def finish_batch():
        nonlocal late_completions
        if not batch:
            return
        batch.sort(key=lambda p:tuple(p['industrial_rank']))
        # Retain diversity even when the second seed has a worse rectangle rank.
        choices = [batch[0]]
        if len(batch)>1:
            choices.append(batch[-1] if any(p.get('piece_type') in {'Glass','L-Shaped Corner','Clipped Corner'} for p in pieces)
                           else batch[min(1,len(batch)-1)])
        for raw in choices:
            if completed>=8 or time.monotonic()>=deadline:
                break
            finished = finish(raw,max(0,deadline-time.monotonic())/max(2,16-completed))
            coverage = nesting_coverage(finished)
            shape_signature = _layout_signature(finished)
            if (late_completions<2 and coverage & {'L-Shaped Corner','Clipped Corner'}
                    and shape_signature not in completed_topologies
                    and len(finished.get('sheets') or [])<=len(finals[0]['sheets'])
                    and has_joint_sources(pieces,machine_type) and time.monotonic()<deadline):
                from .joint_nesting import complete_shape_candidate
                late = complete_shape_candidate(finished,pieces,board_w_cm,board_h_cm,kerf_cm,
                    machine_type=machine_type,mirroring_allowed=mirroring_allowed,
                    deadline=min(deadline,time.monotonic()+min(.3,budget*.05)),metric_kwargs=metric_kwargs)
                offer(enrich_plan_metrics(late,str(late.get('method_key') or ''),machine_type,**metric_kwargs))
                completed_topologies.add(shape_signature)
                late_completions+=1
        batch.clear()
    for index,(name,sequence) in enumerate(sequences()):
        selected = [methods[0]] if name.startswith('dimension_cycle_') else list(dict.fromkeys(
            [methods[0],seed['method_key'],methods[index%len(methods)]]))
        for method in selected:
            if trials>=500 or completed>=8 or time.monotonic()>=deadline:
                break
            signature = packing_signature(method,sequence)
            if signature in seen_orders:
                continue
            seen_orders.add(signature)
            raw = _run_preordered_method(sequence,pieces,board_w_cm,board_h_cm,kerf_cm,method,name)
            trials += 1
            attempts += 1
            signature = _layout_signature(raw)
            if signature in seen_layouts:
                continue
            seen_layouts.add(signature)
            batch.append(enrich_plan_metrics(raw,method,machine_type,**metric_kwargs))
            if len(batch)>=12:
                finish_batch()
        if trials>=500 or completed>=8 or time.monotonic()>=deadline:
            break
    finish_batch()
    if time.monotonic()<deadline and finals:
        def deep_candidate(raw):
            if completed<16 and time.monotonic()<deadline:
                finish(raw,min(.5,max(0,deadline-time.monotonic())*.2))
        warm = dict(finals[0])
        warm['attempts'] = 0
        deep = deep_search(pieces,board_w_cm,board_h_cm,kerf_cm,machine_type,
            max(0,deadline-time.monotonic()),max_attempts=max(0,500-trials),
            initial_plan=warm,candidate_callback=deep_candidate,known_orders=seen_orders,
            signature_key=packing_signature,**metric_kwargs)
        attempts += int(deep.get('attempts') or 0)
        if completed<16 and time.monotonic()<deadline:
            finish(deep,max(0,deadline-time.monotonic())*.5)
    best = finals[0] if finals else initial
    remaining = deadline-time.monotonic()
    if (remaining>.01 and finals and machine_type!='Panel Saw' and 0<len(pieces)<=exact_piece_limit
        and len(best.get('sheets') or [])>1 and all((p.get('piece_type') or 'Regular')=='Regular' for p in pieces)
        and _cp_sat_available()):
        exact = _solve_cp_sat(pieces,board_w_cm,board_h_cm,kerf_cm,len(best['sheets'])-1,max(.001,deadline-time.monotonic()))
        if exact is not None:
            finish(enrich_plan_metrics(exact,OPTIMAL_SEARCH,machine_type,**metric_kwargs),max(0,deadline-time.monotonic()))
    best = dict(finals[0] if finals else initial)
    from .plan_portfolio import manufacturing_export_rejection
    if not finals and manufacturing_export_rejection(best):
        # Keep the established incomplete-plan failure contract. Returning the
        # unprovable baseline here would falsely certify it in the Application.
        best = enrich_plan_metrics(dict(best,sheets=[],unplaced=deepcopy(pieces)),
            str(best.get('method_key') or ''),machine_type,**metric_kwargs)
    best['optimization_mode'] = SMART_SEARCH
    best['attempts'] = attempts
    best['search_elapsed_sec'] = round(time.monotonic()-started,3)
    best['search_time_limit_sec'] = budget
    best['smart_search'] = dict(auto_seed_rank=seed_rank,completed_candidates=completed,packing_trials=trials,
        unique_candidates=len(finals), search_round=search_round,
        valid_final_ranks=[list(p['industrial_rank']) for p in finals],
        deadline_overrun_sec=round(max(0,time.monotonic()-deadline),3))
    best['smart_search']['portfolio'] = dict(valid_unique_completed=len(accepted_ranks),
        dominated_by_winner=sum(rank>tuple(best['industrial_rank']) for rank in accepted_ranks.values()),
        pruned_unique=len(set(accepted_ranks)-{_layout_signature(p) for p in finals}),
        coverage=[sorted(nesting_coverage(p)) for p in finals],rejections=rejected_finals)
    if shape_diagnostics is not None:
        shape_diagnostics['late_joint_completions']=late_completions
        for piece_id,trace in shape_diagnostics['piece_trace'].items():
            trace['reserved_by_initial_glass']=any(int(p['id'])==piece_id and p.get('glass_host_piece_id')
                for s in initial.get('sheets') or [] for p in s['pieces'])
            trace['portfolio_formations']=sum(any(piece_id in ids for ids in
                (p.get('shape_nesting_diagnostics') or {}).get('formation_ids') or []) for p in finals)
        shape_diagnostics['final_plans_using']={kind:sum(kind in nesting_coverage(p) for p in finals)
            for kind in ('L-Shaped Corner','Clipped Corner','Glass','Joint')}
        best['smart_search']['shape_first']=shape_diagnostics
    if joint_diagnostics is not None:
        joint_diagnostics.update(glass_guests=sum(bool(p.get('glass_host_piece_id')) for s in best['sheets'] for p in s['pieces']),
            shape_void_guests=len((best.get('shape_nesting_diagnostics') or {}).get('void_guests') or []),
            boards_before_after=[len(initial['sheets']), len(best['sheets'])])
        best['smart_search']['joint'] = joint_diagnostics
    best['smart_candidates'] = [dict(p) for p in finals]
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
    mirroring_allowed: bool = False,
    seed_plans: tuple[dict[str, Any], ...] = (),
    search_round: int = 0,
) -> dict[str, Any]:
    mode = selected_mode or AUTO_FAST
    metric_kwargs = {
        "min_remnant_width_cm": min_remnant_width_cm,
        "min_remnant_length_cm": min_remnant_length_cm,
        "min_remnant_area_m2": min_remnant_area_m2,
    }

    if mode == SMART_SEARCH:
        return smart_search(
            pieces, board_w_cm, board_h_cm, kerf_cm, machine_type, time_limit_sec,
            exact_piece_limit, mirroring_allowed, seed_plans, search_round, **metric_kwargs,
        )
    if mode == AUTO_FAST:
        baseline = auto_fast(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type,
            **metric_kwargs,
        )
    elif mode == AUTO_PRO:
        baseline = auto_pro(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type,
            **metric_kwargs,
        )
    elif mode == DEEP_SEARCH:
        baseline = deep_search(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type,
            time_limit_sec,
            **metric_kwargs,
        )
    elif mode == OPTIMAL_SEARCH:
        baseline = optimal_search(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            machine_type,
            time_limit_sec,
            exact_piece_limit,
            **metric_kwargs,
        )
    else:
        baseline = run_single_method(
            pieces,
            board_w_cm,
            board_h_cm,
            kerf_cm,
            mode,
        )
        baseline = enrich_plan_metrics(
            baseline,
            mode,
            machine_type,
            **metric_kwargs,
        )
        baseline["optimization_mode"] = "Manual"
        baseline["attempts"] = 1

    return _finish_plan_search(
        baseline, pieces, board_w_cm, board_h_cm, kerf_cm, machine_type,
        time_limit_sec, mirroring_allowed, metric_kwargs,
    )


def _finish_plan_search(
    baseline: dict[str, Any], pieces: list[dict[str, Any]],
    board_w_cm: float, board_h_cm: float, kerf_cm: float,
    machine_type: str, time_limit_sec: float, mirroring_allowed: bool,
    metric_kwargs: dict[str, Any], *, search_deadline: float | None = None,
    require_importable_geometry: bool = False,
    final_candidates: list[dict[str, Any]] | None = None,
    final_candidate_callback: Any = None,
) -> dict[str, Any]:
    from .glass_opening_nesting import nest_glass_openings
    from .plan_search import improve_plan_search
    from .shape_aware_nesting import apply_shape_aware_nesting

    # Post-passes may annotate their input even when they keep its geometry.
    # Preserve each candidate, including its diagnostics, for final selection.
    if search_deadline is None:
        search_deadline = time.monotonic() + max(0.0, float(time_limit_sec))
    nested = nest_glass_openings(
        deepcopy(baseline),
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type=machine_type,
        time_limit_sec=time_limit_sec,
        **metric_kwargs,
    )
    shaped = apply_shape_aware_nesting(
        deepcopy(nested),
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        mirroring_allowed=mirroring_allowed,
        machine_type=machine_type,
        time_limit_sec=max(0.0, search_deadline - time.monotonic()),
        formation_alternatives=True,
        quarter_turns_only=require_importable_geometry,
        **metric_kwargs,
    )
    from .evaluation import placement_permission_errors

    improved = improve_plan_search(
        deepcopy(shaped),
        pieces,
        board_w_cm,
        board_h_cm,
        kerf_cm,
        machine_type=machine_type,
        time_limit_sec=max(0.0, search_deadline - time.monotonic()),
        deadline_monotonic=search_deadline,
        mirroring_allowed=mirroring_allowed,
        **metric_kwargs,
    )
    best: dict[str, Any] | None = None

    def search_candidates():
        # The final gate below proves the seed; this iterator only generates
        # candidates and never replaces its selection decision.
        yield from (baseline, nested, shaped)
        previous_best = best
        yield improved
        if (
            previous_best is None
            or _candidate_is_better(best, previous_best)
            or previous_best.get("sheets") == shaped.get("sheets")
        ):
            return
        ranked_shape = enrich_plan_metrics(
            shaped, str(shaped.get("method_key") or ""), machine_type, **metric_kwargs,
        )
        if not _candidate_is_better(previous_best, ranked_shape):
            return
        remaining = min(1.0, search_deadline - time.monotonic())
        if remaining <= 0 or machine_type == "Panel Saw":
            return
        yield improve_plan_search(
            deepcopy(previous_best), pieces, board_w_cm, board_h_cm, kerf_cm,
            machine_type=machine_type, time_limit_sec=remaining,
            mirroring_allowed=mirroring_allowed,
            deadline_monotonic=min(search_deadline, time.monotonic() + remaining),
            **metric_kwargs,
        )

    for candidate in search_candidates():
        # Strict import cannot prove non-quarter void guests or machining marks
        # inside Glass guests. Keep a proven earlier stage; legacy modes and
        # all export/import contracts remain intact.
        from .plan_portfolio import manufacturing_export_rejection
        if require_importable_geometry and manufacturing_export_rejection(candidate):
            continue
        candidate = enrich_plan_metrics(
            candidate,
            str(candidate.get("method_key") or ""),
            machine_type,
            **metric_kwargs,
        )
        if (final_candidates is not None or final_candidate_callback is not None) and not (validate_plan(
            candidate,pieces,board_w_cm,board_h_cm,kerf_cm=kerf_cm) or placement_permission_errors(
                candidate,pieces,mirroring_allowed=mirroring_allowed)):
            if final_candidate_callback is not None:
                final_candidate_callback(candidate)
            if final_candidates is not None:
                signature = _layout_signature(candidate)
                same = next((p for p in final_candidates if _layout_signature(p)==signature),None)
                if same is None or _candidate_is_better(candidate,same):
                    if same is not None:
                        final_candidates.remove(same)
                    final_candidates.append(candidate)
                    from .plan_portfolio import retain_diverse_finals
                    final_candidates[:] = retain_diverse_finals(final_candidates)
        # Keep post-pass behavior on an exact industrial tie, never at a cost
        # in boards, reusable offcut, or manufacturing complexity.
        if best is not None and _candidate_is_better(best, candidate):
            continue
        # A no-op post-pass may change diagnostics but shares every input to
        # both validators with the already proven best layout.
        same_layout = best is not None and (
            candidate.get("sheets") == best.get("sheets")
            and candidate.get("unplaced") == best.get("unplaced")
        )
        if not same_layout and (validate_plan(
            candidate, pieces, board_w_cm, board_h_cm, kerf_cm=kerf_cm,
        ) or placement_permission_errors(
            candidate,
            pieces,
            mirroring_allowed=mirroring_allowed,
        )):
            continue
        best = candidate
    # Keep the original failure payload when no complete valid plan exists;
    # callers need it for Adaptive Trim probes and explicit validation errors.
    return best if best is not None else baseline


__all__ = [
    "ADVANCED_MODES",
    "AUTO_FAST",
    "AUTO_PRO",
    "DEEP_SEARCH",
    "GUILLOTINE_METHODS",
    "MACHINE_TYPES",
    "OPTIMAL_SEARCH",
    "SMART_SEARCH",
    "smart_search",
    "ORDERING_STRATEGIES",
    "auto_fast",
    "auto_pro",
    "deep_search",
    "enrich_plan_metrics",
    "optimal_search",
    "optimize_plan",
    "order_pieces",
]
