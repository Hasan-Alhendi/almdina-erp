from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


@frappe.whitelist()
def complete_replacement(
    replacement_name: str,
    internal_loss_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Complete replacement work and update operational cost only."""

    require_any_role("Cutting Operator", "Production Manager")
    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "In Progress":
        frappe.throw(_("Only an In Progress replacement can be completed."))

    actual_loss = (
        flt(internal_loss_cost_usd)
        if internal_loss_cost_usd is not None
        else flt(replacement.planned_internal_loss_usd)
    )
    if actual_loss < 0:
        frappe.throw(_("Actual internal loss cannot be negative."))

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Completed",
            "internal_loss_cost_usd": actual_loss,
            "charge_customer": 0,
            "completed_by": frappe.session.user,
            "completed_on": now_datetime(),
            "generated_remnant": None,
            "generated_remnants_json": "[]",
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

    from almdina_erp.almdina_erp.services.cost_service import sync_order_costs
    from almdina_erp.almdina_erp.services.replacement_status_service import (
        sync_replacement_order_status,
    )

    order_status = sync_replacement_order_status(
        replacement.door_cutting_order
    )
    return {
        "replacement_piece": replacement.name,
        "status": "Completed",
        "order_status": order_status,
        "internal_loss_cost_usd": actual_loss,
        "charge_customer": 0,
        "cost_summary": sync_order_costs(replacement.door_cutting_order),
    }
