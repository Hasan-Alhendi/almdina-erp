from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    UPLOADED_DXF,
)


@dataclass(frozen=True)
class PlanFreshnessDecision:
    should_invalidate: bool
    reason: str = ""


def _fingerprints_match(stored_fingerprint: str, expected_fingerprint: str) -> bool:
    stored = str(stored_fingerprint or "").strip()
    expected = str(expected_fingerprint or "").strip()
    return bool(stored) and stored == expected


def matching_freshness_fingerprint(stored_fingerprint: str, *candidates: str) -> str:
    """Return ``stored`` when it still matches any accepted freshness candidate."""

    stored = str(stored_fingerprint or "").strip()
    geometry = str(candidates[0] if candidates else "")
    if not stored:
        return geometry
    for candidate in candidates:
        if _fingerprints_match(stored, candidate):
            return stored
    return geometry


def decide_draft_plan_freshness(
    *,
    status: str,
    stored_fingerprint: str,
    expected_fingerprint: str,
    already_needs_recalculation: bool,
) -> PlanFreshnessDecision:
    """Decide whether an existing plan revision became stale.

    Only Draft revisions may be marked stale in place. Approved geometry stays
    an immutable snapshot; a later order-input change cancels the approval
    relation instead of rewriting that snapshot.
    """

    if str(status or "") != DRAFT:
        return PlanFreshnessDecision(False, "immutable_revision")
    if already_needs_recalculation:
        return PlanFreshnessDecision(False, "already_stale")
    if _fingerprints_match(stored_fingerprint, expected_fingerprint):
        return PlanFreshnessDecision(False, "fresh")

    return PlanFreshnessDecision(True, "order_requirements_changed")


def decide_approved_plan_freshness(
    *,
    status: str,
    stored_fingerprint: str,
    expected_fingerprint: str,
) -> PlanFreshnessDecision:
    """Decide whether the current production approval must be cancelled.

    Geometry is never mutated back into Draft. The Approved revision becomes
    Cancelled so the order can no longer treat it as the production plan.
    """

    if str(status or "") != APPROVED:
        return PlanFreshnessDecision(False, "not_approved")
    if _fingerprints_match(stored_fingerprint, expected_fingerprint):
        return PlanFreshnessDecision(False, "fresh")

    return PlanFreshnessDecision(True, "order_requirements_changed")


def decide_uploaded_plan_mismatch(
    *,
    source_type: str,
    stored_fingerprint: str,
    expected_fingerprint: str,
    already_needs_recalculation: bool,
) -> PlanFreshnessDecision:
    """Decide whether an uploaded DXF should warn that it no longer matches."""

    if str(source_type or "") != UPLOADED_DXF:
        return PlanFreshnessDecision(False, "not_uploaded")
    if already_needs_recalculation:
        return PlanFreshnessDecision(False, "already_stale")
    if _fingerprints_match(stored_fingerprint, expected_fingerprint):
        return PlanFreshnessDecision(False, "fresh")

    return PlanFreshnessDecision(True, "order_requirements_changed")


def manufacturing_trim_matches(
    uploaded_trim_mm: Any,
    manufacturing_trim_mm: Any,
    *,
    tolerance: float = 1e-6,
) -> bool:
    """Compare preferred trim values without treating float noise as a change."""

    try:
        uploaded = float(uploaded_trim_mm)
        manufacturing = float(manufacturing_trim_mm)
    except (TypeError, ValueError):
        return False
    return abs(uploaded - manufacturing) <= tolerance


def decide_uploaded_manufacturing_trim_mismatch(
    *,
    source_type: str,
    status: str,
    uploaded_trim_mm: Any,
    manufacturing_trim_mm: Any,
) -> PlanFreshnessDecision:
    """Decide whether an Uploaded DXF Draft no longer matches manufacturing trim.

    Fingerprints for an uploaded revision include that revision's own trim, so a
    later System trim edit does not stale the uploaded fingerprint. This gate
    compares manufacturing (System) trim to the trim stored on the Uploaded
    Draft — the value used when that DXF was validated — without rewriting the
    uploaded snapshot. Approved/historical revisions stay immutable here.
    """

    if str(source_type or "") != UPLOADED_DXF:
        return PlanFreshnessDecision(False, "not_uploaded")
    if str(status or "") != DRAFT:
        return PlanFreshnessDecision(False, "immutable_revision")
    if manufacturing_trim_matches(uploaded_trim_mm, manufacturing_trim_mm):
        return PlanFreshnessDecision(False, "fresh")
    return PlanFreshnessDecision(True, "trim_margin_changed")


def select_uploaded_workspace_plan(
    rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Choose the uploaded DXF the uploaded tab should keep showing.

    A newer Draft wins so a replacement upload is visible. Otherwise the latest
    Uploaded DXF stays in that tab after approval or later cancellation.
    ``rows`` must already be newest-first.
    """

    latest_draft: Mapping[str, Any] | None = None
    latest_any: Mapping[str, Any] | None = None
    for row in rows:
        if str(row.get("source_type") or "") != UPLOADED_DXF:
            continue
        if latest_any is None:
            latest_any = row
        if latest_draft is None and str(row.get("status") or "") == DRAFT:
            latest_draft = row
    return latest_draft or latest_any


__all__ = [
    "PlanFreshnessDecision",
    "decide_approved_plan_freshness",
    "decide_draft_plan_freshness",
    "decide_uploaded_manufacturing_trim_mismatch",
    "decide_uploaded_plan_mismatch",
    "manufacturing_trim_matches",
    "matching_freshness_fingerprint",
    "select_uploaded_workspace_plan",
]
