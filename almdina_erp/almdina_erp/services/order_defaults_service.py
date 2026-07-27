from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_order_defaults() -> dict[str, Any]:
    settings = frappe.get_single("Almdina ERP Settings")
    return {
        "kerf_mm": flt(settings.default_kerf_mm),
        "trim_margin_mm": flt(settings.default_trim_margin_mm),
        "cutting_cost_per_board_usd": flt(settings.default_cutting_cost_per_board_usd),
        "packing_mode": settings.default_packing_mode or "Auto Pro",
        "cutting_machine_type": settings.default_cutting_machine_type or "Auto",
        "optimization_time_limit_sec": flt(settings.default_optimization_time_limit_sec) or 10,
    }
