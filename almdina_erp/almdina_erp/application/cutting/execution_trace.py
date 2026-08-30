from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import AdaptiveTrimDecision
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.domain.orders.costing import round_value


CUTTING_EXECUTION_TRACE_VERSION = 1


@dataclass(frozen=True, slots=True)
class CuttingExecutionTrace:
    """Immutable evidence of one completed Cutting Plan optimizer execution.

    The trace is built exactly once from canonical PlanSettings, the real
    Adaptive Trim decision, and the real final optimizer outcome. Preview and
    Commit persist its serialized snapshot representation without rebuilding it.
    """

    version: int
    engine_version: str
    requested_optimization_mode: str
    requested_machine_type: str
    requested_kerf_mm: float
    requested_preferred_trim_mm: float
    requested_time_limit_sec: float
    adaptive_trim_applied: bool
    adaptive_trim_reason: str
    applied_width_trim_mm: float
    applied_length_trim_mm: float
    relaxed_axes: tuple[str, ...]
    preferred_unplaced_count: int
    preferred_board_count: int
    applied_unplaced_count: int
    applied_board_count: int
    actual_optimization_mode: str
    method_key: str
    method_label: str
    ordering_strategy: str
    attempts: int
    elapsed_sec: float
    actual_time_limit_sec: float
    solver_status: str
    solver_wall_time_sec: float

    def to_snapshot(self) -> dict[str, Any]:
        """Return the stable JSON-compatible representation stored in the plan snapshot."""

        return {
            "version": self.version,
            "engine_version": self.engine_version,
            "requested": {
                "optimization_mode": self.requested_optimization_mode,
                "machine_type": self.requested_machine_type,
                "kerf_mm": self.requested_kerf_mm,
                "preferred_trim_mm": self.requested_preferred_trim_mm,
                "optimization_time_limit_sec": self.requested_time_limit_sec,
            },
            "adaptive_trim": {
                "applied": self.adaptive_trim_applied,
                "reason": self.adaptive_trim_reason,
                "applied_width_trim_mm": self.applied_width_trim_mm,
                "applied_length_trim_mm": self.applied_length_trim_mm,
                "relaxed_axes": list(self.relaxed_axes),
                "preferred_quality": {
                    "unplaced_count": self.preferred_unplaced_count,
                    "board_count": self.preferred_board_count,
                },
                "applied_quality": {
                    "unplaced_count": self.applied_unplaced_count,
                    "board_count": self.applied_board_count,
                },
            },
            "optimizer": {
                "actual_optimization_mode": self.actual_optimization_mode,
                "method_key": self.method_key,
                "method_label": self.method_label,
                "ordering_strategy": self.ordering_strategy,
                "attempts": self.attempts,
                "elapsed_sec": self.elapsed_sec,
                "time_limit_sec": self.actual_time_limit_sec,
                "solver_status": self.solver_status,
                "solver_wall_time_sec": self.solver_wall_time_sec,
            },
        }


def build_cutting_execution_trace(
    *,
    plan_settings: PlanSettings,
    trim_decision: AdaptiveTrimDecision,
    optimizer_outcome: Mapping[str, Any],
    engine_version: str,
) -> CuttingExecutionTrace:
    """Build the one canonical trace for a completed optimizer execution."""

    return CuttingExecutionTrace(
        version=CUTTING_EXECUTION_TRACE_VERSION,
        engine_version=str(engine_version or ""),
        requested_optimization_mode=plan_settings.optimization_mode,
        requested_machine_type=plan_settings.machine_type,
        requested_kerf_mm=float(plan_settings.kerf_mm),
        requested_preferred_trim_mm=float(plan_settings.preferred_trim_mm),
        requested_time_limit_sec=float(plan_settings.optimization_time_limit_sec),
        adaptive_trim_applied=bool(trim_decision.relaxed_axes),
        adaptive_trim_reason=trim_decision.reason,
        applied_width_trim_mm=round_value(trim_decision.applied.width_trim_cm * 10, 2),
        applied_length_trim_mm=round_value(trim_decision.applied.length_trim_cm * 10, 2),
        relaxed_axes=tuple(trim_decision.relaxed_axes),
        preferred_unplaced_count=int(trim_decision.preferred_quality.unplaced_count),
        preferred_board_count=int(trim_decision.preferred_quality.board_count),
        applied_unplaced_count=int(trim_decision.applied_quality.unplaced_count),
        applied_board_count=int(trim_decision.applied_quality.board_count),
        actual_optimization_mode=str(optimizer_outcome.get("optimization_mode") or ""),
        method_key=str(optimizer_outcome.get("method_key") or ""),
        method_label=str(optimizer_outcome.get("method_label") or ""),
        ordering_strategy=str(optimizer_outcome.get("ordering_strategy") or ""),
        attempts=_integer(optimizer_outcome.get("attempts")),
        elapsed_sec=_number(optimizer_outcome.get("search_elapsed_sec")),
        actual_time_limit_sec=_number(optimizer_outcome.get("search_time_limit_sec")),
        solver_status=str(optimizer_outcome.get("solver_status") or ""),
        solver_wall_time_sec=_number(optimizer_outcome.get("solver_wall_time_sec")),
    )


def _number(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(float(value)) if value is not None else 0
    except (TypeError, ValueError):
        return 0


__all__ = [
    "CUTTING_EXECUTION_TRACE_VERSION",
    "CuttingExecutionTrace",
    "build_cutting_execution_trace",
]
