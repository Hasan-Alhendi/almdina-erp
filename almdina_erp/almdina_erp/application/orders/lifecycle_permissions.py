from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    can_return_to_draft,
    normalize_order_status,
)
from almdina_erp.almdina_erp.domain.orders.revisions import can_create_revision
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class OrderLifecycleAction:
    EDIT = "edit"
    SUBMIT_FOR_REVIEW = "submit_for_review"
    APPROVE = "approve"
    CREATE_REVISION = "create_revision"
    RETURN_TO_DRAFT = "return_to_draft"
    CANCEL = "cancel"


ACTION_CAPABILITIES = MappingProxyType(
    {
        OrderLifecycleAction.EDIT: Capability.EDIT_ORDER,
        OrderLifecycleAction.SUBMIT_FOR_REVIEW: Capability.SUBMIT_ORDER,
        OrderLifecycleAction.APPROVE: Capability.APPROVE_ORDER,
        OrderLifecycleAction.CREATE_REVISION: Capability.CREATE_ORDER_REVISION,
        OrderLifecycleAction.RETURN_TO_DRAFT: Capability.RETURN_ORDER_TO_DRAFT,
        OrderLifecycleAction.CANCEL: Capability.CANCEL_ORDER,
    }
)


@dataclass(frozen=True, slots=True)
class LifecycleActionDecision:
    action: str
    capability: str
    allowed: bool
    reason: str = ""

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "action": self.action,
            "capability": self.capability,
            "allowed": self.allowed,
            "reason": self.reason,
        }


def capability_for_action(action: str) -> str:
    try:
        return ACTION_CAPABILITIES[action]
    except KeyError as exc:
        raise ValueError(f"Unknown order lifecycle action: {action}") from exc


def _state_reason(action: str, status: str, revision_state: str) -> str:
    if revision_state == "Superseded":
        return "This is a historical superseded revision and cannot be changed."

    if action == OrderLifecycleAction.EDIT:
        if status in {"Delivered", "Cancelled", "Completed"}:
            return "Delivered, cancelled, or completed orders cannot be edited."
        if status in {
            "At Sharyoun",
            "At CNC",
            "At Sanding",
            "Ready for Delivery",
            "Cutting In Progress",
            "Cut Completed",
            "Edge Banding In Progress",
            "Quality Check",
            "Partially Completed",
        }:
            return "Orders cannot be edited after cutting has started (Sharyoun or CNC)."
        return ""

    if action == OrderLifecycleAction.SUBMIT_FOR_REVIEW:
        if status not in {"Draft", "Rejected"}:
            return "Only draft or rejected orders can be submitted for review."
        return ""

    if action == OrderLifecycleAction.APPROVE:
        if status not in {"Draft", "Rejected", "Pending Review"}:
            return "Only draft, rejected, or pending-review orders can be approved."
        return ""

    if action == OrderLifecycleAction.CREATE_REVISION:
        if not can_create_revision(status):
            return "This order state does not require or allow a controlled revision."
        return ""

    if action == OrderLifecycleAction.RETURN_TO_DRAFT:
        if not can_return_to_draft(status):
            return "This order cannot be returned to draft from its current state."
        return ""

    if action == OrderLifecycleAction.CANCEL:
        if status in {"Cancelled", "Delivered", "Completed"}:
            return "Cancelled, delivered, or completed orders cannot be cancelled through the normal workflow."
        return ""

    raise ValueError(f"Unknown order lifecycle action: {action}")


def decide_lifecycle_action(
    *,
    action: str,
    status: str | None,
    revision_state: str | None,
    has_capability: bool,
) -> LifecycleActionDecision:
    capability = capability_for_action(action)
    if not has_capability:
        return LifecycleActionDecision(
            action=action,
            capability=capability,
            allowed=False,
            reason="You do not have permission for this order action.",
        )

    normalized_status = normalize_order_status(status)
    normalized_revision_state = str(revision_state or "Current")
    reason = _state_reason(action, normalized_status, normalized_revision_state)
    return LifecycleActionDecision(
        action=action,
        capability=capability,
        allowed=not reason,
        reason=reason,
    )


def build_lifecycle_context(
    *,
    status: str | None,
    revision_state: str | None,
    capability_flags: dict[str, bool],
) -> dict[str, object]:
    decisions = {
        action: decide_lifecycle_action(
            action=action,
            status=status,
            revision_state=revision_state,
            has_capability=bool(capability_flags.get(capability_for_action(action))),
        )
        for action in ACTION_CAPABILITIES
    }
    return {
        "status": normalize_order_status(status),
        "revision_state": str(revision_state or "Current"),
        "actions": {
            action: decision.as_dict()
            for action, decision in decisions.items()
        },
        "editable": decisions[OrderLifecycleAction.EDIT].allowed,
    }


__all__ = [
    "ACTION_CAPABILITIES",
    "LifecycleActionDecision",
    "OrderLifecycleAction",
    "build_lifecycle_context",
    "capability_for_action",
    "decide_lifecycle_action",
]
