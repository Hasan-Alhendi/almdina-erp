from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _reserve_identity_matched_remnant(replacement: Any, order: Any) -> Any | None:
    from almdina_erp.almdina_erp.services.replacement_service import _remnant_fits

    settings = frappe.get_single("Almdina ERP Settings")
    if not cint(settings.prefer_remnants_before_full_boards) or replacement.source_preference == "Full Board":
        return None

    rows = frappe.db.sql(
        """
        select name, board_item, length_mm, width_mm, thickness_mm, material, color,
               area_m2, warehouse, location, parent_remnant
        from `tabBoard Remnant`
        where board_item = %s
          and status = 'Available'
          and coalesce(material, '') = %s
          and coalesce(color, '') = %s
          and abs(coalesce(thickness_mm, 0) - %s) <= 0.001
        order by area_m2 asc, creation asc
        for update
        """,
        (
            replacement.board_item,
            order.board_material or "",
            order.board_color or "",
            flt(order.board_thickness_mm),
        ),
        as_dict=True,
    )
    for remnant in rows:
        if not _remnant_fits(
            remnant,
            replacement.width_cm,
            replacement.length_cm,
            bool(replacement.allow_rotation),
            flt(order.trim_margin_mm),
        ):
            continue
        frappe.db.set_value(
            "Board Remnant",
            remnant.name,
            {
                "status": "Reserved",
                "reserved_for_order": order.name,
                "reservation_timestamp": now_datetime(),
            },
            update_modified=True,
        )
        return remnant
    return None


@frappe.whitelist()
def approve_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Pending Approval":
        frappe.throw(_("Only a Pending Approval replacement can be approved."))

    order = frappe.get_doc("Door Cutting Order", replacement.door_cutting_order)
    remnant = _reserve_identity_matched_remnant(replacement, order)

    from almdina_erp.almdina_erp.services.replacement_service import (
        _build_replacement_snapshot,
        _reserve_replacement_materials,
    )
    from almdina_erp.almdina_erp.services.replacement_plan_service import create_mini_plan

    snapshot = _build_replacement_snapshot(order, replacement, remnant)
    plan = create_mini_plan(order, replacement, snapshot, remnant)

    # Physical remnant reservation is always required once selected so it cannot
    # be assigned twice. Stock-item reservation follows the same optional factory
    # policy as normal orders; start-time consumption will revalidate if disabled.
    settings = frappe.get_single("Almdina ERP Settings")
    material_reservation = None
    if cint(settings.reserve_stock_on_approval):
        material_reservation = _reserve_replacement_materials(replacement, plan)

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Approved",
            "approved_by": frappe.session.user,
            "approved_on": now_datetime(),
            "selected_remnant": remnant.name if remnant else None,
            "cutting_plan": plan.name,
            "planned_internal_loss_usd": flt(plan.total_cost_usd),
            "charge_customer": 0,
        },
        update_modified=True,
    )
    return {
        "replacement_piece": replacement.name,
        "status": "Approved",
        "cutting_plan": plan.name,
        "selected_remnant": remnant.name if remnant else None,
        "material_reservation": material_reservation,
        "planned_internal_loss_usd": flt(plan.total_cost_usd),
    }
