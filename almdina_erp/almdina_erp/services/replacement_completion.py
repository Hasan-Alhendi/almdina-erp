from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, now_datetime


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

    replacement = frappe.db.get_value(
        "Replacement Piece",
        replacement_name,
        ["door_cutting_order", "cutting_plan"],
        as_dict=True,
    )
    if replacement and replacement.cutting_plan:
        plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
        generated = result.get("generated_remnants") or []
        reusable = sum(
            flt(frappe.db.get_value("Board Remnant", name, "area_m2"))
            for name in generated
        )
        reusable = min(max(0.0, reusable), max(0.0, flt(plan.waste_area_m2)))
        scrap = max(0.0, flt(plan.waste_area_m2) - reusable)
        frappe.db.set_value(
            "Cutting Plan",
            plan.name,
            {
                "reusable_remnant_area_m2": reusable,
                "scrap_area_m2": scrap,
                "waste_reconciled_on": now_datetime(),
            },
            update_modified=True,
        )
        result["waste_reconciliation"] = {
            "reusable_remnant_area_m2": reusable,
            "scrap_area_m2": scrap,
        }

    order_name = replacement.door_cutting_order if replacement else None
    result["cost_summary"] = sync_order_costs(order_name) if order_name else {}
    return result
