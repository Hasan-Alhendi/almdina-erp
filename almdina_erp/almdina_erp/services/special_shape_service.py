from __future__ import annotations

import json
import math
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


SPECIAL_PRICE_APPROVER_ROLES = {"Accounts Management", "System Manager"}
EDITABLE_ORDER_STATUSES = {"Draft", "Pending Review", "Rejected"}
ALLOWED_DRAWING_TOOLS = {"pen", "line", "rectangle", "ellipse", "dimension", "note"}
MAX_DRAWING_BYTES = 300_000
MAX_DRAWING_ELEMENTS = 400
MAX_DRAWING_POINTS = 12_000
MAX_NOTE_LENGTH = 500


def _finite_number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} must be a valid number.").format(label))
    if not math.isfinite(result):
        frappe.throw(_("{0} must be finite.").format(label))
    return result


def _validate_coordinate(value: Any, label: str) -> None:
    number = _finite_number(value, label)
    if number < -20_000 or number > 20_000:
        frappe.throw(_("{0} is outside the allowed drawing area.").format(label))


def _validate_element(element: Any, index: int) -> int:
    if not isinstance(element, dict):
        frappe.throw(_("Drawing element {0} must be an object.").format(index))

    element_type = str(element.get("type") or "")
    if element_type not in ALLOWED_DRAWING_TOOLS:
        frappe.throw(_("Drawing element {0} uses an unsupported tool.").format(index))

    element_id = str(element.get("id") or "")
    if not element_id or len(element_id) > 80:
        frappe.throw(_("Drawing element {0} has an invalid identifier.").format(index))

    color = str(element.get("color") or "#172033")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        frappe.throw(_("Drawing element {0} has an invalid color.").format(index))

    if element_type == "pen":
        points = element.get("points")
        if not isinstance(points, list) or len(points) < 2:
            frappe.throw(_("Freehand drawing element {0} needs at least two points.").format(index))
        for point_index, point in enumerate(points, start=1):
            if not isinstance(point, list) or len(point) != 2:
                frappe.throw(
                    _("Point {0} in drawing element {1} is invalid.").format(point_index, index)
                )
            _validate_coordinate(point[0], _("Drawing X"))
            _validate_coordinate(point[1], _("Drawing Y"))
        return len(points)

    coordinate_names = {
        "line": ("x1", "y1", "x2", "y2"),
        "rectangle": ("x", "y", "width", "height"),
        "ellipse": ("cx", "cy", "rx", "ry"),
        "dimension": ("x1", "y1", "x2", "y2"),
        "note": ("x", "y"),
    }[element_type]
    for coordinate_name in coordinate_names:
        _validate_coordinate(
            element.get(coordinate_name),
            _("Drawing {0}").format(coordinate_name),
        )

    if element_type in {"rectangle", "ellipse"}:
        size_names = ("width", "height") if element_type == "rectangle" else ("rx", "ry")
        for size_name in size_names:
            if flt(element.get(size_name)) < 0:
                frappe.throw(_("Drawing sizes cannot be negative."))

    if element_type in {"dimension", "note"}:
        text = str(element.get("text") or "").strip()
        if not text:
            frappe.throw(_("Drawing notes and dimensions cannot be empty."))
        if len(text) > MAX_NOTE_LENGTH:
            frappe.throw(
                _("Drawing note is too long. The maximum is {0} characters.").format(
                    MAX_NOTE_LENGTH
                )
            )

    return 0


def validate_special_shape_drawing(raw_drawing: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the operator sketch as documentation data, never as CNC geometry."""

    if raw_drawing in (None, ""):
        return None

    if isinstance(raw_drawing, str):
        if len(raw_drawing.encode("utf-8")) > MAX_DRAWING_BYTES:
            frappe.throw(
                _("Special shape documentation is too large. Keep the sketch simple and try again.")
            )
        try:
            drawing = json.loads(raw_drawing)
        except (TypeError, ValueError):
            frappe.throw(_("Special shape documentation contains invalid JSON."))
    elif isinstance(raw_drawing, dict):
        drawing = raw_drawing
    else:
        frappe.throw(_("Special shape documentation must be a JSON object."))

    if not isinstance(drawing, dict):
        frappe.throw(_("Special shape documentation must be a JSON object."))
    try:
        version = int(drawing.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version != 1:
        frappe.throw(_("Unsupported special shape documentation version."))

    elements = drawing.get("elements")
    if not isinstance(elements, list):
        frappe.throw(_("Special shape documentation must contain an elements list."))
    if len(elements) > MAX_DRAWING_ELEMENTS:
        frappe.throw(
            _("Special shape documentation has too many elements. The maximum is {0}.").format(
                MAX_DRAWING_ELEMENTS
            )
        )

    point_count = 0
    for index, element in enumerate(elements, start=1):
        point_count += _validate_element(element, index)
    if point_count > MAX_DRAWING_POINTS:
        frappe.throw(
            _("Special shape documentation has too many freehand points. Simplify the sketch.")
        )

    canvas = drawing.get("canvas") or {}
    if not isinstance(canvas, dict):
        frappe.throw(_("Drawing canvas settings are invalid."))
    for fieldname in ("width", "height"):
        value = _finite_number(canvas.get(fieldname) or 0, _("Drawing canvas {0}").format(fieldname))
        if value <= 0 or value > 5_000:
            frappe.throw(_("Drawing canvas dimensions are invalid."))

    return drawing


def has_special_price_approval_role(user: str | None = None) -> bool:
    roles = set(frappe.get_roles(user or frappe.session.user))
    return bool(roles & SPECIAL_PRICE_APPROVER_ROLES)


def _get_special_piece(order: Any, piece_name: str) -> Any:
    for row in order.pieces or []:
        if row.name == piece_name:
            return row
    frappe.throw(_("The selected door row does not belong to order {0}.").format(order.name))


@frappe.whitelist()
def approve_special_piece_price(
    order_name: str,
    piece_name: str,
    unit_price_usd: float,
    note: str,
) -> dict[str, Any]:
    """Approve an inclusive customer unit price without granting accounting full order edit rights."""

    if not has_special_price_approval_role():
        frappe.throw(
            _("Only Accounts Management or System Manager can approve a special door price."),
            frappe.PermissionError,
        )

    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    if order.status not in EDITABLE_ORDER_STATUSES:
        frappe.throw(_("Special pricing can only be changed while the order is editable."))

    piece = _get_special_piece(order, piece_name)
    if (piece.piece_type or "Regular") != "Special":
        frappe.throw(_("Only a special door can receive a custom inclusive price."))
    if piece.special_shape_status != "Documented":
        frappe.throw(_("Document the special door drawing before approving its price."))

    price = _finite_number(unit_price_usd, _("Special Unit Price USD"))
    if price < 0:
        frappe.throw(_("Special Unit Price USD cannot be negative."))
    approval_note = str(note or "").strip()
    if not approval_note:
        frappe.throw(_("Write a short pricing note before approving the custom price."))
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
        "unit_price_usd": piece.special_shape_final_unit_price_usd,
        "price_status": piece.special_shape_price_status,
        "approved_by": piece.special_shape_price_approved_by,
        "approved_on": piece.special_shape_price_approved_on,
        "customer_quote_total_usd": order.customer_quote_total_usd,
        "customer_quote_status": order.customer_quote_status,
    }
