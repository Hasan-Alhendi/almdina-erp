from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.orders.lifecycle import is_cutting_like_stage


def consume_stock_if_due(order_name: str, stage_type: str, trigger: str) -> None:
    if not is_cutting_like_stage(stage_type):
        return
    if not frappe.db.get_value("Door Cutting Order", order_name, "approved_plan"):
        return
    from almdina_erp.almdina_erp.services.stock_service import (
        consume_planned_material_if_due,
    )

    consume_planned_material_if_due(order_name, trigger=trigger)


__all__ = ["consume_stock_if_due"]
