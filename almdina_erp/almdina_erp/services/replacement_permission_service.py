from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.replacements.replacement_authorization import (
    ReplacementAction,
    evaluate_replacement_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
    require_document_capability,
)


_ACTION_CAPABILITIES = frozenset(
    {
        Capability.APPROVE_REPLACEMENT,
        Capability.START_REPLACEMENT,
        Capability.COMPLETE_REPLACEMENT,
        Capability.CANCEL_REPLACEMENT,
        Capability.EDIT_REPLACEMENT_COST,
    }
)


def _granted_for_document(replacement: Any) -> frozenset[str]:
    return frozenset(
        capability
        for capability in _ACTION_CAPABILITIES
        if document_has_capability(replacement, capability)
    )


def replacement_action_context(replacement: Any) -> dict[str, Any]:
    granted = _granted_for_document(replacement)
    has_plan = bool(replacement.cutting_plan)
    actions: dict[str, dict[str, Any]] = {}
    for action in ReplacementAction:
        decision = evaluate_replacement_action(
            granted,
            status=replacement.status,
            action=action,
            has_approved_plan=has_plan,
        )
        actions[action.value] = {
            "allowed": decision.allowed,
            "code": decision.code,
            "reason": decision.reason,
        }
    return {
        "replacement_name": replacement.name,
        "order_name": replacement.door_cutting_order,
        "status": replacement.status,
        "cutting_plan": replacement.cutting_plan,
        "actions": actions,
    }


def require_replacement_action(
    replacement: Any,
    action: ReplacementAction,
) -> None:
    decision = evaluate_replacement_action(
        _granted_for_document(replacement),
        status=replacement.status,
        action=action,
        has_approved_plan=bool(replacement.cutting_plan),
    )
    if decision.allowed:
        return
    exception = frappe.PermissionError if decision.code == "missing_capability" else frappe.ValidationError
    frappe.throw(_(decision.reason), exception)


@frappe.whitelist()
def get_replacement_context(replacement_name: str) -> dict[str, Any]:
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    replacement.check_permission("read")
    require_document_capability(
        replacement,
        Capability.VIEW_REPLACEMENTS,
        message=_("You do not have permission to view replacement pieces."),
    )
    return replacement_action_context(replacement)


__all__ = [
    "get_replacement_context",
    "replacement_action_context",
    "require_replacement_action",
]
