from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    require_any_doctype_capability,
    require_doctype_capability,
)


_QUEUE_CAPABILITIES = (Capability.APPROVE_ORDER, Capability.REJECT_ORDER)


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
def get_approval_queue_context() -> dict[str, Any]:
    require_any_doctype_capability(
        _QUEUE_CAPABILITIES,
        message=_("You do not have permission to access the approval queue."),
    )
    return {
        "can_approve": doctype_has_capability(Capability.APPROVE_ORDER),
        "can_reject": doctype_has_capability(Capability.REJECT_ORDER),
    }


@frappe.whitelist()
def get_pending_review_orders(limit: int = 100) -> list[dict[str, Any]]:
    require_any_doctype_capability(
        _QUEUE_CAPABILITIES,
        message=_("You do not have permission to access the approval queue."),
    )
    return frappe.get_list(
        "Door Cutting Order",
        filters={"status": "Pending Review"},
        fields=[
            "name",
            "customer",
            "order_date",
            "revision",
            "board_description",
            "board_length_cm",
            "board_width_cm",
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
    require_doctype_capability(
        Capability.APPROVE_ORDER,
        message=_("You do not have permission to approve orders."),
    )
    _lock_pending_order(order_name)

    from almdina_erp.almdina_erp.services.order_approval_service import approve_order

    result = approve_order(order_name)
    result["approval_path"] = "row_locked_queue"
    return result


@frappe.whitelist()
def reject_order_safely(order_name: str, reason: str) -> dict[str, Any]:
    require_doctype_capability(
        Capability.REJECT_ORDER,
        message=_("You do not have permission to reject orders."),
    )
    _lock_pending_order(order_name)

    from almdina_erp.almdina_erp.services.order_review_service import reject_order

    result = reject_order(order_name, reason)
    result["approval_path"] = "row_locked_queue"
    return result


__all__ = [
    "approve_order_safely",
    "get_approval_queue_context",
    "get_pending_review_orders",
    "reject_order_safely",
]
