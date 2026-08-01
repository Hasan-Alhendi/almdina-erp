from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.application.orders.lifecycle_permissions import (
    OrderLifecycleAction,
)
from almdina_erp.almdina_erp.services.order_lifecycle_permission_service import (
    require_lifecycle_action,
)


def _cutting_stage(order_name: str) -> Any | None:
    name = frappe.db.get_value(
        "Production Stage",
        {
            "door_cutting_order": order_name,
            "stage_type": "Cutting",
            "piece_label": ["in", ["", None]],
        },
        "name",
    )
    return frappe.get_doc("Production Stage", name) if name else None


def _cancel_stages(order_name: str, reason: str) -> list[str]:
    from almdina_erp.almdina_erp.services.production_service import _log_event

    stages = frappe.get_all(
        "Production Stage",
        filters={"door_cutting_order": order_name},
        pluck="name",
    )
    cancelled: list[str] = []
    for name in stages:
        stage = frappe.get_doc("Production Stage", name)
        if stage.status in {"Completed", "Cancelled"}:
            continue
        stage.status = "Cancelled"
        stage.notes = (
            (stage.notes or "")
            + "\n"
            + _("Cancelled with order: {0}").format(reason)
        ).strip()
        stage.save(ignore_permissions=True)
        _log_event(stage, "Cancel", {"reason": reason})
        cancelled.append(name)
    return cancelled


def _cancel_unstarted_replacements(order_name: str, reason: str) -> list[str]:
    replacements = frappe.get_all(
        "Replacement Piece",
        filters={
            "door_cutting_order": order_name,
            "status": ["!=", "Cancelled"],
        },
        fields=["name", "status"],
    )

    physically_started = [
        row
        for row in replacements
        if row.status in {"In Progress", "Completed"}
    ]
    if physically_started:
        frappe.throw(
            _(
                "Order has replacement work already in progress or completed ({0}). "
                "Resolve that replacement before cancelling the order."
            ).format(", ".join(row.name for row in physically_started))
        )

    from almdina_erp.almdina_erp.services.replacement_execution import (
        cancel_replacement_for_order_cancellation,
    )

    cancelled: list[str] = []
    for row in replacements:
        if row.status in {"Pending Approval", "Approved"}:
            cancel_replacement_for_order_cancellation(
                row.name,
                reason=_("Order cancelled: {0}").format(reason),
            )
            cancelled.append(row.name)
    return cancelled


@frappe.whitelist()
def cancel_order(
    order_name: str,
    reason: str,
    reverse_stock: int | bool = 0,
) -> dict[str, Any]:
    del reverse_stock

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (order_name,),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_lifecycle_action(order, OrderLifecycleAction.CANCEL)

    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("Cancellation reason is required."))

    cutting = _cutting_stage(order.name)
    if cutting and cutting.status == "Completed":
        frappe.throw(
            _(
                "Cutting is already completed. A completed cutting operation "
                "cannot be cancelled automatically."
            )
        )

    cancelled_replacements = _cancel_unstarted_replacements(order.name, reason)
    cancelled_stages = _cancel_stages(order.name, reason)

    if order.approved_plan:
        plan = frappe.get_doc("Cutting Plan", order.approved_plan)
        if plan.status == "Approved":
            plan.flags.allow_status_transition = True
            plan.status = "Cancelled"
            plan.save(ignore_permissions=True)

    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "status",
        "Cancelled",
        update_modified=True,
    )
    order.add_comment(
        "Comment",
        text=_("Order cancelled by {0} on {1}. Reason: {2}").format(
            frappe.session.user,
            now_datetime(),
            reason,
        ),
    )

    return {
        "name": order.name,
        "status": "Cancelled",
        "cancelled_stages": cancelled_stages,
        "cancelled_replacements": cancelled_replacements,
    }
