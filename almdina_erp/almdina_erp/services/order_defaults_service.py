from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    require_any_doctype_capability,
)


_ORDER_DEFAULT_CONSUMERS = (
    Capability.CREATE_ORDER,
    Capability.EDIT_ORDER,
    Capability.RECALCULATE_PLAN,
    Capability.EDIT_OPTIMIZER_SETTINGS,
)


@frappe.whitelist()
def get_order_defaults() -> dict[str, Any]:
    """Return operational defaults without exposing protected costing settings."""

    require_any_doctype_capability(
        _ORDER_DEFAULT_CONSUMERS,
        message=_("لا تملك صلاحية الوصول إلى إعدادات الطلب الافتراضية."),
    )
    settings = frappe.get_single("Almdina ERP Settings")
    payload: dict[str, Any] = {
        "kerf_mm": flt(settings.default_kerf_mm),
        "trim_margin_mm": flt(settings.default_trim_margin_mm),
        "packing_mode": settings.default_packing_mode or "Auto Pro",
        "cutting_machine_type": settings.default_cutting_machine_type or "Auto",
        "optimization_time_limit_sec": flt(settings.default_optimization_time_limit_sec) or 10,
    }
    if doctype_has_capability(Capability.VIEW_COSTS):
        payload["cutting_cost_per_board_usd"] = flt(
            settings.default_cutting_cost_per_board_usd
        )
    return payload


__all__ = ["get_order_defaults"]
