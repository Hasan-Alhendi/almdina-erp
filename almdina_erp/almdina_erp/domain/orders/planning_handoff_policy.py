from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlanningHandoffDecision:
    allowed: bool
    code: str
    reason: str


@dataclass(frozen=True, slots=True)
class PlanningHandoffFacts:
    is_planning_stage: bool
    approved_plan_name: str | None
    has_current_approved_plan: bool
    plan_needs_recalculation: bool


def decide_planning_handoff(facts: PlanningHandoffFacts) -> PlanningHandoffDecision:
    """Return one canonical readiness decision for leaving Planning.

    Authorization is deliberately not part of this policy. Capabilities and current
    assignment are checked by the production action policy; this function only
    describes whether the Cutting Plan itself is ready to leave Planning.
    """

    if not facts.is_planning_stage:
        return PlanningHandoffDecision(True, "allowed", "")

    approved_name = str(facts.approved_plan_name or "").strip()
    if not approved_name:
        return PlanningHandoffDecision(
            False,
            "plan_not_approved",
            "اعتمد خطة القص بعد مراجعتها قبل تسليم مرحلة التخطيط إلى القسم التالي.",
        )

    if facts.plan_needs_recalculation or not facts.has_current_approved_plan:
        return PlanningHandoffDecision(
            False,
            "approved_plan_stale",
            "خطة القص المعتمدة لم تعد مطابقة لبيانات الطلب. أعد حسابها ومراجعتها واعتمادها قبل إرسالها إلى القسم التالي.",
        )

    return PlanningHandoffDecision(True, "allowed", "")


__all__ = [
    "PlanningHandoffDecision",
    "PlanningHandoffFacts",
    "decide_planning_handoff",
]
