from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


@frappe.whitelist()
def start_replacement(replacement_name: str) -> dict[str, Any]:
    """Start an approved replacement without inventory side effects."""

    require_any_role("Cutting Operator", "Production Manager")
    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Approved":
        frappe.throw(_("Only an Approved replacement can be started."))
    if not replacement.cutting_plan:
        frappe.throw(_("Replacement has no approved Mini Cutting Plan."))

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
    return {
        "replacement_piece": replacement.name,
        "status": "In Progress",
        "cutting_plan": plan.name,
        "started_on": started_on,
    }


@frappe.whitelist()
def cancel_replacement(
    replacement_name: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Cancel unstarted replacement work without stock reconciliation."""

    require_any_role("Production Manager")
    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
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
    if reason:
        replacement.add_comment(
            "Comment",
            text=_("Replacement cancelled: {0}").format(reason),
        )

    from almdina_erp.almdina_erp.services.replacement_status_service import (
        sync_replacement_order_status,
    )

    order_status = sync_replacement_order_status(
        replacement.door_cutting_order
    )
    return {
        "replacement_piece": replacement.name,
        "status": "Cancelled",
        "order_status": order_status,
    }
