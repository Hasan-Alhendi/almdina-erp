from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt


@frappe.whitelist()
def get_order_defaults() -> dict[str, Any]:
    settings = frappe.get_single("Almdina ERP Settings")
    return {
        "kerf_mm": flt(settings.default_kerf_mm),
        "trim_margin_mm": flt(settings.default_trim_margin_mm),
        "cutting_cost_per_board_usd": flt(settings.default_cutting_cost_per_board_usd),
        "packing_mode": settings.default_packing_mode or "Auto",
    }


@frappe.whitelist()
def get_board_defaults(board_item: str) -> dict[str, Any]:
    row = frappe.db.get_value(
        "Item",
        board_item,
        [
            "custom_is_mdf",
            "custom_board_length_mm",
            "custom_board_width_mm",
            "custom_board_thickness_mm",
            "custom_board_color",
            "custom_board_material",
            "custom_board_rate_usd",
        ],
        as_dict=True,
    )
    if not row or not cint(row.custom_is_mdf):
        frappe.throw(_("Selected Item is not marked as an MDF/cutting board."))
    return {
        "board_length_mm": flt(row.custom_board_length_mm),
        "board_width_mm": flt(row.custom_board_width_mm),
        "board_thickness_mm": flt(row.custom_board_thickness_mm),
        "board_color": row.custom_board_color or "",
        "board_material": row.custom_board_material or "",
        "board_rate_usd": flt(row.custom_board_rate_usd),
    }
