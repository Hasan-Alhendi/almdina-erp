from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.orders.lifecycle import is_cutting_like_stage


def register_remnants_if_due(
    order_name: str,
    stage_type: str,
) -> dict[str, Any] | None:
    if not is_cutting_like_stage(stage_type):
        return None
    if not frappe.db.get_value("Door Cutting Order", order_name, "approved_plan"):
        return None
    from almdina_erp.almdina_erp.services.remnant_service import register_plan_remnants

    return register_plan_remnants(order_name)


__all__ = ["register_remnants_if_due"]
