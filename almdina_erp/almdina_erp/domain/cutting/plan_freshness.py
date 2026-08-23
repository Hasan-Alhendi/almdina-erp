from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT


@dataclass(frozen=True)
class PlanFreshnessDecision:
    should_invalidate: bool
    reason: str = ""


def decide_draft_plan_freshness(
    *,
    status: str,
    stored_fingerprint: str,
    expected_fingerprint: str,
    already_needs_recalculation: bool,
) -> PlanFreshnessDecision:
    """Decide whether an existing plan revision became stale.

    Only Draft revisions may be invalidated. Approved/Superseded/Cancelled
    revisions are immutable history. A Draft that is already stale needs no
    additional persistence write.
    """

    if str(status or "") != DRAFT:
        return PlanFreshnessDecision(False, "immutable_revision")
    if already_needs_recalculation:
        return PlanFreshnessDecision(False, "already_stale")

    stored = str(stored_fingerprint or "").strip()
    expected = str(expected_fingerprint or "").strip()
    if stored and stored == expected:
        return PlanFreshnessDecision(False, "fresh")

    return PlanFreshnessDecision(True, "order_requirements_changed")


__all__ = [
    "PlanFreshnessDecision",
    "decide_draft_plan_freshness",
]
