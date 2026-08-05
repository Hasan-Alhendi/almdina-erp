from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.application.orders.lifecycle_permissions import (
    ACTION_CAPABILITIES,
    OrderLifecycleAction,
    build_lifecycle_context,
    capability_for_action,
    decide_lifecycle_action,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
)


def _locked_order(order_name: str) -> Any:
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    return order


def require_lifecycle_action(order: Any, action: str) -> None:
    capability = capability_for_action(action)
    has_permission = document_has_capability(order, capability)
    decision = decide_lifecycle_action(
        action=action,
        status=getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
        has_capability=has_permission,
    )
    if decision.allowed:
        return
    exception = frappe.PermissionError if not has_permission else frappe.ValidationError
    frappe.throw(_(decision.reason), exception)


def lifecycle_context_for_order(order: Any) -> dict[str, object]:
    capability_flags = {
        capability: document_has_capability(order, capability)
        for capability in set(ACTION_CAPABILITIES.values())
    }
    context = build_lifecycle_context(
        status=getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
        capability_flags=capability_flags,
    )
    return {
        **context,
        "order_name": order.name,
        "docstatus": int(getattr(order, "docstatus", 0) or 0),
    }


@frappe.whitelist()
def get_order_lifecycle_context(order_name: str) -> dict[str, object]:
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    return lifecycle_context_for_order(order)


@frappe.whitelist()
def submit_order_for_review(order_name: str) -> dict[str, Any]:
    """Move an editable order to review without coupling the action to a role."""

    order = _locked_order(order_name)
    require_lifecycle_action(order, OrderLifecycleAction.SUBMIT_FOR_REVIEW)

    order.flags.allow_status_transition = True
    order.status = "Pending Review"
    order.save(ignore_permissions=True)
    order.add_comment(
        "Comment",
        text=_("Order submitted for review by {0} on {1}.").format(
            frappe.session.user,
            now_datetime(),
        ),
    )
    return {
        "name": order.name,
        "status": order.status,
        "lifecycle": lifecycle_context_for_order(order),
    }


__all__ = [
    "get_order_lifecycle_context",
    "lifecycle_context_for_order",
    "require_lifecycle_action",
    "submit_order_for_review",
]
