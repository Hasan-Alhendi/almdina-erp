from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _lock_pending_order(order_name: str) -> None:
    rows = frappe.db.sql(
        "select name, status from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Door Cutting Order {0} does not exist.").format(order_name))
    if rows[0].status != "Pending Review":
        frappe.throw(
            _("Order {0} is no longer Pending Review. Current status: {1}").format(
                order_name,
                rows[0].status,
            )
        )


@frappe.whitelist()
def get_pending_review_orders(limit: int = 100) -> list[dict[str, Any]]:
    require_any_role("Production Manager")
    return frappe.get_all(
        "Door Cutting Order",
        filters={"status": "Pending Review"},
        fields=[
            "name",
            "customer",
            "order_date",
            "revision",
            "board_item",
            "board_material",
            "board_color",
            "board_thickness_mm",
            "required_boards",
            "waste_percent",
            "packing_method",
            "modified",
        ],
        order_by="modified asc",
        limit_page_length=max(1, min(500, int(limit or 100))),
    )


@frappe.whitelist()
def approve_order_safely(order_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    _lock_pending_order(order_name)

    from almdina_erp.almdina_erp.services.cutting_plan_service import approve_order

    result = approve_order(order_name)
    result["approval_path"] = "row_locked_queue"
    return result


@frappe.whitelist()
def reject_order_safely(order_name: str, reason: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    if not reason:
        frappe.throw(_("Rejection reason is required."))
    _lock_pending_order(order_name)

    from almdina_erp.almdina_erp.services.cutting_plan_service import reject_order

    result = reject_order(order_name, reason)
    result["approval_path"] = "row_locked_queue"
    return result
