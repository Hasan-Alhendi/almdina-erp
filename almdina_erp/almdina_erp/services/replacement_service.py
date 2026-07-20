from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _source_row_for_label(order: Any, piece_label: str) -> Any:
    try:
        group_no = int(str(piece_label).split(".", 1)[0])
    except (TypeError, ValueError):
        frappe.throw(_("Invalid original piece label {0}.").format(piece_label))

    if group_no < 1 or group_no > len(order.pieces or []):
        frappe.throw(_("Piece label {0} does not exist in order {1}.").format(piece_label, order.name))
    return order.pieces[group_no - 1]


def _remnant_fits(remnant: Any, width_mm: float, length_mm: float, allow_rotation: bool) -> bool:
    normal = width_mm <= flt(remnant.width_mm) and length_mm <= flt(remnant.length_mm)
    rotated = allow_rotation and length_mm <= flt(remnant.width_mm) and width_mm <= flt(remnant.length_mm)
    return normal or rotated


def find_best_matching_remnant(
    board_item: str,
    width_cm: float,
    length_cm: float,
    allow_rotation: bool,
) -> str | None:
    """Return the smallest fitting available remnant for the exact board Item."""

    width_mm = flt(width_cm) * 10
    length_mm = flt(length_cm) * 10
    candidates = frappe.get_all(
        "Board Remnant",
        filters={"board_item": board_item, "status": "Available"},
        fields=["name", "width_mm", "length_mm", "area_m2"],
        order_by="area_m2 asc, modified asc",
    )
    for candidate in candidates:
        if _remnant_fits(candidate, width_mm, length_mm, bool(allow_rotation)):
            return candidate.name
    return None


def _reserve_remnant_atomic(remnant_name: str, order_name: str) -> None:
    rows = frappe.db.sql(
        """
        select name, status, reserved_for_order
        from `tabBoard Remnant`
        where name = %s
        for update
        """,
        (remnant_name,),
        as_dict=True,
    )
    if not rows or rows[0].status != "Available":
        frappe.throw(_("Remnant {0} is no longer available.").format(remnant_name))

    frappe.db.set_value(
        "Board Remnant",
        remnant_name,
        {
            "status": "Reserved",
            "reserved_for_order": order_name,
            "reservation_timestamp": now_datetime(),
        },
        update_modified=True,
    )


def _sync_replacement_order_status(order_name: str) -> str:
    open_count = frappe.db.count(
        "Replacement Piece",
        filters={
            "door_cutting_order": order_name,
            "status": ["not in", ["Completed", "Cancelled"]],
        },
    )
    if open_count:
        status = "Replacement Required"
        frappe.db.set_value("Door Cutting Order", order_name, "status", status, update_modified=True)
        return status

    from almdina_erp.almdina_erp.services.production_service import sync_order_status

    return sync_order_status(order_name)


@frappe.whitelist()
def record_incident(
    order_name: str,
    piece_label: str,
    reason: str,
    description: str,
    production_stage: str | None = None,
    requires_replacement: int | bool = 1,
) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Edge Operator", "Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    _source_row_for_label(order, piece_label)

    incident = frappe.new_doc("Production Incident")
    incident.door_cutting_order = order.name
    incident.piece_label = piece_label
    incident.production_stage = production_stage
    incident.worker = frappe.session.user
    incident.reason = reason
    incident.description = description
    incident.requires_replacement = cint(requires_replacement)
    incident.insert(ignore_permissions=True)

    replacement_name = None
    if incident.requires_replacement:
        replacement = _create_replacement(incident, order)
        replacement_name = replacement.name

    return {
        "incident": incident.name,
        "status": incident.status,
        "replacement_piece": replacement_name,
        "order_status": frappe.db.get_value("Door Cutting Order", order.name, "status"),
    }


def _create_replacement(incident: Any, order: Any) -> Any:
    if incident.replacement_piece:
        return frappe.get_doc("Replacement Piece", incident.replacement_piece)

    source_row = _source_row_for_label(order, incident.piece_label)
    replacement = frappe.new_doc("Replacement Piece")
    replacement.door_cutting_order = order.name
    replacement.incident = incident.name
    replacement.original_piece_label = incident.piece_label
    replacement.status = "Planned"
    replacement.board_item = order.board_item
    replacement.width_cm = flt(source_row.width_cm)
    replacement.length_cm = flt(source_row.length_cm)
    replacement.qty = 1
    replacement.allow_rotation = cint(source_row.allow_rotation)
    replacement.edge_long_right = cint(source_row.edge_long_right)
    replacement.edge_long_left = cint(source_row.edge_long_left)
    replacement.edge_width_top = cint(source_row.edge_width_top)
    replacement.edge_width_bottom = cint(source_row.edge_width_bottom)
    replacement.edge_type = source_row.edge_type or order.default_edge_type or ""
    replacement.source_preference = "Remnant First"
    replacement.charge_customer = 0

    settings = frappe.get_single("Almdina ERP Settings")
    if cint(settings.prefer_remnants_before_full_boards):
        remnant_name = find_best_matching_remnant(
            order.board_item,
            replacement.width_cm,
            replacement.length_cm,
            bool(replacement.allow_rotation),
        )
        if remnant_name:
            _reserve_remnant_atomic(remnant_name, order.name)
            replacement.selected_remnant = remnant_name

    replacement.insert(ignore_permissions=True)

    frappe.db.set_value(
        "Production Incident",
        incident.name,
        {"status": "Replacement Created", "replacement_piece": replacement.name},
        update_modified=True,
    )
    frappe.db.set_value("Door Cutting Order", order.name, "status", "Replacement Required", update_modified=True)
    return replacement


@frappe.whitelist()
def create_replacement_from_incident(incident_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    incident = frappe.get_doc("Production Incident", incident_name)
    if not cint(incident.requires_replacement):
        frappe.throw(_("This incident is not marked as requiring a replacement."))
    order = frappe.get_doc("Door Cutting Order", incident.door_cutting_order)
    replacement = _create_replacement(incident, order)
    return {
        "replacement_piece": replacement.name,
        "selected_remnant": replacement.selected_remnant,
        "status": replacement.status,
    }


@frappe.whitelist()
def start_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Production Manager")
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Planned":
        frappe.throw(_("Only a Planned replacement can be started."))
    frappe.db.set_value("Replacement Piece", replacement.name, "status", "In Progress", update_modified=True)
    return {"replacement_piece": replacement.name, "status": "In Progress"}


@frappe.whitelist()
def complete_replacement(
    replacement_name: str,
    internal_loss_cost_usd: float | None = None,
) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Production Manager")
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status not in {"Planned", "In Progress"}:
        frappe.throw(_("Only a Planned or In Progress replacement can be completed."))

    if replacement.selected_remnant:
        rows = frappe.db.sql(
            """
            select status, reserved_for_order
            from `tabBoard Remnant`
            where name = %s
            for update
            """,
            (replacement.selected_remnant,),
            as_dict=True,
        )
        if not rows or rows[0].status != "Reserved" or rows[0].reserved_for_order != replacement.door_cutting_order:
            frappe.throw(_("The selected remnant reservation is no longer valid."))
        frappe.db.set_value(
            "Board Remnant",
            replacement.selected_remnant,
            {"status": "Consumed", "reserved_for_order": None, "reservation_timestamp": None},
            update_modified=True,
        )

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Completed",
            "internal_loss_cost_usd": flt(internal_loss_cost_usd),
            "charge_customer": 0,
            "completed_on": now_datetime(),
        },
        update_modified=True,
    )
    frappe.db.set_value("Production Incident", replacement.incident, "status", "Resolved", update_modified=True)
    order_status = _sync_replacement_order_status(replacement.door_cutting_order)

    return {
        "replacement_piece": replacement.name,
        "status": "Completed",
        "order_status": order_status,
        "internal_loss_cost_usd": flt(internal_loss_cost_usd),
        "charge_customer": 0,
    }


@frappe.whitelist()
def cancel_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status == "Completed":
        frappe.throw(_("A completed replacement cannot be cancelled."))

    if replacement.selected_remnant:
        frappe.db.sql(
            """
            select name from `tabBoard Remnant`
            where name = %s
            for update
            """,
            (replacement.selected_remnant,),
        )
        current = frappe.db.get_value(
            "Board Remnant",
            replacement.selected_remnant,
            ["status", "reserved_for_order"],
            as_dict=True,
        )
        if current and current.status == "Reserved" and current.reserved_for_order == replacement.door_cutting_order:
            frappe.db.set_value(
                "Board Remnant",
                replacement.selected_remnant,
                {"status": "Available", "reserved_for_order": None, "reservation_timestamp": None},
                update_modified=True,
            )

    frappe.db.set_value("Replacement Piece", replacement.name, "status", "Cancelled", update_modified=True)
    frappe.db.set_value("Production Incident", replacement.incident, "status", "Resolved", update_modified=True)
    order_status = _sync_replacement_order_status(replacement.door_cutting_order)
    return {"replacement_piece": replacement.name, "status": "Cancelled", "order_status": order_status}
