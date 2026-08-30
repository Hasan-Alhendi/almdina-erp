from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AdaptiveTrimDecision,
    AppliedTrim,
    PlanQuality,
    TRIM_PRECISION_CM,
    resolve_adaptive_trim,
)
from almdina_erp.almdina_erp.domain.orders.costing import round_value


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
class AppliedMargins(AppliedTrim):
    """Compatibility surface for callers using the pre-ALMADINA-138 API."""

    def usable_width_cm(self, board: BoardGeometry) -> float:
        return super().usable_width_cm(full_width_cm=board.full_width_cm)

    def usable_length_cm(self, board: BoardGeometry) -> float:
        return super().usable_length_cm(full_length_cm=board.full_length_cm)


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
    """Expand pieces, resolve Adaptive Trim, optimize, validate, and snapshot."""

    board = command.board
    rows = [dict(row) for row in command.piece_rows]
    expanded = engine.expand_pieces(rows)
    preferred_trim = AppliedTrim(
        width_trim_cm=max(0.0, board.trim_cm),
        length_trim_cm=max(0.0, board.trim_cm),
    )

    preferred_plan = _run_engine(
        command,
        engine=engine,
        pieces=expanded,
        trim=preferred_trim,
    )
    evaluated_plans: dict[AppliedTrim, dict[str, Any]] = {
        preferred_trim: preferred_plan,
    }

    def evaluate_trim(trim: AppliedTrim) -> PlanQuality:
        plan = evaluated_plans.get(trim)
        if plan is None:
            plan = _run_engine(
                command,
                engine=engine,
                pieces=expanded,
                trim=trim,
            )
            evaluated_plans[trim] = plan
        return _plan_quality(plan)

    trim_decision = resolve_adaptive_trim(
        preferred=preferred_trim,
        preferred_quality=_plan_quality(preferred_plan),
        evaluate=evaluate_trim,
        has_pieces=bool(expanded),
        physical_board_lower_bound=_physical_board_lower_bound(expanded, board),
    )
    applied_trim = trim_decision.applied
    plan = evaluated_plans.get(applied_trim)
    if plan is None:
        plan = _run_engine(
            command,
            engine=engine,
            pieces=expanded,
            trim=applied_trim,
        )

    usable_width_cm = applied_trim.usable_width_cm(
        full_width_cm=board.full_width_cm
    )
    usable_length_cm = applied_trim.usable_length_cm(
        full_length_cm=board.full_length_cm
    )
    validation_errors = engine.validate(
        plan,
        expanded,
        usable_width_cm,
        usable_length_cm,
    )
    margin_notes = _build_margin_notes(board, applied_trim)

    metrics = dict(plan.get("industrial_metrics") or {})
    required_boards = len(plan.get("sheets") or [])
    waste_area = max(0.0, _number(plan.get("waste_area_m2")))
    total_board_area = _number(plan.get("total_board_area_m2"))
    waste_percent = round_value(
        (waste_area / total_board_area * 100) if total_board_area else 0,
        2,
    )
    method_label = str(plan.get("method_label") or "")

    sheets = [dict(sheet) for sheet in (plan.get("sheets") or [])]
    for sheet in sheets:
        sheet.setdefault("full_width_cm", board.full_width_cm)
        sheet.setdefault("full_length_cm", board.full_length_cm)
        sheet.setdefault("usable_width_cm", usable_width_cm)
        sheet.setdefault("usable_length_cm", usable_length_cm)
        sheet["applied_trim_width_cm"] = applied_trim.width_trim_cm
        sheet["applied_trim_length_cm"] = applied_trim.length_trim_cm

    trim_policy = _trim_policy_metadata(
        board=board,
        decision=trim_decision,
    )
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
        "usable_board_width_cm": usable_width_cm,
        "usable_board_length_cm": usable_length_cm,
        "kerf_cm": board.kerf_cm,
        "trim_cm": board.trim_cm,
        "applied_trim_width_cm": applied_trim.width_trim_cm,
        "applied_trim_length_cm": applied_trim.length_trim_cm,
        "trim_policy": trim_policy,
        # Compatibility metadata retained for print/DXF/readers that still use
        # the pre-ALMADINA-138 margin vocabulary.
        "margin_policy": {
            "mode": trim_decision.mode,
            "preferred_margin_mm": trim_policy["preferred_trim_mm"],
            "left_mm": trim_policy["applied_width_trim_mm"],
            "right_mm": trim_policy["applied_width_trim_mm"],
            "top_mm": trim_policy["applied_length_trim_mm"],
            "bottom_mm": trim_policy["applied_length_trim_mm"],
            "notes": margin_notes,
        },
        "margin_notes": margin_notes,
        "used_area_m2": plan.get("used_area_m2"),
        "total_board_area_m2": plan.get("total_board_area_m2"),
        "waste_area_m2": plan.get("waste_area_m2"),
        "special_shape_raw_summary": summarize_special_shapes(expanded, plan),
        "sheets": sheets,
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
    if margin_notes:
        packing_score += " | ⚠ " + " ".join(margin_notes)

    return OptimizationOutcome(
        snapshot=snapshot,
        packing_score=packing_score,
        required_boards=required_boards,
        method_label=method_label,
        expanded_pieces=tuple(expanded),
    )


def _run_engine(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
    pieces: list[dict[str, Any]],
    trim: AppliedTrim,
) -> dict[str, Any]:
    board = command.board
    return engine.optimize(
        pieces,
        trim.usable_width_cm(full_width_cm=board.full_width_cm),
        trim.usable_length_cm(full_length_cm=board.full_length_cm),
        board.kerf_cm,
        selected_mode=command.optimizer.selected_mode,
        machine_type=command.optimizer.machine_type,
        time_limit_sec=command.optimizer.time_limit_sec,
        exact_piece_limit=command.optimizer.exact_piece_limit,
        min_remnant_width_cm=command.optimizer.min_remnant_width_cm,
        min_remnant_length_cm=command.optimizer.min_remnant_length_cm,
        min_remnant_area_m2=command.optimizer.min_remnant_area_m2,
    )


def _physical_board_lower_bound(
    pieces: list[dict[str, Any]],
    board: BoardGeometry,
) -> int:
    board_area = max(0.0, board.full_width_cm * board.full_length_cm)
    if board_area <= 0:
        return 0
    piece_area = sum(
        max(0.0, _number(piece.get("width_cm")))
        * max(0.0, _number(piece.get("length_cm")))
        for piece in pieces
    )
    return max(1, math.ceil(piece_area / board_area)) if piece_area else 0


def _plan_quality(plan: dict[str, Any]) -> PlanQuality:
    return PlanQuality(
        unplaced_count=len(plan.get("unplaced") or []),
        board_count=len(plan.get("sheets") or []),
    )


def _trim_policy_metadata(
    *,
    board: BoardGeometry,
    decision: AdaptiveTrimDecision,
) -> dict[str, Any]:
    return {
        "mode": decision.mode,
        "preferred_trim_mm": round_value(max(0.0, board.trim_cm) * 10, 2),
        "applied_width_trim_mm": round_value(
            max(0.0, decision.applied.width_trim_cm) * 10,
            2,
        ),
        "applied_length_trim_mm": round_value(
            max(0.0, decision.applied.length_trim_cm) * 10,
            2,
        ),
        "relaxed_axes": list(decision.relaxed_axes),
        "precision_mm": round_value(TRIM_PRECISION_CM * 10, 2),
        "preferred_quality": {
            "unplaced_count": decision.preferred_quality.unplaced_count,
            "board_count": decision.preferred_quality.board_count,
        },
        "applied_quality": {
            "unplaced_count": decision.applied_quality.unplaced_count,
            "board_count": decision.applied_quality.board_count,
        },
    }


def _build_margin_notes(
    board: BoardGeometry,
    margins: AppliedTrim,
) -> list[str]:
    preferred_mm = round_value(max(0.0, board.trim_cm) * 10, 2)
    width_mm = round_value(max(0.0, margins.width_trim_cm) * 10, 2)
    length_mm = round_value(max(0.0, margins.length_trim_cm) * 10, 2)
    notes: list[str] = []

    if length_mm < preferred_mm:
        if length_mm <= 0:
            notes.append(
                "تم إلغاء هامش التشذيب العلوي والسفلي واستخدام طول اللوح الكامل؛ "
                "يجب التأكد من استقامة الحافتين قبل التنفيذ."
            )
        else:
            notes.append(
                f"تم تخفيض هامش التشذيب العلوي والسفلي من {preferred_mm:g} مم "
                f"إلى {length_mm:g} مم لكل جهة للحفاظ على قياسات القطع المطلوبة."
            )

    if width_mm < preferred_mm:
        if width_mm <= 0:
            notes.append(
                "تم إلغاء هامش التشذيب الأيمن والأيسر واستخدام عرض اللوح الكامل؛ "
                "يجب التأكد من استقامة الحافتين قبل التنفيذ."
            )
        else:
            notes.append(
                f"تم تخفيض هامش التشذيب الأيمن والأيسر من {preferred_mm:g} مم "
                f"إلى {width_mm:g} مم لكل جهة للحفاظ على قياسات القطع المطلوبة."
            )

    return notes


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
    "AppliedMargins",
    "BoardGeometry",
    "CuttingPlanEngine",
    "OptimizationOutcome",
    "OptimizeOrderPlanCommand",
    "OptimizerOptions",
    "optimize_order_plan",
    "summarize_special_shapes",
]
