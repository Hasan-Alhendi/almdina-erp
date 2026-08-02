from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
    require_document_capability,
)


def _source_row_for_label(order: Any, piece_label: str) -> Any:
    try:
        group_no = int(str(piece_label).split(".", 1)[0])
    except (TypeError, ValueError):
        frappe.throw(_("Invalid original piece label {0}.").format(piece_label))

    if group_no < 1 or group_no > len(order.pieces or []):
        frappe.throw(
            _("Piece label {0} does not exist in order {1}.").format(
                piece_label,
                order.name,
            )
        )
    return order.pieces[group_no - 1]


def _create_replacement(incident: Any, order: Any) -> Any:
    if incident.replacement_piece:
        return frappe.get_doc("Replacement Piece", incident.replacement_piece)

    source_row = _source_row_for_label(order, incident.piece_label)
    replacement = frappe.new_doc("Replacement Piece")
    replacement.door_cutting_order = order.name
    replacement.incident = incident.name
    replacement.original_piece_label = incident.piece_label
    replacement.status = "Pending Approval"
    replacement.board_description = str(order.board_description or "").strip()
    replacement.width_cm = flt(source_row.width_cm)
    replacement.length_cm = flt(source_row.length_cm)
    replacement.qty = 1
    replacement.allow_rotation = cint(source_row.allow_rotation)
    replacement.edge_long_right = cint(source_row.edge_long_right)
    replacement.edge_long_left = cint(source_row.edge_long_left)
    replacement.edge_width_top = cint(source_row.edge_width_top)
    replacement.edge_width_bottom = cint(source_row.edge_width_bottom)
    replacement.edge_type = source_row.edge_type or order.default_edge_type or ""
    replacement.source_preference = "Full Board"
    replacement.charge_customer = 0
    replacement.insert(ignore_permissions=True)

    frappe.db.set_value(
        "Production Incident",
        incident.name,
        {
            "status": "Replacement Created",
            "replacement_piece": replacement.name,
        },
        update_modified=True,
    )
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "status",
        "Replacement Required",
        update_modified=True,
    )
    replacement.add_comment(
        "Comment",
        text=_("Replacement created by {0} from incident {1}.").format(
            frappe.session.user,
            incident.name,
        ),
    )
    return replacement


@frappe.whitelist()
def record_incident(
    order_name: str,
    piece_label: str,
    reason: str,
    description: str,
    production_stage: str | None = None,
    requires_replacement: int | bool = 1,
) -> dict[str, Any]:
    require_doctype_capability(
        Capability.RECORD_INCIDENT,
        message=_("You do not have permission to record production incidents."),
    )
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_document_capability(order, Capability.RECORD_INCIDENT)
    _source_row_for_label(order, piece_label)

    reason = str(reason or "").strip()
    description = str(description or "").strip()
    if not reason:
        frappe.throw(_("Incident reason is required."))
    if not description:
        frappe.throw(_("Incident description is required."))

    should_create_replacement = bool(cint(requires_replacement))
    if should_create_replacement:
        require_document_capability(
            order,
            Capability.CREATE_REPLACEMENT,
            message=_("You may record the incident but cannot create a replacement piece."),
        )

    incident = frappe.new_doc("Production Incident")
    incident.door_cutting_order = order.name
    incident.piece_label = piece_label
    incident.production_stage = production_stage
    incident.worker = frappe.session.user
    incident.reason = reason
    incident.description = description
    incident.requires_replacement = cint(should_create_replacement)
    incident.insert(ignore_permissions=True)

    replacement_name = None
    if should_create_replacement:
        replacement = _create_replacement(incident, order)
        replacement_name = replacement.name

    return {
        "incident": incident.name,
        "status": incident.status,
        "replacement_piece": replacement_name,
        "order_status": frappe.db.get_value(
            "Door Cutting Order",
            order.name,
            "status",
        ),
    }


@frappe.whitelist()
def create_replacement_from_incident(
    incident_name: str,
) -> dict[str, Any]:
    require_doctype_capability(
        Capability.CREATE_REPLACEMENT,
        message=_("You do not have permission to create replacement pieces."),
    )
    incident = frappe.get_doc("Production Incident", incident_name)
    if not cint(incident.requires_replacement):
        frappe.throw(_("This incident is not marked as requiring a replacement."))
    order = frappe.get_doc("Door Cutting Order", incident.door_cutting_order)
    order.check_permission("read")
    require_document_capability(order, Capability.CREATE_REPLACEMENT)
    replacement = _create_replacement(incident, order)
    return {
        "replacement_piece": replacement.name,
        "status": replacement.status,
    }
