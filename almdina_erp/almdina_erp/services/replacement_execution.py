from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.replacements.replacement_authorization import (
    ReplacementAction,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.services.replacement_permission_service import (
    require_replacement_action,
)


def _load_locked_replacement(replacement_name: str) -> Any:
    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    return frappe.get_doc("Replacement Piece", replacement_name)


@frappe.whitelist()
def start_replacement(replacement_name: str) -> dict[str, Any]:
    """Start an approved replacement without inventory side effects."""

    require_doctype_capability(
        Capability.START_REPLACEMENT,
        message=_("You do not have permission to start replacement work."),
    )
    replacement = _load_locked_replacement(replacement_name)
    replacement.check_permission("read")
    require_replacement_action(replacement, ReplacementAction.START)

    plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
    if plan.status != "Approved" or plan.plan_kind != "Replacement":
        frappe.throw(_("Replacement Mini Cutting Plan is not approved."))

    started_on = now_datetime()
    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "In Progress",
            "started_by": frappe.session.user,
            "started_on": started_on,
            "stock_entry": None,
        },
        update_modified=True,
    )
    replacement.add_comment(
        "Comment",
        text=_("Replacement work started by {0} on {1}.").format(
            frappe.session.user,
            started_on,
        ),
    )
    return {
        "replacement_piece": replacement.name,
        "status": "In Progress",
        "cutting_plan": plan.name,
        "started_on": started_on,
    }


def _cancel_locked_replacement(replacement: Any, reason: str | None) -> dict[str, Any]:
    if replacement.status == "Completed":
        frappe.throw(_("A completed replacement cannot be cancelled."))
    if replacement.status == "In Progress":
        frappe.throw(_("An in-progress replacement cannot be cancelled automatically."))

    if replacement.cutting_plan:
        plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
        if plan.status == "Approved":
            plan.flags.allow_status_transition = True
            plan.status = "Cancelled"
            plan.save(ignore_permissions=True)

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Cancelled",
            "selected_remnant": None,
            "stock_entry": None,
        },
        update_modified=True,
    )
    frappe.db.set_value(
        "Production Incident",
        replacement.incident,
        "status",
        "Resolved",
        update_modified=True,
    )
    replacement.add_comment(
        "Comment",
        text=_("Replacement cancelled by {0}. Reason: {1}").format(
            frappe.session.user,
            str(reason or "").strip() or _("No reason provided"),
        ),
    )

    from almdina_erp.almdina_erp.services.replacement_status_service import (
        sync_replacement_order_status,
    )

    order_status = sync_replacement_order_status(replacement.door_cutting_order)
    return {
        "replacement_piece": replacement.name,
        "status": "Cancelled",
        "order_status": order_status,
    }


@frappe.whitelist()
def cancel_replacement(
    replacement_name: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Cancel unstarted replacement work without stock reconciliation."""

    require_doctype_capability(
        Capability.CANCEL_REPLACEMENT,
        message=_("You do not have permission to cancel replacement work."),
    )
    replacement = _load_locked_replacement(replacement_name)
    replacement.check_permission("read")
    require_replacement_action(replacement, ReplacementAction.CANCEL)
    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("Cancellation reason is required."))
    return _cancel_locked_replacement(replacement, reason)


def cancel_replacement_for_order_cancellation(
    replacement_name: str,
    *,
    reason: str,
) -> dict[str, Any]:
    """Internal side effect of an already-authorized order cancellation."""

    replacement = _load_locked_replacement(replacement_name)
    return _cancel_locked_replacement(replacement, reason)


__all__ = [
    "cancel_replacement",
    "cancel_replacement_for_order_cancellation",
    "start_replacement",
]
