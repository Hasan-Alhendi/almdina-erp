from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _missing(payload: dict[str, Any], fieldname: str) -> bool:
    return fieldname not in payload or payload.get(fieldname) in (None, "")


def apply_factory_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply configured defaults only to truly omitted values.

    Explicit numeric zero remains an intentional value and is never replaced.
    """
    values = dict(payload or {})
    settings = frappe.get_single("Almdina ERP Settings")

    if _missing(values, "kerf_mm"):
        values["kerf_mm"] = flt(settings.default_kerf_mm)
    if _missing(values, "trim_margin_mm"):
        values["trim_margin_mm"] = flt(settings.default_trim_margin_mm)
    if _missing(values, "cutting_cost_per_board_usd"):
        values["cutting_cost_per_board_usd"] = flt(settings.default_cutting_cost_per_board_usd)
    if _missing(values, "packing_mode"):
        values["packing_mode"] = settings.default_packing_mode or "Auto"
    return values


@frappe.whitelist()
def get_new_order_defaults() -> dict[str, Any]:
    require_any_role("Order Entry", "Production Manager")
    return apply_factory_defaults({})


@frappe.whitelist()
def create_door_cutting_order(payload: str | dict[str, Any]) -> dict[str, Any]:
    require_any_role("Order Entry", "Production Manager")
    values = frappe.parse_json(payload) if isinstance(payload, str) else dict(payload or {})
    if values.get("doctype") not in (None, "", "Door Cutting Order"):
        frappe.throw(_("This endpoint only creates Door Cutting Order documents."))

    values = apply_factory_defaults(values)
    values["doctype"] = "Door Cutting Order"
    values.pop("name", None)
    values.pop("status", None)
    values.pop("approved_plan", None)
    values.pop("revision", None)

    doc = frappe.get_doc(values)
    doc.insert()
    return {
        "name": doc.name,
        "status": doc.status,
        "revision": doc.revision,
        "kerf_mm": doc.kerf_mm,
        "trim_margin_mm": doc.trim_margin_mm,
        "cutting_cost_per_board_usd": doc.cutting_cost_per_board_usd,
        "packing_mode": doc.packing_mode,
        "required_boards": doc.required_boards,
        "waste_area_m2": doc.waste_area_m2,
        "total_cost_usd": doc.total_cost_usd,
    }
