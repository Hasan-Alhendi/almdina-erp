from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _release_material_reservations(replacement_name: str) -> list[str]:
    names = frappe.get_all(
        "Material Reservation",
        filters={"replacement_piece": replacement_name, "status": "Active"},
        pluck="name",
    )
    released: list[str] = []
    for name in names:
        reservation = frappe.get_doc("Material Reservation", name)
        reservation.flags.allow_status_transition = True
        reservation.status = "Released"
        reservation.released_on = now_datetime()
        reservation.save(ignore_permissions=True)
        released.append(name)
    return released


def _release_or_restore_selected_remnant(replacement: Any) -> str | None:
    if not replacement.selected_remnant:
        return None

    rows = frappe.db.sql(
        "select status, reserved_for_order from `tabBoard Remnant` where name = %s for update",
        (replacement.selected_remnant,),
        as_dict=True,
    )
    if not rows:
        return None
    state = rows[0]

    # Before start it is Reserved; after safe stock reversal it may be Consumed.
    if state.status in {"Reserved", "Consumed"}:
        frappe.db.set_value(
            "Board Remnant",
            replacement.selected_remnant,
            {
                "status": "Available",
                "reserved_for_order": None,
                "reservation_timestamp": None,
            },
            update_modified=True,
        )
        return replacement.selected_remnant
    return None


def _cancel_mini_plan(replacement: Any) -> str | None:
    if not replacement.cutting_plan:
        return None
    plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
    if plan.status == "Approved":
        plan.flags.allow_status_transition = True
        plan.status = "Cancelled"
        plan.save(ignore_permissions=True)
    return plan.name


def _cancel_stock_entry(replacement: Any) -> str | None:
    if not replacement.stock_entry:
        return None
    entry = frappe.get_doc("Stock Entry", replacement.stock_entry)
    if entry.docstatus == 1:
        entry.cancel()
    return entry.name


@frappe.whitelist()
def cancel_replacement(
    replacement_name: str,
    reason: str,
    reverse_stock: int | bool = 0,
    cancel_with_order: int | bool = 0,
) -> dict[str, Any]:
    require_any_role("Production Manager")
    if not reason:
        frappe.throw(_("Cancellation reason is required."))

    frappe.db.sql(
        "select name from `tabReplacement Piece` where name = %s for update",
        (replacement_name,),
    )
    replacement = frappe.get_doc("Replacement Piece", replacement_name)

    if replacement.status == "Cancelled":
        return {"replacement_piece": replacement.name, "status": "Cancelled", "already_cancelled": True}
    if replacement.status == "Completed":
        frappe.throw(
            _(
                "Completed replacement {0} cannot be automatically cancelled because physical material has already changed."
            ).format(replacement.name)
        )

    if replacement.status == "In Progress" and replacement.stock_entry and not int(reverse_stock):
        frappe.throw(
            _(
                "Replacement {0} already consumed material. Explicit stock reversal is required before cancellation."
            ).format(replacement.name)
        )

    # A completed replacement is blocked above. Therefore generated remnants
    # should not exist for a cancellable flow; if they do, block rather than
    # pretending the physical source can be restored safely.
    generated = frappe.db.exists(
        "Board Remnant",
        {"source_plan": replacement.cutting_plan},
    ) if replacement.cutting_plan else None
    if generated:
        frappe.throw(
            _(
                "Replacement {0} already generated physical remnants. Reconcile physical stock before cancellation."
            ).format(replacement.name)
        )

    cancelled_stock_entry = None
    if replacement.status == "In Progress" and replacement.stock_entry:
        cancelled_stock_entry = _cancel_stock_entry(replacement)

    released_reservations = _release_material_reservations(replacement.name)
    restored_remnant = _release_or_restore_selected_remnant(replacement)
    cancelled_plan = _cancel_mini_plan(replacement)

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Cancelled",
            "completed_on": None,
        },
        update_modified=True,
    )
    replacement.add_comment(
        "Comment",
        text=_("Replacement cancelled by {0}. Reason: {1}").format(frappe.session.user, reason),
    )

    if replacement.incident:
        incident = frappe.get_doc("Production Incident", replacement.incident)
        if incident.status != "Resolved":
            frappe.db.set_value(
                "Production Incident",
                incident.name,
                "status",
                "Resolved",
                update_modified=True,
            )
            incident.add_comment(
                "Comment",
                text=_("Replacement was cancelled by Production Manager. Reason: {0}").format(reason),
            )

    from almdina_erp.almdina_erp.services.cost_service import sync_order_costs
    from almdina_erp.almdina_erp.services.production_service import sync_order_status

    cost_summary = sync_order_costs(replacement.door_cutting_order)
    order_status = sync_order_status(replacement.door_cutting_order)

    return {
        "replacement_piece": replacement.name,
        "status": "Cancelled",
        "cancelled_stock_entry": cancelled_stock_entry,
        "released_material_reservations": released_reservations,
        "restored_remnant": restored_remnant,
        "cancelled_plan": cancelled_plan,
        "order_status": order_status,
        "cost_summary": cost_summary,
        "cancel_with_order": bool(int(cancel_with_order)),
    }
