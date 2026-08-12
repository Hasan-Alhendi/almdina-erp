from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    ACTIVE_STAGE_STATUSES,
    can_dispatch_from_status,
    can_mark_delivered,
    can_revert_department,
    can_transition_stage,
    is_order_dispatched,
)
from almdina_erp.almdina_erp.domain.orders.stage_operational_access import (
    decide_stage_scoped_mutation,
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


@dataclass(frozen=True, slots=True)
class ProductionActionFacts:
    order_status: str | None
    production_path: str | None = None
    current_stage_name: str | None = None
    has_cutting_plan: bool = False
    plan_needs_recalculation: bool = False
    stage_name: str | None = None
    stage_type: str | None = None
    stage_status: str | None = None
    assigned_to: str | None = None
    actor: str | None = None
    drawing_dxf_status: str | None = None
    operational_role: str | None = None
    actor_roles: tuple[str, ...] = ()
    is_admin: bool = False


def _decision(
    action: str,
    allowed: bool,
    code: str,
    reason: str,
) -> ProductionActionDecision:
    return ProductionActionDecision(
        action=action,
        capability=action,
        allowed=allowed,
        code=code,
        reason=reason,
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
        if not facts.has_cutting_plan:
            return _decision(
                action,
                False,
                "missing_cutting_plan",
                "احسب خطة القص قبل إرسال الطلب إلى الإنتاج.",
            )
        if facts.plan_needs_recalculation:
            return _decision(
                action,
                False,
                "stale_cutting_plan",
                "أعد حساب خطة القص قبل إرسال الطلب إلى الإنتاج.",
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
        if not can_revert_department(
            facts.order_status,
            production_path=facts.production_path,
        ):
            return _decision(
                action,
                False,
                "not_on_production_path",
                "لا يمكن إعادة الطلب إلى مرحلة إنتاج سابقة في حالته الحالية.",
            )
        return _decision(action, True, "allowed", "")

    if not _stage_is_current(facts):
        return _decision(
            action,
            False,
            "inactive_stage",
            "المرحلة المحددة ليست مرحلة الإنتاج الحالية للطلب.",
        )

    if action in {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
        Capability.REASSIGN_WORKER,
    }:
        allowed, code, reason = decide_stage_scoped_mutation(
            actor_roles=facts.actor_roles,
            operational_role=facts.operational_role,
            has_current_stage=True,
            is_admin=facts.is_admin,
        )
        # Reassignment is a supervisory override: only require that the stage
        # has an operational role configured, not that the supervisor holds it.
        if action == Capability.REASSIGN_WORKER:
            if code == "missing_stage_role":
                return _decision(action, False, code, reason)
        elif not allowed:
            return _decision(action, False, code, reason)

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
            "هذه المرحلة مسندة إلى عامل آخر.",
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
        return _decision(action, True, "allowed", "")

    if action == Capability.HANDOFF_ASSIGNED_STAGE:
        if not facts.stage_status or not can_transition_stage(
            facts.stage_status,
            "finish",
        ):
            return _decision(
                action,
                False,
                "stage_not_handoff_ready",
                "ابدأ المرحلة أولًا قبل تسليمها إلى القسم التالي.",
            )
        return _decision(action, True, "allowed", "")

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
