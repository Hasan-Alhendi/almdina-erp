from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _cancel_stock_entry(name: str | None) -> str | None:
    if not name:
        return None
    entry = frappe.get_doc("Stock Entry", name)
    if entry.docstatus == 1:
        entry.cancel()
    return entry.name


@frappe.whitelist()
def reverse_actual_consumption(consumption_log: str, reason: str) -> dict[str, Any]:
    require_any_role("Production Manager", "Stock Manager")
    if not reason:
        frappe.throw(_("Reversal reason is required."))

    frappe.db.sql(
        "select name from `tabMaterial Consumption Log` where name = %s for update",
        (consumption_log,),
    )
    log = frappe.get_doc("Material Consumption Log", consumption_log)
    if log.status != "Submitted":
        frappe.throw(_("Only a Submitted consumption log can have its actual variance reversed."))
    if not log.actual_recorded:
        return {
            "consumption_log": log.name,
            "actual_recorded": False,
            "already_reversed": True,
        }

    cancelled_issue = _cancel_stock_entry(log.adjustment_issue_stock_entry)
    cancelled_return = _cancel_stock_entry(log.adjustment_return_stock_entry)

    history = frappe.parse_json(log.actual_details_json or "{}") or {}
    history["reversed"] = {
        "by": frappe.session.user,
        "reason": reason,
        "cancelled_additional_issue": cancelled_issue,
        "cancelled_return_receipt": cancelled_return,
    }

    log.set("variance_items", [])
    log.actual_recorded = 0
    log.actual_recorded_by = None
    log.actual_recorded_on = None
    log.adjustment_issue_stock_entry = None
    log.adjustment_return_stock_entry = None
    log.material_variance_cost_usd = 0
    log.actual_details_json = frappe.as_json(history)
    log.add_comment("Comment", text=_("Actual consumption variance reversed. Reason: {0}").format(reason))
    log.save(ignore_permissions=True)

    from almdina_erp.almdina_erp.services.cost_service import sync_order_costs

    cost_summary = sync_order_costs(log.door_cutting_order)
    return {
        "consumption_log": log.name,
        "actual_recorded": False,
        "cancelled_additional_issue": cancelled_issue,
        "cancelled_return_receipt": cancelled_return,
        "cost_summary": cost_summary,
    }
