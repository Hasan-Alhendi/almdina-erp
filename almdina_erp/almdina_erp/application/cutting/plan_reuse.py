from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlanReuseContext:
    has_plan_json: bool
    has_snapshot_sheets: bool
    requested_input_fingerprint: str
    stored_input_fingerprint: str = ""
    snapshot_input_fingerprint: str = ""
    has_legacy_plan: bool = False
    legacy_input_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class PlanReuseDecision:
    reuse: bool
    needs_legacy_fingerprint: bool = False
    reason: str = ""


def decide_plan_reuse(context: PlanReuseContext) -> PlanReuseDecision:
    """Preserve fast-path and legacy migration behaviour without framework access."""

    requested = str(context.requested_input_fingerprint or "")
    stored = str(context.stored_input_fingerprint or "")
    snapshot = str(context.snapshot_input_fingerprint or "")

    if context.has_plan_json and stored:
        return PlanReuseDecision(
            reuse=stored == requested,
            reason="stored_hash_match" if stored == requested else "stored_hash_changed",
        )

    if not context.has_snapshot_sheets:
        return PlanReuseDecision(reuse=False, reason="missing_snapshot_sheets")

    if snapshot:
        return PlanReuseDecision(
            reuse=snapshot == requested,
            reason="snapshot_hash_match" if snapshot == requested else "snapshot_hash_changed",
        )

    if not context.has_legacy_plan:
        return PlanReuseDecision(reuse=False, reason="missing_legacy_plan")

    legacy = str(context.legacy_input_fingerprint or "")
    if not legacy:
        return PlanReuseDecision(
            reuse=False,
            needs_legacy_fingerprint=True,
            reason="legacy_fingerprint_required",
        )

    return PlanReuseDecision(
        reuse=legacy == requested,
        reason="legacy_hash_match" if legacy == requested else "legacy_hash_changed",
    )


def plan_invalidation_state(*, engine_version: str) -> dict[str, Any]:
    """Return the authoritative field reset for a stale placement plan."""

    return {
        "plan_needs_recalculation": 1,
        "calculated_plan_input_hash": "",
        "calculated_plan_metadata_hash": "",
        "cutting_plan_json": "",
        "required_boards": 0,
        "waste_area_m2": 0,
        "waste_percent": 0,
        "mdf_cost_usd": 0,
        "cutting_cost_usd": 0,
        "total_cost_usd": 0,
        "packing_method": "",
        "packing_score": "خطة القص تحتاج إعادة حساب",
        "engine_version": engine_version,
    }


__all__ = [
    "PlanReuseContext",
    "PlanReuseDecision",
    "decide_plan_reuse",
    "plan_invalidation_state",
]
