from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _active_replacement_reservation(replacement_name: str, plan_name: str) -> Any | None:
    name = frappe.db.get_value(
        "Material Reservation",
        {
            "replacement_piece": replacement_name,
            "cutting_plan": plan_name,
            "status": "Active",
        },
        "name",
    )
    return frappe.get_doc("Material Reservation", name) if name else None


def _materials_to_consume(replacement: Any, plan: Any, reservation: Any | None) -> list[dict[str, Any]]:
    if reservation:
        return [
            {
                "item_code": row.item_code,
                "qty": flt(row.qty),
                "warehouse": row.warehouse,
            }
            for row in (reservation.items or [])
            if flt(row.qty) > 0
        ]

    from almdina_erp.almdina_erp.services.replacement_service import _replacement_materials
    from almdina_erp.almdina_erp.services.stock_service import get_settings

    settings = get_settings()
    if not settings.default_warehouse:
        frappe.throw(_("Set Default Warehouse before starting a replacement."))
    return [
        {
            "item_code": row["item_code"],
            "qty": flt(row["qty"]),
            "warehouse": settings.default_warehouse,
        }
        for row in _replacement_materials(replacement, plan)
        if flt(row.get("qty")) > 0
    ]


def _validate_available_stock(materials: list[dict[str, Any]], reservation: Any | None) -> None:
    from almdina_erp.almdina_erp.services.stock_service import _active_reserved_qty, _stock_balance

    for row in sorted(materials, key=lambda item: (item["warehouse"], item["item_code"])):
        frappe.db.sql(
            "select name from `tabBin` where item_code = %s and warehouse = %s for update",
            (row["item_code"], row["warehouse"]),
        )

    for row in materials:
        actual = _stock_balance(row["item_code"], row["warehouse"])
        reserved_other = _active_reserved_qty(
            row["item_code"],
            row["warehouse"],
            exclude_reservation=reservation.name if reservation else None,
        )
        available_for_this_job = max(0.0, actual - reserved_other)
        if available_for_this_job + 1e-9 < flt(row["qty"]):
            frappe.throw(
                _(
                    "Insufficient stock for replacement Item {0}: required {1}, "
                    "available after other reservations {2} in {3}."
                ).format(
                    row["item_code"],
                    row["qty"],
                    available_for_this_job,
                    row["warehouse"],
                )
            )


def _create_material_issue(replacement: Any, plan: Any, materials: list[dict[str, Any]]) -> str | None:
    if not materials:
        return None

    warehouses = {row["warehouse"] for row in materials}
    if len(warehouses) != 1:
        frappe.throw(_("Replacement materials must be consumed from one configured warehouse."))
    warehouse = next(iter(warehouses))
    company = frappe.db.get_value("Warehouse", warehouse, "company")
    if not company:
        frappe.throw(_("Warehouse {0} is not linked to a Company.").format(warehouse))

    entry = frappe.new_doc("Stock Entry")
    if entry.meta.has_field("stock_entry_type"):
        entry.stock_entry_type = "Material Issue"
    if entry.meta.has_field("purpose"):
        entry.purpose = "Material Issue"
    if entry.meta.has_field("company"):
        entry.company = company
    entry.remarks = _("Replacement material issue | {0} | Plan {1}").format(replacement.name, plan.name)

    for row in materials:
        entry.append(
            "items",
            {
                "item_code": row["item_code"],
                "s_warehouse": row["warehouse"],
                "qty": flt(row["qty"]),
            },
        )
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry.name


@frappe.whitelist()
def start_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Approved":
        frappe.throw(_("Only an Approved replacement can be started."))
    if replacement.stock_entry:
        frappe.throw(_("Replacement already has a material Stock Entry and cannot be started twice."))
    if not replacement.cutting_plan:
        frappe.throw(_("Replacement has no approved Mini Cutting Plan."))

    plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
    if plan.status != "Approved" or plan.plan_kind != "Replacement":
        frappe.throw(_("Replacement Mini Cutting Plan is not approved."))

    if plan.required_boards:
        from almdina_erp.almdina_erp.services.stock_service import _validate_board_stock_uom

        _validate_board_stock_uom(replacement.board_item)

    reservation = _active_replacement_reservation(replacement.name, plan.name)
    materials = _materials_to_consume(replacement, plan, reservation)
    _validate_available_stock(materials, reservation)
    stock_entry = _create_material_issue(replacement, plan, materials)

    if reservation:
        reservation.flags.allow_status_transition = True
        reservation.status = "Consumed"
        reservation.released_on = now_datetime()
        reservation.save(ignore_permissions=True)

    from almdina_erp.almdina_erp.services.replacement_service import _consume_selected_remnant

    _consume_selected_remnant(replacement)
    started_on = now_datetime()
    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "In Progress",
            "started_by": frappe.session.user,
            "started_on": started_on,
            "stock_entry": stock_entry,
        },
        update_modified=True,
    )
    return {
        "replacement_piece": replacement.name,
        "status": "In Progress",
        "stock_entry": stock_entry,
        "cutting_plan": plan.name,
        "used_material_reservation": reservation.name if reservation else None,
        "started_on": started_on,
    }
