from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    ACTIVE_STAGE_STATUSES,
    can_dispatch_from_status,
    can_mark_delivered,
    can_transition_stage,
    is_order_dispatched,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


PRODUCTION_ACTIONS = (
    Capability.DISPATCH_ORDER,
    Capability.START_ASSIGNED_STAGE,
    Capability.HANDOFF_ASSIGNED_STAGE,
    Capability.REVERT_DEPARTMENT,
    Capability.MARK_DELIVERED,
    Capability.REASSIGN_WORKER,
)


@dataclass(frozen=True, slots=True)
class ProductionActionDecision:
    action: str
    capability: str
    allowed: bool
    code: str
    reason: str
    transition_event: str | None = None


@dataclass(frozen=True, slots=True)
class ProductionActionFacts:
    order_status: str | None
    production_path: str | None = None
    current_stage_name: str | None = None
    has_cutting_plan: bool = False
    plan_needs_recalculation: bool = False
    route_starts_with_planning: bool = False
    stage_name: str | None = None
    stage_type: str | None = None
    stage_status: str | None = None
    assigned_to: str | None = None
    actor: str | None = None
    drawing_dxf_status: str | None = None
    # Retained in the read model for routing/presentation compatibility only.
    # Operational roles qualify assignment candidates; they never grant actions.
    operational_role: str | None = None
    actor_roles: tuple[str, ...] = ()
    is_admin: bool = False


def _decision(
    action: str,
    allowed: bool,
    code: str,
    reason: str,
    *,
    transition_event: str | None = None,
) -> ProductionActionDecision:
    return ProductionActionDecision(
        action=action,
        capability=action,
        allowed=allowed,
        code=code,
        reason=reason,
        transition_event=transition_event,
    )


def _stage_is_current(facts: ProductionActionFacts) -> bool:
    return bool(
        facts.stage_name
        and facts.current_stage_name
        and facts.stage_name == facts.current_stage_name
    )


def decide_production_action(
    action: str,
    *,
    capabilities: Iterable[str] | None,
    facts: ProductionActionFacts,
) -> ProductionActionDecision:
    """Decide one production action from capabilities plus business state.

    Roles are intentionally absent from authorization. A route's operational role
    is only an assignment-eligibility/configuration concern. Once a stage exists,
    the assigned user and the capability matrix are the action authority.
    """

    if action not in PRODUCTION_ACTIONS:
        raise ValueError(f"إجراء الإنتاج غير معروف: {action}")

    granted = frozenset(str(value) for value in (capabilities or ()) if value)
    if action not in granted:
        return _decision(
            action,
            False,
            "missing_capability",
            "لا تملك الصلاحية المطلوبة لتنفيذ هذا الإجراء الإنتاجي.",
        )

    if action == Capability.DISPATCH_ORDER:
        if is_order_dispatched(
            production_path=facts.production_path,
            current_stage=facts.current_stage_name,
        ):
            return _decision(
                action,
                False,
                "already_dispatched",
                "الطلب مُرسل إلى الإنتاج مسبقًا.",
            )
        if not can_dispatch_from_status(facts.order_status):
            return _decision(
                action,
                False,
                "invalid_order_status",
                "حالة الطلب الحالية لا تسمح بإرساله إلى الإنتاج.",
            )
        # Planning-first routes deliberately receive the order before a production
        # plan exists: calculating/reviewing that plan is the planning stage's job.
        if not facts.route_starts_with_planning:
            if not facts.has_cutting_plan:
                return _decision(
                    action,
                    False,
                    "missing_cutting_plan",
                    "احسب خطة القص قبل إرسال الطلب إلى مسار إنتاج لا يبدأ بالتخطيط.",
                )
            if facts.plan_needs_recalculation:
                return _decision(
                    action,
                    False,
                    "stale_cutting_plan",
                    "أعد حساب خطة القص قبل إرسال الطلب إلى مسار إنتاج لا يبدأ بالتخطيط.",
                )
        return _decision(action, True, "allowed", "")

    if action == Capability.MARK_DELIVERED:
        if not can_mark_delivered(facts.order_status):
            return _decision(
                action,
                False,
                "not_ready_for_delivery",
                "يمكن تأكيد التسليم فقط للطلبات الجاهزة للتسليم.",
            )
        return _decision(action, True, "allowed", "")

    if action == Capability.REVERT_DEPARTMENT:
        # Capability alone authorizes revert; structural target checks stay in
        # the command (must pick an existing earlier stage on the order).
        return _decision(action, True, "allowed", "")

    if not _stage_is_current(facts):
        return _decision(
            action,
            False,
            "inactive_stage",
            "المرحلة المحددة ليست مرحلة الإنتاج الحالية للطلب.",
        )

    if action == Capability.REASSIGN_WORKER:
        if facts.stage_status not in ACTIVE_STAGE_STATUSES:
            return _decision(
                action,
                False,
                "closed_stage",
                "يمكن تغيير العامل فقط لمرحلة إنتاج نشطة.",
            )
        return _decision(action, True, "allowed", "")

    if not facts.actor or facts.assigned_to != facts.actor:
        return _decision(
            action,
            False,
            "not_assigned",
            "هذه المرحلة مسندة إلى مستخدم آخر.",
        )

    if action == Capability.START_ASSIGNED_STAGE:
        if not facts.stage_status or not can_transition_stage(
            facts.stage_status,
            "start",
        ):
            return _decision(
                action,
                False,
                "stage_not_startable",
                "يمكن بدء المرحلة فقط عندما تكون بحالة بحاجة للعمل.",
            )
        return _decision(
            action,
            True,
            "allowed",
            "",
            transition_event="start",
        )

    if action == Capability.HANDOFF_ASSIGNED_STAGE:
        if facts.stage_status and can_transition_stage(
            facts.stage_status,
            "finish",
        ):
            return _decision(
                action,
                True,
                "allowed",
                "",
                transition_event="finish",
            )
        if (
            Capability.START_ASSIGNED_STAGE not in granted
            and facts.stage_status
            and can_transition_stage(facts.stage_status, "direct_handoff")
        ):
            return _decision(
                action,
                True,
                "allowed",
                "",
                transition_event="direct_handoff",
            )
        return _decision(
            action,
            False,
            "stage_not_handoff_ready",
            "ابدأ المرحلة أولًا قبل تسليمها إلى القسم التالي.",
        )

    raise AssertionError(f"إجراء إنتاج غير معالج: {action}")


def build_production_action_context(
    *,
    capabilities: Iterable[str] | None,
    facts: ProductionActionFacts,
) -> dict[str, dict[str, str | bool]]:
    return {
        action: {
            "allowed": decision.allowed,
            "code": decision.code,
            "reason": decision.reason,
            "capability": decision.capability,
        }
        for action in PRODUCTION_ACTIONS
        for decision in (
            decide_production_action(
                action,
                capabilities=capabilities,
                facts=facts,
            ),
        )
    }


__all__ = [
    "PRODUCTION_ACTIONS",
    "ProductionActionDecision",
    "ProductionActionFacts",
    "build_production_action_context",
    "decide_production_action",
]
