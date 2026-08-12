from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

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
class AppliedMargins:
    """Resolved symmetric trim per physical board axis.

    ``width_trim_cm`` is applied to both left and right edges.
    ``length_trim_cm`` is applied to both top and bottom edges.
    """

    width_trim_cm: float
    length_trim_cm: float

    def usable_width_cm(self, board: BoardGeometry) -> float:
        return max(0.0, board.full_width_cm - (self.width_trim_cm * 2))

    def usable_length_cm(self, board: BoardGeometry) -> float:
        return max(0.0, board.full_length_cm - (self.length_trim_cm * 2))


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
    """Expand pieces, resolve safe trim, optimize, validate, and persist a snapshot."""

    board = command.board
    rows = [dict(row) for row in command.piece_rows]
    expanded = engine.expand_pieces(rows)
    preferred_margins = AppliedMargins(
        width_trim_cm=max(0.0, board.trim_cm),
        length_trim_cm=max(0.0, board.trim_cm),
    )

    preferred_plan = _run_engine(
        command,
        engine=engine,
        pieces=expanded,
        margins=preferred_margins,
        selected_mode=command.optimizer.selected_mode,
    )
    applied_margins, plan = _resolve_adaptive_margins(
        command,
        engine=engine,
        pieces=expanded,
        preferred_margins=preferred_margins,
        preferred_plan=preferred_plan,
    )

    usable_width_cm = applied_margins.usable_width_cm(board)
    usable_length_cm = applied_margins.usable_length_cm(board)
    validation_errors = engine.validate(
        plan,
        expanded,
        usable_width_cm,
        usable_length_cm,
    )
    margin_notes = _build_margin_notes(board, applied_margins)

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
        sheet["applied_trim_width_cm"] = applied_margins.width_trim_cm
        sheet["applied_trim_length_cm"] = applied_margins.length_trim_cm

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
        "applied_trim_width_cm": applied_margins.width_trim_cm,
        "applied_trim_length_cm": applied_margins.length_trim_cm,
        "margin_policy": {
            "mode": "adaptive" if margin_notes else "preferred",
            "preferred_margin_mm": round_value(board.trim_cm * 10, 2),
            "left_mm": round_value(applied_margins.width_trim_cm * 10, 2),
            "right_mm": round_value(applied_margins.width_trim_cm * 10, 2),
            "top_mm": round_value(applied_margins.length_trim_cm * 10, 2),
            "bottom_mm": round_value(applied_margins.length_trim_cm * 10, 2),
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


def _resolve_adaptive_margins(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
    pieces: list[dict[str, Any]],
    preferred_margins: AppliedMargins,
    preferred_plan: dict[str, Any],
) -> tuple[AppliedMargins, dict[str, Any]]:
    """Relax trim only when it improves placement or physical board count.

    The cutting Domain remains unaware of trim policy. We probe only exceptional
    plans, then refine the affected axis to retain as much trim as possible.
    """

    board = command.board
    if board.trim_cm <= 0 or not pieces:
        return preferred_margins, preferred_plan

    preferred_quality = _plan_quality(preferred_plan)
    physical_lower_bound = _physical_board_lower_bound(pieces, board)
    if preferred_quality[0] == 0 and preferred_quality[1] <= physical_lower_bound:
        return preferred_margins, preferred_plan

    probes = [
        AppliedMargins(0.0, preferred_margins.length_trim_cm),
        AppliedMargins(preferred_margins.width_trim_cm, 0.0),
        AppliedMargins(0.0, 0.0),
    ]
    best_margins = preferred_margins
    best_quality = preferred_quality

    for margins in probes:
        probe = _run_engine(
            command,
            engine=engine,
            pieces=pieces,
            margins=margins,
            selected_mode="Auto",
        )
        quality = _plan_quality(probe)
        if quality < best_quality or (
            quality == best_quality
            and _retained_margin(margins) > _retained_margin(best_margins)
        ):
            best_margins = margins
            best_quality = quality

    if best_quality >= preferred_quality:
        return preferred_margins, preferred_plan

    refined = best_margins
    target_quality = best_quality
    if refined.width_trim_cm < preferred_margins.width_trim_cm:
        refined = _refine_axis_margin(
            command,
            engine=engine,
            pieces=pieces,
            margins=refined,
            axis="width",
            preferred_cm=preferred_margins.width_trim_cm,
            target_quality=target_quality,
        )
    if refined.length_trim_cm < preferred_margins.length_trim_cm:
        refined = _refine_axis_margin(
            command,
            engine=engine,
            pieces=pieces,
            margins=refined,
            axis="length",
            preferred_cm=preferred_margins.length_trim_cm,
            target_quality=target_quality,
        )

    final_plan = _run_engine(
        command,
        engine=engine,
        pieces=pieces,
        margins=refined,
        selected_mode=command.optimizer.selected_mode,
    )
    if _plan_quality(final_plan) < preferred_quality:
        return refined, final_plan

    # The probe may find a packing that the requested strategy cannot reproduce.
    # In that case keep the original safe plan instead of relaxing trim for no gain.
    return preferred_margins, preferred_plan


def _refine_axis_margin(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
    pieces: list[dict[str, Any]],
    margins: AppliedMargins,
    axis: str,
    preferred_cm: float,
    target_quality: tuple[int, int],
) -> AppliedMargins:
    low = 0.0
    high = max(0.0, preferred_cm)

    for _ in range(7):
        mid = (low + high) / 2
        candidate = (
            AppliedMargins(mid, margins.length_trim_cm)
            if axis == "width"
            else AppliedMargins(margins.width_trim_cm, mid)
        )
        probe = _run_engine(
            command,
            engine=engine,
            pieces=pieces,
            margins=candidate,
            selected_mode="Auto",
        )
        if _plan_quality(probe) <= target_quality:
            low = mid
        else:
            high = mid

    # Keep 0.1 mm precision and round downward so the final margin stays feasible.
    resolved = math.floor((low * 100) + 1e-9) / 100
    if axis == "width":
        return AppliedMargins(resolved, margins.length_trim_cm)
    return AppliedMargins(margins.width_trim_cm, resolved)


def _run_engine(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
    pieces: list[dict[str, Any]],
    margins: AppliedMargins,
    selected_mode: str,
) -> dict[str, Any]:
    board = command.board
    return engine.optimize(
        pieces,
        margins.usable_width_cm(board),
        margins.usable_length_cm(board),
        board.kerf_cm,
        selected_mode=selected_mode,
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


def _plan_quality(plan: dict[str, Any]) -> tuple[int, int]:
    return (
        len(plan.get("unplaced") or []),
        len(plan.get("sheets") or []),
    )


def _retained_margin(margins: AppliedMargins) -> float:
    return margins.width_trim_cm + margins.length_trim_cm


def _build_margin_notes(
    board: BoardGeometry,
    margins: AppliedMargins,
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
