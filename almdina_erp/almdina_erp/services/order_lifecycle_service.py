from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _cutting_stage(order_name: str) -> Any | None:
    name = frappe.db.get_value(
        "Production Stage",
        {"door_cutting_order": order_name, "stage_type": "Cutting", "piece_label": ["in", ["", None]]},
        "name",
    )
    return frappe.get_doc("Production Stage", name) if name else None


def _cancel_stock_entries(order_name: str) -> list[str]:
    reversed_entries: list[str] = []
    logs = frappe.get_all(
        "Material Consumption Log",
        filters={"door_cutting_order": order_name, "status": "Submitted"},
        fields=["name", "stock_entry"],
    )
    for row in logs:
        if row.stock_entry:
            entry = frappe.get_doc("Stock Entry", row.stock_entry)
            if entry.docstatus == 1:
                entry.cancel()
                reversed_entries.append(entry.name)
        frappe.db.set_value("Material Consumption Log", row.name, "status", "Reversed", update_modified=True)
    return reversed_entries


def _release_remnants(order_name: str) -> list[str]:
    released: list[str] = []
    names = frappe.get_all(
        "Board Remnant",
        filters={"status": "Reserved", "reserved_for_order": order_name},
        pluck="name",
    )
    for name in names:
        frappe.db.sql("select name from `tabBoard Remnant` where name = %s for update", (name,))
        frappe.db.set_value(
            "Board Remnant",
            name,
            {"status": "Available", "reserved_for_order": None, "reservation_timestamp": None},
            update_modified=True,
        )
        released.append(name)
    return released


def _restore_consumed_source_remnants(order_name: str) -> list[str]:
    plan_name = frappe.db.get_value("Door Cutting Order", order_name, "approved_plan")
    if not plan_name:
        return []

    generated = frappe.db.exists("Board Remnant", {"source_order": order_name, "source_plan": plan_name})
    if generated:
        frappe.throw(
            _(
                "Cutting has already generated new physical remnants. Automatic cancellation cannot restore the original material safely. "
                "Reconcile physical stock/remnants first."
            )
        )

    names = frappe.get_all(
        "Cutting Plan Source",
        filters={"parent": plan_name, "parenttype": "Cutting Plan", "source_type": "Remnant"},
        pluck="remnant",
    )
    restored: list[str] = []
    for name in [n for n in names if n]:
        frappe.db.sql("select name from `tabBoard Remnant` where name = %s for update", (name,))
        status = frappe.db.get_value("Board Remnant", name, "status")
        if status == "Consumed":
            frappe.db.set_value(
                "Board Remnant",
                name,
                {"status": "Available", "reserved_for_order": None, "reservation_timestamp": None},
                update_modified=True,
            )
            restored.append(name)
    return restored


def _cancel_stages(order_name: str, reason: str) -> list[str]:
    from almdina_erp.almdina_erp.services.production_service import _log_event

    stages = frappe.get_all("Production Stage", filters={"door_cutting_order": order_name}, pluck="name")
    cancelled: list[str] = []
    for name in stages:
        stage = frappe.get_doc("Production Stage", name)
        if stage.status in {"Completed", "Cancelled"}:
            continue
        stage.status = "Cancelled"
        stage.notes = ((stage.notes or "") + "\n" + _("Cancelled with order: {0}").format(reason)).strip()
        stage.save(ignore_permissions=True)
        _log_event(stage, "Cancel", {"reason": reason})
        cancelled.append(name)
    return cancelled


@frappe.whitelist()
def cancel_order(
    order_name: str,
    reason: str,
    reverse_stock: int | bool = 0,
) -> dict[str, Any]:
    require_any_role("Production Manager")
    if not reason:
        frappe.throw(_("Cancellation reason is required."))

    frappe.db.sql("select name from `tabDoor Cutting Order` where name = %s for update", (order_name,))
    order = frappe.get_doc("Door Cutting Order", order_name)
    if order.status == "Cancelled":
        return {"name": order.name, "status": "Cancelled", "already_cancelled": True}
    if order.status == "Completed":
        frappe.throw(_("A completed order cannot be cancelled through the normal workflow."))

    cutting = _cutting_stage(order.name)
    if cutting and cutting.status == "Completed":
        frappe.throw(
            _(
                "Cutting is already completed. Reconcile physical stock/remnants before cancelling; automatic reversal is intentionally blocked."
            )
        )

    submitted_consumption = frappe.db.exists(
        "Material Consumption Log",
        {"door_cutting_order": order.name, "status": "Submitted"},
    )
    if submitted_consumption and not int(reverse_stock):
        frappe.throw(_("This order has submitted stock consumption. Enable explicit stock reversal to cancel it."))

    reversed_entries: list[str] = []
    restored_source_remnants: list[str] = []
    if submitted_consumption:
        reversed_entries = _cancel_stock_entries(order.name)
        restored_source_remnants = _restore_consumed_source_remnants(order.name)

    from almdina_erp.almdina_erp.services.stock_service import transition_order_reservation

    released_material_reservations = transition_order_reservation(order.name, "Released")
    released_remnants = _release_remnants(order.name)
    cancelled_stages = _cancel_stages(order.name, reason)

    if order.approved_plan:
        plan = frappe.get_doc("Cutting Plan", order.approved_plan)
        if plan.status == "Approved":
            plan.flags.allow_status_transition = True
            plan.status = "Cancelled"
            plan.save(ignore_permissions=True)

    frappe.db.set_value("Door Cutting Order", order.name, "status", "Cancelled", update_modified=True)
    order.add_comment(
        "Comment",
        text=_("Order cancelled by {0} on {1}. Reason: {2}").format(frappe.session.user, now_datetime(), reason),
    )

    return {
        "name": order.name,
        "status": "Cancelled",
        "reversed_stock_entries": reversed_entries,
        "released_material_reservations": released_material_reservations,
        "released_remnants": released_remnants,
        "restored_source_remnants": restored_source_remnants,
        "cancelled_stages": cancelled_stages,
    }
