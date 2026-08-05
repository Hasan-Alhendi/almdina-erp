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
        raise ValueError(f"Unknown production action: {action}")

    granted = frozenset(str(value) for value in (capabilities or ()) if value)
    if action not in granted:
        return _decision(
            action,
            False,
            "missing_capability",
            "You do not have permission for this production action.",
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
                "The order is already assigned to production.",
            )
        if not can_dispatch_from_status(facts.order_status):
            return _decision(
                action,
                False,
                "invalid_order_status",
                "The order status does not allow production dispatch.",
            )
        if not facts.has_cutting_plan:
            return _decision(
                action,
                False,
                "missing_cutting_plan",
                "Calculate a cutting plan before sending the order to production.",
            )
        if facts.plan_needs_recalculation:
            return _decision(
                action,
                False,
                "stale_cutting_plan",
                "Recalculate the cutting plan before sending the order to production.",
            )
        return _decision(action, True, "allowed", "")

    if action == Capability.MARK_DELIVERED:
        if not can_mark_delivered(facts.order_status):
            return _decision(
                action,
                False,
                "not_ready_for_delivery",
                "Only orders ready for delivery can be marked as delivered.",
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
                "The order cannot be returned to an earlier production stage.",
            )
        return _decision(action, True, "allowed", "")

    if not _stage_is_current(facts):
        return _decision(
            action,
            False,
            "inactive_stage",
            "The selected stage is not the current production stage.",
        )

    if action == Capability.REASSIGN_WORKER:
        if facts.stage_status not in ACTIVE_STAGE_STATUSES:
            return _decision(
                action,
                False,
                "closed_stage",
                "Only an active production stage can be reassigned.",
            )
        return _decision(action, True, "allowed", "")

    if not facts.actor or facts.assigned_to != facts.actor:
        return _decision(
            action,
            False,
            "not_assigned",
            "This production stage is assigned to another worker.",
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
                "Only a stage that needs work can be started.",
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
                "Start the stage before sending it to the next department.",
            )
        if (
            facts.stage_type == "Drawing"
            and (facts.drawing_dxf_status or "None") != "Approved by Drawing"
        ):
            return _decision(
                action,
                False,
                "dxf_not_approved",
                "Approve the production DXF before sending the order to CNC.",
            )
        return _decision(action, True, "allowed", "")

    raise AssertionError(f"Unhandled production action: {action}")


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
