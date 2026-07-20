from __future__ import annotations

from typing import Any

import frappe


@frappe.whitelist()
def cancel_order(
    order_name: str,
    reason: str,
    reverse_stock: int | bool = 0,
) -> dict[str, Any]:
    # Execute the authoritative lifecycle cancellation first. The whole request
    # remains one DB transaction, so any failure while reversing variance Stock
    # Entries rolls back the complete cancellation.
    from almdina_erp.almdina_erp.services.order_lifecycle_service import cancel_order as cancel_core

    result = cancel_core(
        order_name=order_name,
        reason=reason,
        reverse_stock=reverse_stock,
    )

    reversed_adjustments: list[str] = []
    if int(reverse_stock):
        logs = frappe.get_all(
            "Material Consumption Log",
            filters={"door_cutting_order": order_name},
            fields=["name", "adjustment_issue_stock_entry", "adjustment_return_stock_entry"],
        )
        for row in logs:
            for stock_entry_name in (
                row.adjustment_issue_stock_entry,
                row.adjustment_return_stock_entry,
            ):
                if not stock_entry_name:
                    continue
                entry = frappe.get_doc("Stock Entry", stock_entry_name)
                if entry.docstatus == 1:
                    entry.cancel()
                reversed_adjustments.append(entry.name)

    from almdina_erp.almdina_erp.services.cost_service import sync_order_costs

    result["reversed_actual_consumption_adjustments"] = reversed_adjustments
    result["cost_summary"] = sync_order_costs(order_name)
    return result
