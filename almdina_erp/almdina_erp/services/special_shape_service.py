from __future__ import annotations

import json
import math
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_any_capability,
)

SPECIAL_PRICE_APPROVAL_CAPABILITIES = frozenset(
    {Capability.APPROVE_SPECIAL_PRICE, Capability.EDIT_SPECIAL_PRICE}
)
EDITABLE_ORDER_STATUSES = {"Draft", "Pending Review", "Rejected"}
ALLOWED_DRAWING_TOOLS = {"pen", "line", "rectangle", "ellipse", "dimension", "note"}
MAX_DRAWING_BYTES = 300_000
MAX_DRAWING_ELEMENTS = 400
MAX_DRAWING_POINTS = 12_000
MAX_NOTE_LENGTH = 500
MAX_GEOMETRY_BYTES = 50_000
MAX_GEOMETRY_VERTICES = 64
GEOMETRY_EPSILON = 0.001


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


def _same_geometry_point(first: list[float], second: list[float]) -> bool:
    return (
        abs(first[0] - second[0]) <= GEOMETRY_EPSILON
        and abs(first[1] - second[1]) <= GEOMETRY_EPSILON
    )


def _geometry_orientation(
    first: list[float],
    second: list[float],
    third: list[float],
) -> int:
    value = (
        (second[1] - first[1]) * (third[0] - second[0])
        - (second[0] - first[0]) * (third[1] - second[1])
    )
    if abs(value) <= GEOMETRY_EPSILON:
        return 0
    return 1 if value > 0 else 2


def _geometry_point_on_segment(
    first: list[float],
    point: list[float],
    second: list[float],
) -> bool:
    return (
        min(first[0], second[0]) - GEOMETRY_EPSILON
        <= point[0]
        <= max(first[0], second[0]) + GEOMETRY_EPSILON
        and min(first[1], second[1]) - GEOMETRY_EPSILON
        <= point[1]
        <= max(first[1], second[1]) + GEOMETRY_EPSILON
    )


def _geometry_segments_intersect(
    first_start: list[float],
    first_end: list[float],
    second_start: list[float],
    second_end: list[float],
) -> bool:
    first_orientation = _geometry_orientation(first_start, first_end, second_start)
    second_orientation = _geometry_orientation(first_start, first_end, second_end)
    third_orientation = _geometry_orientation(second_start, second_end, first_start)
    fourth_orientation = _geometry_orientation(second_start, second_end, first_end)
    if (
        first_orientation != second_orientation
        and third_orientation != fourth_orientation
    ):
        return True
    if first_orientation == 0 and _geometry_point_on_segment(
        first_start, second_start, first_end
    ):
        return True
    if second_orientation == 0 and _geometry_point_on_segment(
        first_start, second_end, first_end
    ):
        return True
    if third_orientation == 0 and _geometry_point_on_segment(
        second_start, first_start, second_end
    ):
        return True
    return fourth_orientation == 0 and _geometry_point_on_segment(
        second_start, first_end, second_end
    )


def _geometry_has_self_intersection(points: list[list[float]]) -> bool:
    count = len(points)
    if count < 4:
        return False
    for first_index in range(count):
        first_next = (first_index + 1) % count
        for second_index in range(first_index + 1, count):
            second_next = (second_index + 1) % count
            if (
                first_index == second_index
                or first_next == second_index
                or second_next == first_index
                or (first_index == 0 and second_next == 0)
            ):
                continue
            if _geometry_segments_intersect(
                points[first_index],
                points[first_next],
                points[second_index],
                points[second_next],
            ):
                return True
    return False


def _geometry_area(points: list[list[float]]) -> float:
    return abs(
        sum(
            point[0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * point[1]
            for index, point in enumerate(points)
        )
    ) / 2


def validate_special_shape_geometry(
    raw_geometry: str | dict[str, Any] | None,
    expected_width_cm: float | None = None,
    expected_length_cm: float | None = None,
) -> dict[str, Any] | None:
    """Validate exact centimetre polygon geometry used by cutting-plan and DXF renderers."""

    if raw_geometry in (None, ""):
        return None

    if isinstance(raw_geometry, str):
        if len(raw_geometry.encode("utf-8")) > MAX_GEOMETRY_BYTES:
            frappe.throw(_("Special shape geometry is too large."))
        try:
            geometry = json.loads(raw_geometry)
        except (TypeError, ValueError):
            frappe.throw(_("Special shape geometry contains invalid JSON."))
    elif isinstance(raw_geometry, dict):
        geometry = raw_geometry
    else:
        frappe.throw(_("Special shape geometry must be a JSON object."))

    if not isinstance(geometry, dict):
        frappe.throw(_("Special shape geometry must be a JSON object."))
    try:
        version = int(geometry.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version != 1:
        frappe.throw(_("Unsupported special shape geometry version."))
    if geometry.get("kind") != "polygon" or geometry.get("units") != "cm":
        frappe.throw(_("Special shape geometry must be a centimetre polygon."))

    width = _finite_number(geometry.get("blank_width_cm"), _("Special Shape Width CM"))
    length = _finite_number(geometry.get("blank_length_cm"), _("Special Shape Length CM"))
    if width <= 0 or length <= 0:
        frappe.throw(_("Special shape width and length must be greater than zero."))
    if expected_width_cm and not math.isclose(
        width,
        flt(expected_width_cm),
        rel_tol=0,
        abs_tol=GEOMETRY_EPSILON,
    ):
        frappe.throw(_("Special shape geometry width does not match the piece width."))
    if expected_length_cm and not math.isclose(
        length,
        flt(expected_length_cm),
        rel_tol=0,
        abs_tol=GEOMETRY_EPSILON,
    ):
        frappe.throw(_("Special shape geometry length does not match the piece length."))

    raw_points = geometry.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 3:
        frappe.throw(_("Special shape geometry needs at least three vertices."))
    if len(raw_points) > MAX_GEOMETRY_VERTICES:
        frappe.throw(
            _("Special shape geometry cannot exceed {0} vertices.").format(
                MAX_GEOMETRY_VERTICES
            )
        )

    points: list[list[float]] = []
    for index, point in enumerate(raw_points, start=1):
        if not isinstance(point, list) or len(point) != 2:
            frappe.throw(_("Special shape vertex {0} is invalid.").format(index))
        x = _finite_number(point[0], _("Special Shape Vertex X"))
        y = _finite_number(point[1], _("Special Shape Vertex Y"))
        if (
            x < -GEOMETRY_EPSILON
            or y < -GEOMETRY_EPSILON
            or x > width + GEOMETRY_EPSILON
            or y > length + GEOMETRY_EPSILON
        ):
            frappe.throw(_("Special shape vertex {0} is outside the raw piece.").format(index))
        points.append([round(x, 3), round(y, 3)])

    if len(points) > 1 and _same_geometry_point(points[0], points[-1]):
        points.pop()
    if len(points) < 3:
        frappe.throw(_("Special shape geometry needs at least three distinct vertices."))
    for index, point in enumerate(points):
        if _same_geometry_point(point, points[(index + 1) % len(points)]):
            frappe.throw(_("Special shape geometry has duplicate adjacent vertices."))

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if (
        abs(min(xs)) > GEOMETRY_EPSILON
        or abs(max(xs) - width) > GEOMETRY_EPSILON
        or abs(min(ys)) > GEOMETRY_EPSILON
        or abs(max(ys) - length) > GEOMETRY_EPSILON
    ):
        frappe.throw(_("Special shape geometry must touch all four raw-piece bounds."))
    if _geometry_area(points) <= GEOMETRY_EPSILON:
        frappe.throw(_("Special shape geometry area must be greater than zero."))
    if _geometry_has_self_intersection(points):
        frappe.throw(_("Special shape geometry edges cannot intersect."))

    template = str(geometry.get("template") or "custom").strip()
    if len(template) > 80:
        frappe.throw(_("Special shape template name is too long."))
    return {
        "version": 1,
        "kind": "polygon",
        "units": "cm",
        "template": template or "custom",
        "blank_width_cm": round(width, 3),
        "blank_length_cm": round(length, 3),
        "points": points,
        "exact": True,
    }


def has_special_price_approval_permission(user: str | None = None) -> bool:
    """Resolve special-price access exclusively from configured capabilities."""

    return doctype_has_any_capability(
        SPECIAL_PRICE_APPROVAL_CAPABILITIES,
        user=user,
    )


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
    note: str | None = None,
) -> dict[str, Any]:
    """Approve an inclusive customer unit price without granting accounting full order edit rights."""

    if not has_special_price_approval_permission():
        frappe.throw(
            _("You do not have permission to approve or edit a special door price."),
            frappe.PermissionError,
        )

    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    if order.status not in EDITABLE_ORDER_STATUSES:
        frappe.throw(_("Special pricing can only be changed while the order is editable."))

    piece = _get_special_piece(order, piece_name)
    if (piece.piece_type or "Regular") != "Special":
        frappe.throw(_("Only a special door can receive a custom inclusive price."))

    price = _finite_number(unit_price_usd, _("Special Unit Price USD"))
    if price < 0:
        frappe.throw(_("Special Unit Price USD cannot be negative."))
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
        "unit_price_usd": piece.special_shape_final_unit_price_usd,
        "price_status": piece.special_shape_price_status,
        "approved_by": piece.special_shape_price_approved_by,
        "approved_on": piece.special_shape_price_approved_on,
        "customer_quote_total_usd": order.customer_quote_total_usd,
        "customer_quote_status": order.customer_quote_status,
    }
