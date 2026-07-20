from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


STOCK_CONSUMPTION_POINTS = {"Cutting Start", "Cutting Finish"}
REMNANT_COST_POLICIES = {"Zero", "Average Valuation", "Configured Rate"}


@frappe.whitelist()
def get_stock_settings() -> dict[str, Any]:
    require_any_role("Stock Manager", "Production Manager")
    settings = frappe.get_single("Almdina ERP Settings")
    return {
        "default_warehouse": settings.default_warehouse,
        "reserve_stock_on_approval": cint(settings.reserve_stock_on_approval),
        "stock_consumption_point": settings.stock_consumption_point or "Cutting Start",
        "prefer_remnants_before_full_boards": cint(settings.prefer_remnants_before_full_boards),
        "min_remnant_width_mm": flt(settings.min_remnant_width_mm),
        "min_remnant_length_mm": flt(settings.min_remnant_length_mm),
        "min_remnant_area_m2": flt(settings.min_remnant_area_m2),
        "remnant_cost_policy": settings.remnant_cost_policy or "Zero",
        "remnant_rate_usd_per_m2": flt(settings.remnant_rate_usd_per_m2),
        "can_edit": "System Manager" in frappe.get_roles() or "Stock Manager" in frappe.get_roles(),
    }


@frappe.whitelist()
def update_stock_settings(values: str | dict[str, Any]) -> dict[str, Any]:
    require_any_role("Stock Manager")
    payload = frappe.parse_json(values) if isinstance(values, str) else dict(values or {})
    settings = frappe.get_single("Almdina ERP Settings")

    warehouse = payload.get("default_warehouse") or None
    if warehouse and not frappe.db.exists("Warehouse", warehouse):
        frappe.throw(_("Warehouse {0} does not exist.").format(warehouse))

    consumption_point = payload.get("stock_consumption_point") or "Cutting Start"
    if consumption_point not in STOCK_CONSUMPTION_POINTS:
        frappe.throw(_("Invalid Stock Consumption Point."))

    remnant_policy = payload.get("remnant_cost_policy") or "Zero"
    if remnant_policy not in REMNANT_COST_POLICIES:
        frappe.throw(_("Invalid Remnant Cost Policy."))

    numeric_fields = {
        "min_remnant_width_mm": flt(payload.get("min_remnant_width_mm")),
        "min_remnant_length_mm": flt(payload.get("min_remnant_length_mm")),
        "min_remnant_area_m2": flt(payload.get("min_remnant_area_m2")),
        "remnant_rate_usd_per_m2": flt(payload.get("remnant_rate_usd_per_m2")),
    }
    for fieldname, value in numeric_fields.items():
        if value < 0:
            frappe.throw(_("{0} cannot be negative.").format(fieldname))

    settings.default_warehouse = warehouse
    settings.reserve_stock_on_approval = cint(payload.get("reserve_stock_on_approval"))
    settings.stock_consumption_point = consumption_point
    settings.prefer_remnants_before_full_boards = cint(payload.get("prefer_remnants_before_full_boards"))
    settings.min_remnant_width_mm = numeric_fields["min_remnant_width_mm"]
    settings.min_remnant_length_mm = numeric_fields["min_remnant_length_mm"]
    settings.min_remnant_area_m2 = numeric_fields["min_remnant_area_m2"]
    settings.remnant_cost_policy = remnant_policy
    settings.remnant_rate_usd_per_m2 = numeric_fields["remnant_rate_usd_per_m2"]
    settings.save(ignore_permissions=True)

    settings.add_comment(
        "Comment",
        text=_("Stock/remnant policy updated by {0}.").format(frappe.session.user),
    )
    return get_stock_settings()
