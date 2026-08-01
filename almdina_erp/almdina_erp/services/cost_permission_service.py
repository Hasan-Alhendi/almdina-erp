from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)


EDITABLE_ORDER_STATUSES = {"Draft", "Pending Review", "Rejected"}
ORDER_COST_FIELDS = (
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
    "special_shapes_baseline_cost_usd",
    "special_shapes_estimated_total_usd",
    "special_shapes_final_total_usd",
    "customer_quote_total_usd",
    "customer_quote_status",
    "material_variance_cost_usd",
    "internal_loss_cost_usd",
    "actual_cost_usd",
)
PIECE_COST_FIELDS = (
    "edge_long_rate_usd",
    "edge_width_rate_usd",
    "edge_long_cost_usd",
    "edge_width_cost_usd",
    "edge_cost_usd",
    "edge_rate_usd",
    "special_shape_estimated_unit_price_usd",
    "special_shape_custom_unit_price_usd",
    "special_shape_final_unit_price_usd",
    "special_shape_price_status",
    "special_shape_price_note",
    "special_shape_price_approved_by",
    "special_shape_price_approved_on",
)


def _finite_non_negative(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} must be a valid number.").format(label))
    if not math.isfinite(number):
        frappe.throw(_("{0} must be finite.").format(label))
    if number < 0:
        frappe.throw(_("{0} cannot be negative.").format(label))
    return number


def _authorized_order(order_name: str, capability: str) -> Any:
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_document_capability(order, capability)
    return order


def _special_piece(order: Any, piece_name: str) -> Any:
    for piece in order.pieces or []:
        if piece.name == piece_name:
            return piece
    frappe.throw(_("The selected door row does not belong to this order."))


def _piece_snapshot(piece: Any) -> dict[str, Any]:
    return {
        "name": piece.name,
        **{fieldname: getattr(piece, fieldname, None) for fieldname in PIECE_COST_FIELDS},
    }


def _cost_snapshot(order: Any) -> dict[str, Any]:
    return {
        "order_name": order.name,
        "order": {
            fieldname: getattr(order, fieldname, None)
            for fieldname in ORDER_COST_FIELDS
        },
        "pieces": [_piece_snapshot(piece) for piece in (order.pieces or [])],
    }


@frappe.whitelist()
def get_order_cost_snapshot(order_name: str) -> dict[str, Any]:
    """Return cost data only to users granted ``view_costs`` by the administrator."""

    order = _authorized_order(order_name, Capability.VIEW_COSTS)
    return _cost_snapshot(order)


@frappe.whitelist()
def update_order_cost_settings(
    order_name: str,
    board_rate_usd: float,
    cutting_cost_per_board_usd: float,
) -> dict[str, Any]:
    """Update editable costing inputs without granting full document write access."""

    order = _authorized_order(order_name, Capability.EDIT_COST_SETTINGS)
    if order.status not in EDITABLE_ORDER_STATUSES:
        frappe.throw(_("Cost settings can only be changed while the order is editable."))

    order.board_rate_usd = _finite_non_negative(board_rate_usd, _("Board Rate USD"))
    order.cutting_cost_per_board_usd = _finite_non_negative(
        cutting_cost_per_board_usd,
        _("Cutting Cost / Board USD"),
    )
    order.flags.force_cutting_plan_recalculation = True
    order.save(ignore_permissions=True)
    return _cost_snapshot(order)


@frappe.whitelist()
def approve_special_piece_price(
    order_name: str,
    piece_name: str,
    unit_price_usd: float,
    note: str | None = None,
) -> dict[str, Any]:
    """Approve or edit a special-door price through configurable capabilities."""

    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    piece = _special_piece(order, piece_name)
    required_capability = (
        Capability.EDIT_SPECIAL_PRICE
        if piece.special_shape_price_status == "Approved"
        else Capability.APPROVE_SPECIAL_PRICE
    )
    require_document_capability(order, required_capability)

    if order.status not in EDITABLE_ORDER_STATUSES:
        frappe.throw(_("Special pricing can only be changed while the order is editable."))
    if (piece.piece_type or "Regular") != "Special":
        frappe.throw(_("Only a special door can receive a custom inclusive price."))
    if piece.special_shape_status != "Documented":
        frappe.throw(_("Document the special door shape before approving its price."))

    price = _finite_non_negative(unit_price_usd, _("Special Unit Price USD"))
    approval_note = str(note or "").strip()
    if len(approval_note) > 500:
        frappe.throw(_("Pricing note cannot exceed 500 characters."))

    piece.special_shape_custom_unit_price_usd = price
    piece.special_shape_price_status = "Approved"
    piece.special_shape_price_note = approval_note
    piece.special_shape_price_approved_by = frappe.session.user
    piece.special_shape_price_approved_on = now_datetime()
    order.flags.special_price_approval_action = True
    order.save(ignore_permissions=True)

    return {
        "order_name": order.name,
        "piece_name": piece.name,
        "unit_price_usd": flt(piece.special_shape_final_unit_price_usd),
        "price_status": piece.special_shape_price_status,
        "approved_by": piece.special_shape_price_approved_by,
        "approved_on": piece.special_shape_price_approved_on,
        "required_capability": required_capability,
        "customer_quote_total_usd": flt(order.customer_quote_total_usd),
        "customer_quote_status": order.customer_quote_status,
    }


__all__ = [
    "approve_special_piece_price",
    "get_order_cost_snapshot",
    "update_order_cost_settings",
]
