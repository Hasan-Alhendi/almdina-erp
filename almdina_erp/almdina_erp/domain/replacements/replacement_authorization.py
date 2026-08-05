from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from almdina_erp.almdina_erp.domain.security.authorization import (
    Capability,
    normalize_capabilities,
)


class ReplacementAction(StrEnum):
    APPROVE = "approve"
    START = "start"
    COMPLETE = "complete"
    CANCEL = "cancel"
    EDIT_ACTUAL_COST = "edit_actual_cost"


@dataclass(frozen=True, slots=True)
class ReplacementAuthorizationDecision:
    allowed: bool
    code: str
    reason: str


_REQUIRED_CAPABILITY = {
    ReplacementAction.APPROVE: Capability.APPROVE_REPLACEMENT,
    ReplacementAction.START: Capability.START_REPLACEMENT,
    ReplacementAction.COMPLETE: Capability.COMPLETE_REPLACEMENT,
    ReplacementAction.CANCEL: Capability.CANCEL_REPLACEMENT,
    ReplacementAction.EDIT_ACTUAL_COST: Capability.EDIT_REPLACEMENT_COST,
}
_ALLOWED_STATUSES = {
    ReplacementAction.APPROVE: frozenset({"Pending Approval"}),
    ReplacementAction.START: frozenset({"Approved"}),
    ReplacementAction.COMPLETE: frozenset({"In Progress"}),
    ReplacementAction.CANCEL: frozenset({"Pending Approval", "Approved"}),
    ReplacementAction.EDIT_ACTUAL_COST: frozenset({"In Progress"}),
}


def evaluate_replacement_action(
    capabilities: set[str] | frozenset[str] | tuple[str, ...] | list[str],
    *,
    status: str | None,
    action: ReplacementAction,
    has_approved_plan: bool = True,
) -> ReplacementAuthorizationDecision:
    granted = normalize_capabilities(capabilities)
    required = _REQUIRED_CAPABILITY[action]
    if required not in granted:
        return ReplacementAuthorizationDecision(
            False,
            "missing_capability",
            "لا تملك الصلاحية المطلوبة لتنفيذ هذا الإجراء.",
        )

    normalized_status = str(status or "")
    if normalized_status not in _ALLOWED_STATUSES[action]:
        return ReplacementAuthorizationDecision(
            False,
            "invalid_status",
            "حالة قطعة التعويض الحالية لا تسمح بهذا الإجراء.",
        )

    if action == ReplacementAction.START and not has_approved_plan:
        return ReplacementAuthorizationDecision(
            False,
            "missing_approved_plan",
            "لا توجد خطة قص مصغرة معتمدة لقطعة التعويض.",
        )

    return ReplacementAuthorizationDecision(True, "allowed", "")


__all__ = [
    "ReplacementAction",
    "ReplacementAuthorizationDecision",
    "evaluate_replacement_action",
]
