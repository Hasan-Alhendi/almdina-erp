from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
    require_document_capability,
)


@frappe.whitelist()
def reject_order(order_name: str, reason: str | None = None) -> dict[str, Any]:
    require_doctype_capability(
        Capability.REJECT_ORDER,
        message=_("You do not have permission to reject orders."),
    )
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_document_capability(order, Capability.REJECT_ORDER)
    if order.status != "Pending Review":
        frappe.throw(_("Only orders in Pending Review can be rejected."))

    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("Rejection reason is required."))

    rejected_on = now_datetime()
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "status",
        "Rejected",
        update_modified=True,
    )
    order.add_comment(
        "Comment",
        text=_("Order rejected by {0} on {1}. Reason: {2}").format(
            frappe.session.user,
            rejected_on,
            reason,
        ),
    )
    return {
        "name": order.name,
        "status": "Rejected",
        "revision": order.revision,
        "rejected_on": rejected_on,
    }


__all__ = ["reject_order"]
