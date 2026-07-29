from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


@frappe.whitelist()
def approve_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Pending Approval":
        frappe.throw(_("Only a Pending Approval replacement can be approved."))

    order = frappe.get_doc("Door Cutting Order", replacement.door_cutting_order)

    from almdina_erp.almdina_erp.services.replacement_service import _build_replacement_snapshot
    from almdina_erp.almdina_erp.services.replacement_plan_service import create_mini_plan

    board_description = str(
        replacement.board_description or order.board_description or ""
    ).strip()
    if not board_description:
        frappe.throw(_("Board description is required."))
    replacement.board_description = board_description
    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        "board_description",
        board_description,
        update_modified=False,
    )

    snapshot = _build_replacement_snapshot(order, replacement, None)
    plan = create_mini_plan(order, replacement, snapshot)

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Approved",
            "approved_by": frappe.session.user,
            "approved_on": now_datetime(),
            "board_description": board_description,
            "selected_remnant": None,
            "stock_entry": None,
            "cutting_plan": plan.name,
            "planned_internal_loss_usd": flt(plan.total_cost_usd),
            "charge_customer": 0,
        },
        update_modified=True,
    )
    return {
        "replacement_piece": replacement.name,
        "status": "Approved",
        "cutting_plan": plan.name,
        "planned_internal_loss_usd": flt(plan.total_cost_usd),
    }
