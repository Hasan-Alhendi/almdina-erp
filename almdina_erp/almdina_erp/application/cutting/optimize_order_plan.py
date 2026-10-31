from __future__ import annotations

import math
from copy import deepcopy
import time
from dataclasses import dataclass, replace
from typing import Any, Protocol

from almdina_erp.almdina_erp.application.cutting.execution_trace import (
    build_cutting_execution_trace,
)
from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AdaptiveTrimDecision,
    AppliedTrim,
    PlanQuality,
    TRIM_PRECISION_CM,
)
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    realize_sheet_edge_trim,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    PlanSettings,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygon_area
from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import placed_glass_hole_mm
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.orders.costing import round_value
from almdina_erp.almdina_erp.domain.orders.piece_mirroring import piece_mirroring_allowed


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
        mirroring_allowed: bool = False,
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
    plan_settings: PlanSettings | None = None
    allow_piece_mirroring: bool = False
    seed_plans: tuple[dict[str, Any], ...] = ()
    search_round: int = 0


@dataclass(frozen=True, slots=True)
class OptimizationOutcome:
    snapshot: dict[str, Any]
    packing_score: str
    required_boards: int
    method_label: str
    expanded_pieces: tuple[dict[str, Any], ...]
    candidate_snapshots: tuple[dict[str, Any], ...] = ()
    search_seeds: tuple[dict[str, Any], ...] = ()


def optimize_order_plan(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
) -> OptimizationOutcome:
    """Expand pieces, resolve Adaptive Trim, optimize, validate, and snapshot."""

    started = time.monotonic()
    board = command.board
    plan_settings = _canonical_trace_settings(command)
    smart = plan_settings.optimization_mode == "smart"
    deadline = started + command.optimizer.time_limit_sec
    rows = [dict(row) for row in command.piece_rows]
    expanded = engine.expand_pieces(rows)
    preferred_trim = AppliedTrim(
        width_trim_cm=max(0.0, board.trim_cm),
        length_trim_cm=max(0.0, board.trim_cm),
    )

    def run_for_trim(trim: AppliedTrim) -> dict[str, Any]:
        return _run_engine(
            command, engine=engine, pieces=expanded, trim=trim,
            time_limit_sec=max(0.0, deadline - time.monotonic()) if smart else None,
        )

    preferred_plan = run_for_trim(preferred_trim)
    # New plans use the requested trim as a mandatory physical inset.
    # Do not spend the search budget probing smaller margins.
    preferred_quality = _plan_quality(preferred_plan)
    trim_decision = AdaptiveTrimDecision(
        preferred=preferred_trim,
        applied=preferred_trim,
        preferred_quality=preferred_quality,
        applied_quality=preferred_quality,
    )
    applied_trim = trim_decision.applied
    plan = preferred_plan

    raw_candidates = plan.pop('smart_candidates', []) if smart else []
    raw_seeds = []
    outcome = _snapshot_outcome(command, engine, deepcopy(plan), expanded, applied_trim, trim_decision, plan_settings)
    snapshots = []
    for raw in raw_candidates:
        result = _snapshot_outcome(command,engine,deepcopy(raw),expanded,applied_trim,trim_decision,plan_settings)
        if result.snapshot['validation']['is_valid']:
            snapshots.append(result.snapshot)
            raw_seeds.append(deepcopy(raw))
    if smart:
        ranked = sorted(
            zip(snapshots, raw_seeds),
            key=lambda pair: tuple(pair[0].get("industrial_rank") or ()),
        )
        snapshots = [snapshot for snapshot, _ in ranked]
        raw_seeds = [seed for _, seed in ranked]
        if snapshots:
            outcome = replace(
                outcome,
                snapshot=snapshots[0],
                required_boards=len(snapshots[0].get("sheets") or []),
                method_label=str(snapshots[0].get("method_label") or ""),
                packing_score=_packing_score_for_snapshot(snapshots[0]),
            )
        outcome.snapshot['smart_search'] = dict(plan.get('smart_search') or {})
        outcome.snapshot['search_time_limit_sec'] = command.optimizer.time_limit_sec
        outcome.snapshot['total_elapsed_sec'] = round(time.monotonic()-started,3)
        outcome.snapshot['smart_search']['trim_evaluations'] = 1
    return replace(outcome,candidate_snapshots=tuple(snapshots),search_seeds=tuple(raw_seeds))


def _snapshot_outcome(command, engine, plan, expanded, applied_trim, trim_decision, plan_settings):
    """One manufacturing snapshot projection for the default and every alternative."""
    board = command.board
    plan["kerf_cm"] = board.kerf_cm
    usable_width_cm = applied_trim.usable_width_cm(
        full_width_cm=board.full_width_cm
    )
    usable_length_cm = applied_trim.usable_length_cm(
        full_length_cm=board.full_length_cm
    )
    margin_notes = _build_margin_notes(board, applied_trim)

    method_label = str(plan.get("method_label") or "")

    sheets = [dict(sheet) for sheet in (plan.get("sheets") or [])]
    for sheet in sheets:
        sheet.setdefault("full_width_cm", board.full_width_cm)
        sheet.setdefault("full_length_cm", board.full_length_cm)
        sheet.setdefault("usable_width_cm", usable_width_cm)
        sheet.setdefault("usable_length_cm", usable_length_cm)
        sheet["applied_trim_width_cm"] = applied_trim.width_trim_cm
        sheet["applied_trim_length_cm"] = applied_trim.length_trim_cm
    machine_type = command.optimizer.machine_type or "Auto"
    metric_options = {
        "machine_type": machine_type,
        "min_remnant_width_cm": command.optimizer.min_remnant_width_cm,
        "min_remnant_length_cm": command.optimizer.min_remnant_length_cm,
        "min_remnant_area_m2": command.optimizer.min_remnant_area_m2,
    }
    original_sheets = deepcopy(sheets)
    original_metrics = _enrich_final_geometry_metrics(
        {**plan, "sheets": original_sheets}, metric_options
    )
    realize_sheet_edge_trim(
        sheets,
        full_width_cm=board.full_width_cm,
        full_length_cm=board.full_length_cm,
        preferred_width_trim_cm=trim_decision.preferred.width_trim_cm,
        preferred_length_trim_cm=trim_decision.preferred.length_trim_cm,
        balance_existing_applied=True,
        **metric_options,
    )
    plan["sheets"] = sheets
    plan = _enrich_final_geometry_metrics(plan, metric_options)
    if tuple(plan.get("industrial_rank") or ()) > tuple(
        original_metrics.get("industrial_rank") or ()
    ):
        plan["sheets"] = original_sheets
        plan = _enrich_final_geometry_metrics(plan, metric_options)

    def validate_snapshot_plan() -> list[str]:
        errors = list(
            engine.validate(plan, expanded, usable_width_cm, usable_length_cm)
        )
        errors.extend(
            placement_permission_errors(
                plan,
                expanded,
                mirroring_allowed=piece_mirroring_allowed(
                    command.allow_piece_mirroring
                ),
            )
        )
        if plan.get("unplaced"):
            errors.append(
                "تعذر وضع جميع القطع ضمن أبعاد اللوح والهامش الأدنى المحددين."
            )
        return errors

    validation_errors = validate_snapshot_plan()
    if validation_errors and plan.get("sheets") != original_sheets:
        plan["sheets"] = original_sheets
        plan = _enrich_final_geometry_metrics(plan, metric_options)
        validation_errors = validate_snapshot_plan()

    metrics = dict(plan.get("industrial_metrics") or {})
    required_boards = len(plan.get("sheets") or [])

    trim_policy = _trim_policy_metadata(
        board=board,
        decision=trim_decision,
    )
    execution_trace = build_cutting_execution_trace(
        plan_settings=plan_settings,
        trim_decision=trim_decision,
        optimizer_outcome=plan,
        engine_version=command.engine_version,
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
        "allow_piece_mirroring": piece_mirroring_allowed(command.allow_piece_mirroring),
        "applied_trim_width_cm": applied_trim.width_trim_cm,
        "applied_trim_length_cm": applied_trim.length_trim_cm,
        "trim_policy": trim_policy,
        "execution_trace": execution_trace.to_snapshot(),
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

    return OptimizationOutcome(
        snapshot=snapshot,
        packing_score=_packing_score_for_snapshot(snapshot),
        required_boards=required_boards,
        method_label=method_label,
        expanded_pieces=tuple(expanded),
    )


def _packing_score_for_snapshot(snapshot: dict[str, Any]) -> str:
    metrics = dict(snapshot.get("industrial_metrics") or {})
    waste_area = max(0.0, _number(snapshot.get("waste_area_m2")))
    total_board_area = _number(snapshot.get("total_board_area_m2"))
    waste_percent = round_value(
        (waste_area / total_board_area * 100) if total_board_area else 0,
        2,
    )
    score = (
        f"ألواح: {len(snapshot.get('sheets') or [])} | هدر: {waste_percent}% | "
        f"قصات تقديرية: {_integer(metrics.get('estimated_cut_count'))} | "
        "أكبر بقايا مفيدة: "
        f"{round_value(metrics.get('largest_reusable_free_area_m2') or 0, 3)} م² | "
        f"محاولات: {_integer(snapshot.get('attempts'))} | "
        f"الخوارزمية: {snapshot.get('method_label') or ''}"
    )
    notes = snapshot.get("margin_notes") or []
    return score + (" | ⚠ " + " ".join(notes) if notes else "")


def _enrich_final_geometry_metrics(
    plan: dict[str, Any], metric_options: dict[str, Any]
) -> dict[str, Any]:
    """Refresh quality only when the snapshot has complete placed geometry."""
    for sheet in plan.get("sheets") or []:
        if _number(sheet.get("w")) <= 0 or _number(sheet.get("h")) <= 0:
            return plan
        for piece in sheet.get("pieces") or []:
            if any(piece.get(key) is None for key in ("x", "y", "w", "h")):
                return plan
    return enrich_plan_metrics(
        plan, str(plan.get("method_key") or ""), **metric_options
    )


def _canonical_trace_settings(command: OptimizeOrderPlanCommand) -> PlanSettings:
    """Return the canonical settings object used as execution-trace input.

    Frappe production callers pass their already-normalized PlanSettings object.
    The fallback preserves compatibility for application callers that predate
    ALMADINA-139 while still constructing the trace from a canonical contract.
    """

    if command.plan_settings is not None:
        return command.plan_settings
    return normalize_plan_settings(
        optimization_mode=command.optimizer.selected_mode,
        machine_type=command.optimizer.machine_type,
        optimization_time_limit_sec=command.optimizer.time_limit_sec,
        kerf_mm=command.board.kerf_cm * 10,
        preferred_trim_mm=command.board.trim_cm * 10,
    )


def _run_engine(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
    pieces: list[dict[str, Any]],
    trim: AppliedTrim,
    time_limit_sec: float | None = None,
) -> dict[str, Any]:
    board = command.board
    return engine.optimize(
        pieces,
        trim.usable_width_cm(full_width_cm=board.full_width_cm),
        trim.usable_length_cm(full_length_cm=board.full_length_cm),
        board.kerf_cm,
        selected_mode=command.optimizer.selected_mode,
        machine_type=command.optimizer.machine_type,
        time_limit_sec=(command.optimizer.time_limit_sec if time_limit_sec is None else time_limit_sec),
        exact_piece_limit=command.optimizer.exact_piece_limit,
        min_remnant_width_cm=command.optimizer.min_remnant_width_cm,
        min_remnant_length_cm=command.optimizer.min_remnant_length_cm,
        min_remnant_area_m2=command.optimizer.min_remnant_area_m2,
        mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring),
        **({'seed_plans':command.seed_plans,'search_round':command.search_round}
           if command.seed_plans or command.search_round else {}),
    )


def _physical_board_lower_bound(
    pieces: list[dict[str, Any]],
    board: BoardGeometry,
) -> int:
    board_area = max(0.0, board.full_width_cm * board.full_length_cm)
    if board_area <= 0:
        return 0
    areas = []
    for piece in pieces:
        kind = str(piece.get("piece_type") or "Regular")
        if kind == "Regular":
            areas.append(
                max(0.0, _number(piece.get("width_cm")))
                * max(0.0, _number(piece.get("length_cm")))
            )
            continue
        # Special source outlines do not certify net material including all
        # structural holes. Unknown geometry contributes zero, never its box.
        if kind not in {"L-Shaped Corner", "Clipped Corner", "Glass"}:
            continue
        try:
            outline = material_outline_cm(piece)
            if outline is None:
                continue
            area = polygon_area(outline)
            if kind == "Glass":
                hole_mm = placed_glass_hole_mm(piece, rotated=False)
                if hole_mm is None:
                    continue
                area -= polygon_area(hole_mm) / 100  # mm² -> cm²
            if math.isfinite(area):
                areas.append(max(0.0, area))
        except (TypeError, ValueError, OverflowError):
            continue
    piece_area = sum(areas)
    if piece_area:
        return max(1, math.ceil(piece_area / board_area))
    return int(any((piece.get("piece_type") or "Regular") != "Regular" for piece in pieces))


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
        "policy": "mandatory_minimum_v1",
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
