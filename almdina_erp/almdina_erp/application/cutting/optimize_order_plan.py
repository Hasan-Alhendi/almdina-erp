from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.costing import round_value


_ADAPTIVE_TRIM_PRECISION_CM = 0.01


class CuttingPlanEngine(Protocol):
    """Port implemented by the current optimization-engine adapter."""

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        *,
        selected_mode: str,
        machine_type: str,
        time_limit_sec: float,
        exact_piece_limit: int,
        min_remnant_width_cm: float,
        min_remnant_length_cm: float,
        min_remnant_area_m2: float,
    ) -> dict[str, Any]: ...

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class BoardGeometry:
    full_width_cm: float
    full_length_cm: float
    trim_cm: float
    kerf_cm: float

    @property
    def usable_width_cm(self) -> float:
        return self.full_width_cm - (self.trim_cm * 2)

    @property
    def usable_length_cm(self) -> float:
        return self.full_length_cm - (self.trim_cm * 2)


@dataclass(frozen=True, slots=True)
class OptimizerOptions:
    selected_mode: str
    machine_type: str
    time_limit_sec: float
    exact_piece_limit: int
    min_remnant_width_cm: float
    min_remnant_length_cm: float
    min_remnant_area_m2: float


@dataclass(frozen=True, slots=True)
class OptimizeOrderPlanCommand:
    engine_version: str
    input_fingerprint: str
    board: BoardGeometry
    optimizer: OptimizerOptions
    piece_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class OptimizationOutcome:
    snapshot: dict[str, Any]
    packing_score: str
    required_boards: int
    method_label: str
    expanded_pieces: tuple[dict[str, Any], ...]


def optimize_order_plan(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
) -> OptimizationOutcome:
    """Optimize with the configured trim, relaxing it only when production improves."""

    rows = [dict(row) for row in command.piece_rows]
    expanded = engine.expand_pieces(rows)
    configured = _optimize_with_board(
        command,
        expanded_pieces=expanded,
        board=command.board,
        engine=engine,
    )

    if not _should_probe_smaller_trim(
        command.board,
        expanded_pieces=expanded,
        outcome=configured,
    ):
        return configured

    zero_trim_board = _board_with_trim(command.board, 0.0)
    zero_trim = _optimize_with_board(
        command,
        expanded_pieces=expanded,
        board=zero_trim_board,
        engine=engine,
    )
    target_key = _production_key(zero_trim)
    if target_key >= _production_key(configured):
        return configured

    best = zero_trim
    low_units = 1
    high_units = _trim_units(command.board.trim_cm)

    while low_units <= high_units:
        mid_units = (low_units + high_units) // 2
        candidate = _optimize_with_board(
            command,
            expanded_pieces=expanded,
            board=_board_with_trim(
                command.board,
                mid_units * _ADAPTIVE_TRIM_PRECISION_CM,
            ),
            engine=engine,
        )
        if _production_key(candidate) <= target_key:
            best = candidate
            low_units = mid_units + 1
        else:
            high_units = mid_units - 1

    return best


def _optimize_with_board(
    command: OptimizeOrderPlanCommand,
    *,
    expanded_pieces: list[dict[str, Any]],
    board: BoardGeometry,
    engine: CuttingPlanEngine,
) -> OptimizationOutcome:
    plan = engine.optimize(
        expanded_pieces,
        board.usable_width_cm,
        board.usable_length_cm,
        board.kerf_cm,
        selected_mode=command.optimizer.selected_mode,
        machine_type=command.optimizer.machine_type,
        time_limit_sec=command.optimizer.time_limit_sec,
        exact_piece_limit=command.optimizer.exact_piece_limit,
        min_remnant_width_cm=command.optimizer.min_remnant_width_cm,
        min_remnant_length_cm=command.optimizer.min_remnant_length_cm,
        min_remnant_area_m2=command.optimizer.min_remnant_area_m2,
    )
    validation_errors = engine.validate(
        plan,
        expanded_pieces,
        board.usable_width_cm,
        board.usable_length_cm,
    )

    metrics = dict(plan.get("industrial_metrics") or {})
    required_boards = len(plan.get("sheets") or [])
    waste_area = max(0.0, _number(plan.get("waste_area_m2")))
    total_board_area = _number(plan.get("total_board_area_m2"))
    waste_percent = round_value(
        (waste_area / total_board_area * 100) if total_board_area else 0,
        2,
    )
    method_label = str(plan.get("method_label") or "")

    snapshot = {
        "engine_version": command.engine_version,
        "input_fingerprint": command.input_fingerprint,
        "optimization_mode": (
            plan.get("optimization_mode")
            or command.optimizer.selected_mode
            or "Auto Pro"
        ),
        "machine_type": command.optimizer.machine_type or "Auto",
        "method_key": plan.get("method_key") or "",
        "method_label": method_label,
        "ordering_strategy": plan.get("ordering_strategy") or "",
        "score": plan.get("score"),
        "industrial_metrics": metrics,
        "industrial_rank": list(plan.get("industrial_rank") or []),
        "attempts": _integer(plan.get("attempts")),
        "search_elapsed_sec": _number(plan.get("search_elapsed_sec")),
        "search_time_limit_sec": _number(plan.get("search_time_limit_sec")),
        "solver_status": plan.get("solver_status") or "",
        "solver_wall_time_sec": _number(plan.get("solver_wall_time_sec")),
        "full_board_width_cm": board.full_width_cm,
        "full_board_length_cm": board.full_length_cm,
        "usable_board_width_cm": board.usable_width_cm,
        "usable_board_length_cm": board.usable_length_cm,
        "kerf_cm": board.kerf_cm,
        "trim_cm": board.trim_cm,
        "configured_trim_cm": command.board.trim_cm,
        "trim_adjusted": board.trim_cm < command.board.trim_cm,
        "used_area_m2": plan.get("used_area_m2"),
        "total_board_area_m2": plan.get("total_board_area_m2"),
        "waste_area_m2": plan.get("waste_area_m2"),
        "special_shape_raw_summary": summarize_special_shapes(
            expanded_pieces,
            plan,
        ),
        "sheets": plan.get("sheets") or [],
        "unplaced": plan.get("unplaced") or [],
        "validation": {
            "is_valid": not validation_errors,
            "errors": list(validation_errors),
        },
    }

    packing_score = (
        f"ألواح: {required_boards} | هدر: {waste_percent}% | "
        f"قصات تقديرية: {_integer(metrics.get('estimated_cut_count'))} | "
        "أكبر بقايا مفيدة: "
        f"{round_value(metrics.get('largest_reusable_free_area_m2') or 0, 3)} م² | "
        f"محاولات: {_integer(plan.get('attempts'))} | الخوارزمية: {method_label}"
    )

    return OptimizationOutcome(
        snapshot=snapshot,
        packing_score=packing_score,
        required_boards=required_boards,
        method_label=method_label,
        expanded_pieces=tuple(expanded_pieces),
    )


def _should_probe_smaller_trim(
    board: BoardGeometry,
    *,
    expanded_pieces: list[dict[str, Any]],
    outcome: OptimizationOutcome,
) -> bool:
    if board.trim_cm <= 0:
        return False

    validation = outcome.snapshot.get("validation") or {}
    if not validation.get("is_valid") or outcome.snapshot.get("unplaced"):
        return True

    if outcome.required_boards <= 1:
        return False

    lower_bound = _regular_piece_board_lower_bound(
        board,
        expanded_pieces=expanded_pieces,
    )
    return lower_bound is None or outcome.required_boards > lower_bound


def _regular_piece_board_lower_bound(
    board: BoardGeometry,
    *,
    expanded_pieces: list[dict[str, Any]],
) -> int | None:
    """Return a safe area lower bound, or None for non-rectangular demand."""

    full_board_area_cm2 = board.full_width_cm * board.full_length_cm
    if full_board_area_cm2 <= 0:
        return None

    demanded_area_cm2 = 0.0
    for piece in expanded_pieces:
        if (piece.get("piece_type") or "Regular") != "Regular":
            return None
        demanded_area_cm2 += max(0.0, _number(piece.get("width_cm"))) * max(
            0.0,
            _number(piece.get("length_cm")),
        )

    if demanded_area_cm2 <= 0:
        return None
    return max(1, math.ceil(demanded_area_cm2 / full_board_area_cm2))


def _production_key(outcome: OptimizationOutcome) -> tuple[int, int, int]:
    validation = outcome.snapshot.get("validation") or {}
    return (
        0 if validation.get("is_valid") else 1,
        len(outcome.snapshot.get("unplaced") or []),
        outcome.required_boards,
    )


def _trim_units(trim_cm: float) -> int:
    return max(0, int(math.floor((trim_cm / _ADAPTIVE_TRIM_PRECISION_CM) + 1e-9)))


def _board_with_trim(board: BoardGeometry, trim_cm: float) -> BoardGeometry:
    return BoardGeometry(
        full_width_cm=board.full_width_cm,
        full_length_cm=board.full_length_cm,
        trim_cm=max(0.0, trim_cm),
        kerf_cm=board.kerf_cm,
    )


def summarize_special_shapes(
    expanded_pieces: list[dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, int | bool]:
    requested_ids = {
        _integer(piece.get("id"))
        for piece in expanded_pieces
        if (piece.get("piece_type") or "Regular") == "Special"
    }
    placed_ids = {
        _integer(piece.get("id"))
        for sheet in (plan.get("sheets") or [])
        for piece in (sheet.get("pieces") or [])
        if (piece.get("piece_type") or "Regular") == "Special"
    }
    unplaced_ids = {
        _integer(piece.get("id"))
        for piece in (plan.get("unplaced") or [])
        if (piece.get("piece_type") or "Regular") == "Special"
    }
    return {
        "requested": len(requested_ids),
        "placed": len(requested_ids.intersection(placed_ids)),
        "unplaced": len(requested_ids.intersection(unplaced_ids)),
        "complete": requested_ids.issubset(placed_ids) and not unplaced_ids,
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


__all__ = [
    "BoardGeometry",
    "CuttingPlanEngine",
    "OptimizationOutcome",
    "OptimizeOrderPlanCommand",
    "OptimizerOptions",
    "optimize_order_plan",
    "summarize_special_shapes",
]
