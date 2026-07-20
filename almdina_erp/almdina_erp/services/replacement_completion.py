from __future__ import annotations

from typing import Any

import frappe


@frappe.whitelist()
def complete_replacement(
    replacement_name: str,
    internal_loss_cost_usd: float | None = None,
) -> dict[str, Any]:
    # Direct Python call intentionally bypasses whitelisted-method override
    # dispatch, avoiding recursion while preserving the authoritative original
    # replacement lifecycle implementation.
    from almdina_erp.almdina_erp.services.replacement_service import complete_replacement as complete_core
    from almdina_erp.almdina_erp.services.cost_service import sync_order_costs

    result = complete_core(
        replacement_name=replacement_name,
        internal_loss_cost_usd=internal_loss_cost_usd,
    )
    order_name = frappe.db.get_value("Replacement Piece", replacement_name, "door_cutting_order")
    result["cost_summary"] = sync_order_costs(order_name) if order_name else {}
    return result
