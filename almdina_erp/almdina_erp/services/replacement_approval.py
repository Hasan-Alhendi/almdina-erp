from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

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


@frappe.whitelist()
def approve_replacement(replacement_name: str) -> dict[str, Any]:
    require_doctype_capability(
        Capability.APPROVE_REPLACEMENT,
        message=_("You do not have permission to approve replacement pieces."),
    )
    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    replacement.check_permission("read")
    require_replacement_action(replacement, ReplacementAction.APPROVE)

    order = frappe.get_doc("Door Cutting Order", replacement.door_cutting_order)

    from almdina_erp.almdina_erp.infrastructure.frappe.replacements.snapshot_adapter import (
        build_replacement_snapshot,
    )
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

    snapshot = build_replacement_snapshot(order, replacement)
    plan = create_mini_plan(order, replacement, snapshot)

    approved_on = now_datetime()
    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Approved",
            "approved_by": frappe.session.user,
            "approved_on": approved_on,
            "board_description": board_description,
            "selected_remnant": None,
            "stock_entry": None,
            "cutting_plan": plan.name,
            "planned_internal_loss_usd": flt(plan.total_cost_usd),
            "charge_customer": 0,
        },
        update_modified=True,
    )
    replacement.add_comment(
        "Comment",
        text=_("Replacement approved by {0} on {1}.").format(
            frappe.session.user,
            approved_on,
        ),
    )
    return {
        "replacement_piece": replacement.name,
        "status": "Approved",
        "cutting_plan": plan.name,
        "planned_internal_loss_usd": flt(plan.total_cost_usd),
    }
