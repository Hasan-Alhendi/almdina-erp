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
    document_has_capability,
    require_doctype_capability,
)
from almdina_erp.almdina_erp.services.replacement_permission_service import (
    require_replacement_action,
)


@frappe.whitelist()
def complete_replacement(
    replacement_name: str,
    internal_loss_cost_usd: float | None = None,
) -> dict[str, Any]:
    """Complete replacement work and return only authorized cost data."""

    require_doctype_capability(
        Capability.COMPLETE_REPLACEMENT,
        message=_("You do not have permission to complete replacement work."),
    )
    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    replacement.check_permission("read")
    require_replacement_action(replacement, ReplacementAction.COMPLETE)

    can_edit_cost = document_has_capability(
        replacement,
        Capability.EDIT_REPLACEMENT_COST,
    )
    if internal_loss_cost_usd is not None and not can_edit_cost:
        require_replacement_action(
            replacement,
            ReplacementAction.EDIT_ACTUAL_COST,
        )

    actual_loss = (
        flt(internal_loss_cost_usd)
        if internal_loss_cost_usd is not None
        else flt(replacement.planned_internal_loss_usd)
    )
    if actual_loss < 0:
        frappe.throw(_("Actual internal loss cannot be negative."))

    completed_on = now_datetime()
    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Completed",
            "internal_loss_cost_usd": actual_loss,
            "charge_customer": 0,
            "completed_by": frappe.session.user,
            "completed_on": completed_on,
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

    order_status = sync_replacement_order_status(replacement.door_cutting_order)
    cost_summary = sync_order_costs(replacement.door_cutting_order)
    replacement.add_comment(
        "Comment",
        text=_("Replacement completed by {0} on {1}.").format(
            frappe.session.user,
            completed_on,
        ),
    )

    result: dict[str, Any] = {
        "replacement_piece": replacement.name,
        "status": "Completed",
        "order_status": order_status,
        "completed_on": completed_on,
    }
    if can_edit_cost:
        result.update(
            {
                "internal_loss_cost_usd": actual_loss,
                "charge_customer": 0,
                "cost_summary": cost_summary,
            }
        )
    return result
