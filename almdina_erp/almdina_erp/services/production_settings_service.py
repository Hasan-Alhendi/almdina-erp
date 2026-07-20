from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.services.cutting_engine import PACKING_OPTIONS
from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


@frappe.whitelist()
def get_production_settings() -> dict[str, Any]:
    require_any_role("Production Manager")
    settings = frappe.get_single("Almdina ERP Settings")
    return {
        "default_production_routing": settings.default_production_routing,
        "default_kerf_mm": flt(settings.default_kerf_mm),
        "default_trim_margin_mm": flt(settings.default_trim_margin_mm),
        "default_cutting_cost_per_board_usd": flt(settings.default_cutting_cost_per_board_usd),
        "default_packing_mode": settings.default_packing_mode or "Auto",
        "packing_options": list(PACKING_OPTIONS),
        "allow_stage_override": int(settings.allow_stage_override or 0),
    }


@frappe.whitelist()
def update_production_settings(values: str | dict[str, Any]) -> dict[str, Any]:
    require_any_role("Production Manager")
    payload = frappe.parse_json(values) if isinstance(values, str) else dict(values or {})
    settings = frappe.get_single("Almdina ERP Settings")

    routing_name = payload.get("default_production_routing") or None
    if not routing_name:
        frappe.throw(_("Default Production Routing is required."))
    routing = frappe.db.get_value(
        "Production Routing",
        routing_name,
        ["name", "disabled"],
        as_dict=True,
    )
    if not routing:
        frappe.throw(_("Production Routing {0} does not exist.").format(routing_name))
    if routing.disabled:
        frappe.throw(_("Production Routing {0} is disabled.").format(routing_name))

    kerf = flt(payload.get("default_kerf_mm"))
    trim = flt(payload.get("default_trim_margin_mm"))
    cutting_cost = flt(payload.get("default_cutting_cost_per_board_usd"))
    for label, value in (
        (_("Default Kerf MM"), kerf),
        (_("Default Trim Margin MM"), trim),
        (_("Default Cutting Cost / Board USD"), cutting_cost),
    ):
        if value < 0:
            frappe.throw(_("{0} cannot be negative.").format(label))

    packing_mode = payload.get("default_packing_mode") or "Auto"
    if packing_mode not in PACKING_OPTIONS:
        frappe.throw(_("Unsupported Packing Mode: {0}").format(packing_mode))

    settings.default_production_routing = routing_name
    settings.default_kerf_mm = kerf
    settings.default_trim_margin_mm = trim
    settings.default_cutting_cost_per_board_usd = cutting_cost
    settings.default_packing_mode = packing_mode
    settings.save(ignore_permissions=True)
    settings.add_comment(
        "Comment",
        text=_("Production defaults updated by {0}.").format(frappe.session.user),
    )
    return get_production_settings()
