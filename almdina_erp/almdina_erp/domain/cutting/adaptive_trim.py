from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal


TRIM_PRECISION_CM = 0.01  # 0.1 mm
TrimAxis = Literal["width", "length"]


@dataclass(frozen=True, slots=True)
class AppliedTrim:
    """Symmetric trim applied on each physical board axis."""

    width_trim_cm: float
    length_trim_cm: float

    def usable_width_cm(self, *, full_width_cm: float) -> float:
        return max(0.0, full_width_cm - (self.width_trim_cm * 2))

    def usable_length_cm(self, *, full_length_cm: float) -> float:
        return max(0.0, full_length_cm - (self.length_trim_cm * 2))

    @property
    def retained_trim_cm(self) -> float:
        return self.width_trim_cm + self.length_trim_cm

    def relaxed_axes(self, preferred: AppliedTrim) -> tuple[TrimAxis, ...]:
        axes: list[TrimAxis] = []
        if self.width_trim_cm < preferred.width_trim_cm:
            axes.append("width")
        if self.length_trim_cm < preferred.length_trim_cm:
            axes.append("length")
        return tuple(axes)


@dataclass(frozen=True, order=True, slots=True)
class PlanQuality:
    """Business quality used by Adaptive Trim: feasibility, then board count."""

    unplaced_count: int
    board_count: int


@dataclass(frozen=True, slots=True)
class AdaptiveTrimDecision:
    preferred: AppliedTrim
    applied: AppliedTrim
    preferred_quality: PlanQuality
    applied_quality: PlanQuality

    @property
    def relaxed_axes(self) -> tuple[TrimAxis, ...]:
        return self.applied.relaxed_axes(self.preferred)

    @property
    def mode(self) -> str:
        return "adaptive" if self.relaxed_axes else "preferred"


TrimEvaluator = Callable[[AppliedTrim], PlanQuality]


def resolve_adaptive_trim(
    *,
    preferred: AppliedTrim,
    preferred_quality: PlanQuality,
    evaluate: TrimEvaluator,
    has_pieces: bool,
    physical_board_lower_bound: int,
    precision_cm: float = TRIM_PRECISION_CM,
) -> AdaptiveTrimDecision:
    """Keep preferred trim unless relaxing it improves feasibility or board count.

    Candidate order is deterministic: width-only, length-only, then both axes.
    If relaxation helps, each affected axis is refined independently to the
    largest feasible trim at the configured precision. The evaluator owns the
    actual optimization run, so the caller can guarantee that every probe uses
    the same selected algorithm, kerf and engine options as the final plan.
    """

    if not has_pieces or _is_zero_trim(preferred):
        return AdaptiveTrimDecision(
            preferred=preferred,
            applied=preferred,
            preferred_quality=preferred_quality,
            applied_quality=preferred_quality,
        )

    if (
        preferred_quality.unplaced_count == 0
        and preferred_quality.board_count <= max(0, physical_board_lower_bound)
    ):
        return AdaptiveTrimDecision(
            preferred=preferred,
            applied=preferred,
            preferred_quality=preferred_quality,
            applied_quality=preferred_quality,
        )

    best_trim = preferred
    best_quality = preferred_quality
    for candidate in _relaxation_candidates(preferred):
        quality = evaluate(candidate)
        if _candidate_is_better(
            candidate=candidate,
            quality=quality,
            current=best_trim,
            current_quality=best_quality,
        ):
            best_trim = candidate
            best_quality = quality

    if best_quality >= preferred_quality:
        return AdaptiveTrimDecision(
            preferred=preferred,
            applied=preferred,
            preferred_quality=preferred_quality,
            applied_quality=preferred_quality,
        )

    refined = best_trim
    if refined.width_trim_cm < preferred.width_trim_cm:
        refined = _refine_axis(
            current=refined,
            preferred_cm=preferred.width_trim_cm,
            axis="width",
            target_quality=best_quality,
            evaluate=evaluate,
            precision_cm=precision_cm,
        )
    if refined.length_trim_cm < preferred.length_trim_cm:
        refined = _refine_axis(
            current=refined,
            preferred_cm=preferred.length_trim_cm,
            axis="length",
            target_quality=best_quality,
            evaluate=evaluate,
            precision_cm=precision_cm,
        )

    refined_quality = evaluate(refined)
    if refined_quality > best_quality:
        refined = best_trim
        refined_quality = best_quality

    return AdaptiveTrimDecision(
        preferred=preferred,
        applied=refined,
        preferred_quality=preferred_quality,
        applied_quality=refined_quality,
    )


def _relaxation_candidates(preferred: AppliedTrim) -> tuple[AppliedTrim, ...]:
    return (
        AppliedTrim(0.0, preferred.length_trim_cm),
        AppliedTrim(preferred.width_trim_cm, 0.0),
        AppliedTrim(0.0, 0.0),
    )


def _candidate_is_better(
    *,
    candidate: AppliedTrim,
    quality: PlanQuality,
    current: AppliedTrim,
    current_quality: PlanQuality,
) -> bool:
    if quality != current_quality:
        return quality < current_quality
    return candidate.retained_trim_cm > current.retained_trim_cm


def _refine_axis(
    *,
    current: AppliedTrim,
    preferred_cm: float,
    axis: TrimAxis,
    target_quality: PlanQuality,
    evaluate: TrimEvaluator,
    precision_cm: float,
) -> AppliedTrim:
    precision = float(precision_cm)
    if not math.isfinite(precision) or precision <= 0:
        raise ValueError("adaptive_trim_precision_must_be_positive")

    max_step = max(0, math.floor((max(0.0, preferred_cm) / precision) + 1e-9))
    low = 0
    high = max_step

    while low < high:
        mid = (low + high + 1) // 2
        candidate_value = mid * precision
        candidate = (
            AppliedTrim(candidate_value, current.length_trim_cm)
            if axis == "width"
            else AppliedTrim(current.width_trim_cm, candidate_value)
        )
        if evaluate(candidate) <= target_quality:
            low = mid
        else:
            high = mid - 1

    resolved = low * precision
    if axis == "width":
        return AppliedTrim(resolved, current.length_trim_cm)
    return AppliedTrim(current.width_trim_cm, resolved)


def _is_zero_trim(trim: AppliedTrim) -> bool:
    return trim.width_trim_cm <= 0 and trim.length_trim_cm <= 0


__all__ = [
    "AdaptiveTrimDecision",
    "AppliedTrim",
    "PlanQuality",
    "TRIM_PRECISION_CM",
    "TrimAxis",
    "resolve_adaptive_trim",
]
