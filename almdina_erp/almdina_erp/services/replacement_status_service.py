from __future__ import annotations

import frappe


def sync_replacement_order_status(order_name: str) -> str:
    open_count = frappe.db.count(
        "Replacement Piece",
        filters={
            "door_cutting_order": order_name,
            "status": ["not in", ["Completed", "Cancelled"]],
        },
    )
    if open_count:
        status = "Replacement Required"
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            "status",
            status,
            update_modified=True,
        )
        return status

    from almdina_erp.almdina_erp.services.order_status_sync_service import (
        sync_order_status,
    )

    return sync_order_status(order_name)
