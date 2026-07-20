from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt


def _internal_loss(order_name: str) -> float:
    return flt(
        frappe.db.sql(
            """
            select coalesce(sum(internal_loss_cost_usd), 0)
            from `tabReplacement Piece`
            where door_cutting_order = %s
              and status = 'Completed'
              and coalesce(charge_customer, 0) = 0
            """,
            (order_name,),
        )[0][0]
    )


def _material_variance(order_name: str) -> float:
    return flt(
        frappe.db.sql(
            """
            select coalesce(sum(material_variance_cost_usd), 0)
            from `tabMaterial Consumption Log`
            where door_cutting_order = %s
              and status = 'Submitted'
              and coalesce(actual_recorded, 0) = 1
            """,
            (order_name,),
        )[0][0]
    )


def get_order_cost_summary(order_name: str) -> dict[str, Any]:
    order = frappe.get_doc("Door Cutting Order", order_name)
    planned_cost = flt(order.total_cost_usd)

    if order.approved_plan:
        planned_cost = flt(
            frappe.db.get_value("Cutting Plan", order.approved_plan, "total_cost_usd")
        ) or planned_cost

    internal_loss = _internal_loss(order_name)
    material_variance = _material_variance(order_name)
    actual_cost = planned_cost + material_variance + internal_loss

    return {
        "planned_cost_usd": planned_cost,
        "material_variance_cost_usd": material_variance,
        "internal_loss_cost_usd": internal_loss,
        "actual_cost_usd": actual_cost,
        "variance_usd": actual_cost - planned_cost,
    }


def sync_order_costs(order_name: str) -> dict[str, Any]:
    summary = get_order_cost_summary(order_name)
    frappe.db.set_value(
        "Door Cutting Order",
        order_name,
        {
            "actual_cost_usd": summary["actual_cost_usd"],
            "material_variance_cost_usd": summary["material_variance_cost_usd"],
            "internal_loss_cost_usd": summary["internal_loss_cost_usd"],
        },
        update_modified=True,
    )
    return summary


def on_replacement_update(doc: Any, method: str | None = None) -> None:
    if doc.door_cutting_order:
        sync_order_costs(doc.door_cutting_order)


def on_order_plan_update(doc: Any, method: str | None = None) -> None:
    if (doc.plan_kind or "Order") != "Order" or doc.status != "Approved" or not doc.door_cutting_order:
        return

    # This hook runs while the new approved plan may not yet be linked into the
    # order. Use this plan directly, but still include already-recorded actual
    # consumption variances and completed internal replacement losses.
    internal_loss = _internal_loss(doc.door_cutting_order)
    material_variance = _material_variance(doc.door_cutting_order)
    frappe.db.set_value(
        "Door Cutting Order",
        doc.door_cutting_order,
        {
            "actual_cost_usd": flt(doc.total_cost_usd) + material_variance + internal_loss,
            "material_variance_cost_usd": material_variance,
            "internal_loss_cost_usd": internal_loss,
        },
        update_modified=True,
    )


@frappe.whitelist()
def refresh_order_costs(order_name: str) -> dict[str, Any]:
    doc = frappe.get_doc("Door Cutting Order", order_name)
    doc.check_permission("read")
    return sync_order_costs(order_name)
