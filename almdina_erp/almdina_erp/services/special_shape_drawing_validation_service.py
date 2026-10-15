from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.special_shape_service import (
    MAX_DRAWING_BYTES,
    MAX_DRAWING_ELEMENTS,
)

DOCUMENTATION_SCHEMA = "almdina.special-shape-documentation"
DOCUMENTATION_VERSION = 1
DOCUMENTATION_ELEMENT_TYPES = {
    "stroke", "line", "rect", "ellipse", "arrow", "dimension", "text",
}
DOCUMENTATION_SOURCES = {"image", "template", "pen", "mixed"}
DOCUMENTATION_TEMPLATES = {
    "clipped-corner", "top-arch", "side-arch", "trapezoid", "inner-opening", "slanted-edge",
}
MAX_COORDINATE_MM = 20_000
MAX_NOTES_LENGTH = 2_000
MAX_TEXT_LENGTH = 300
MAX_STROKE_POINTS = 500
MAX_REFERENCE_URL_LENGTH = 500
MAX_REFERENCE_IMAGE_PIXELS_PER_SIDE = 100_000
MIN_REFERENCE_CROP_SIZE = 0.02


def _parse(raw_documentation: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_documentation, str):
        if len(raw_documentation.encode("utf-8")) > MAX_DRAWING_BYTES:
            frappe.throw(_("The door documentation is too large. Simplify the drawing and try again."))
        try:
            documentation = json.loads(raw_documentation)
        except (TypeError, ValueError):
            frappe.throw(_("The door documentation contains invalid JSON."))
    elif isinstance(raw_documentation, dict):
        try:
            encoded = json.dumps(raw_documentation, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            frappe.throw(_("The door documentation contains values that cannot be saved."))
        if len(encoded) > MAX_DRAWING_BYTES:
            frappe.throw(_("The door documentation is too large. Simplify the drawing and try again."))
        documentation = raw_documentation
    else:
        frappe.throw(_("The door documentation must be a JSON object."))
    if not isinstance(documentation, dict):
        frappe.throw(_("The door documentation must be a JSON object."))
    return documentation


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} must be a valid number.").format(label))
    if not math.isfinite(number) or abs(number) > MAX_COORDINATE_MM:
        frappe.throw(_("{0} is outside the documentation area.").format(label))
    if positive and number <= 0:
        frappe.throw(_("{0} must be greater than zero.").format(label))
    return number


def _point(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        frappe.throw(_("{0} must be a valid point.").format(label))
    _finite(value.get("xMm"), _("X coordinate"))
    _finite(value.get("yMm"), _("Y coordinate"))


def _validate_reference(reference: Any) -> None:
    if reference in (None, {}):
        return
    if not isinstance(reference, dict):
        frappe.throw(_("The reference image data is invalid."))
    file_url = str(reference.get("fileUrl") or "").strip()
    if not file_url.startswith("/private/files/") or len(file_url) > MAX_REFERENCE_URL_LENGTH:
        frappe.throw(_("The reference image link is invalid."))
    rotation = _finite(reference.get("rotationDeg", 0), _("Image rotation"))
    if rotation < -360 or rotation > 360:
        frappe.throw(_("The image rotation angle is invalid."))
    try:
        opacity = float(reference.get("opacity", 1))
    except (TypeError, ValueError):
        frappe.throw(_("The image opacity is invalid."))
    if not math.isfinite(opacity) or opacity < 0.1 or opacity > 1:
        frappe.throw(_("Image opacity must be between 10% and 100%."))
    if not isinstance(reference.get("locked", True), bool):
        frappe.throw(_("The image lock state is invalid."))
    crop = reference.get("crop")
    if crop is None:
        return
    if not isinstance(crop, dict):
        frappe.throw(_("The image crop data is invalid."))
    try:
        x = float(crop.get("x"))
        y = float(crop.get("y"))
        width = float(crop.get("width"))
        height = float(crop.get("height"))
    except (TypeError, ValueError):
        frappe.throw(_("The image crop data is invalid."))
    values = (x, y, width, height)
    if (
        not all(math.isfinite(value) for value in values)
        or x < 0
        or y < 0
        or width < MIN_REFERENCE_CROP_SIZE
        or height < MIN_REFERENCE_CROP_SIZE
        or x + width > 1.000001
        or y + height > 1.000001
    ):
        frappe.throw(_("The image crop bounds are outside the original image."))
    image_size = reference.get("imageSize")
    is_full_crop = x <= 0.000001 and y <= 0.000001 and width >= 0.999999 and height >= 0.999999
    if image_size is None and is_full_crop:
        return
    if not isinstance(image_size, dict):
        frappe.throw(_("The original image dimensions are required to save the crop."))
    try:
        width_px = float(image_size.get("widthPx"))
        height_px = float(image_size.get("heightPx"))
    except (TypeError, ValueError):
        frappe.throw(_("The original image dimensions are invalid."))
    if (
        not math.isfinite(width_px)
        or not math.isfinite(height_px)
        or width_px <= 0
        or height_px <= 0
        or width_px > MAX_REFERENCE_IMAGE_PIXELS_PER_SIDE
        or height_px > MAX_REFERENCE_IMAGE_PIXELS_PER_SIDE
        or not width_px.is_integer()
        or not height_px.is_integer()
    ):
        frappe.throw(_("The original image dimensions are invalid."))


def _validate_element(element: Any, index: int, identifiers: set[str]) -> None:
    if not isinstance(element, dict):
        frappe.throw(_("Documentation element {0} is invalid.").format(index))
    element_id = str(element.get("id") or "").strip()
    if not element_id or len(element_id) > 80 or element_id in identifiers:
        frappe.throw(_("Documentation element {0} has an invalid or duplicate identifier.").format(index))
    identifiers.add(element_id)
    element_type = str(element.get("type") or "")
    if element_type not in DOCUMENTATION_ELEMENT_TYPES:
        frappe.throw(_("Documentation element {0} has an unsupported type.").format(index))

    if element_type == "stroke":
        points = element.get("points")
        if not isinstance(points, list) or len(points) < 2 or len(points) > MAX_STROKE_POINTS:
            frappe.throw(_("Pen stroke {0} has an invalid number of points.").format(index))
        for point_index, value in enumerate(points, start=1):
            _point(value, _("Pen point {0}").format(point_index))
        return
    if element_type in {"line", "arrow", "dimension"}:
        _point(element.get("start"), _("Element start"))
        _point(element.get("end"), _("Element end"))
        if element_type == "dimension":
            _finite(element.get("valueMm"), _("Dimension value"), positive=True)
            if str(element.get("unit") or "mm") not in {"mm", "cm"}:
                frappe.throw(_("The measurement unit is not supported."))
        return
    if element_type in {"rect", "ellipse"}:
        _finite(element.get("xMm"), _("X position"))
        _finite(element.get("yMm"), _("Y position"))
        _finite(element.get("widthMm"), _("Width"), positive=True)
        _finite(element.get("heightMm"), _("Length"), positive=True)
        return
    if element_type == "text":
        _point(element.get("position"), _("Note position"))
        text = str(element.get("text") or "").strip()
        if not text or len(text) > MAX_TEXT_LENGTH:
            frappe.throw(_("Note text must not exceed {0} characters.").format(MAX_TEXT_LENGTH))


def validate_special_shape_drawing(
    raw_documentation: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate explanatory documentation; it is never manufacturing geometry."""

    if raw_documentation in (None, ""):
        return None
    documentation = _parse(raw_documentation)
    if documentation.get("schema") != DOCUMENTATION_SCHEMA:
        frappe.throw(_("The door documentation contract is not supported."))
    try:
        version = int(documentation.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version != DOCUMENTATION_VERSION:
        frappe.throw(_("The door documentation version is not supported."))
    canvas = documentation.get("canvas")
    if not isinstance(canvas, dict):
        frappe.throw(_("The documentation canvas size is invalid."))
    _finite(canvas.get("widthMm"), _("Door width"), positive=True)
    _finite(canvas.get("heightMm"), _("Door length"), positive=True)
    _validate_reference(documentation.get("reference"))

    elements = documentation.get("elements")
    if not isinstance(elements, list) or len(elements) > MAX_DRAWING_ELEMENTS:
        frappe.throw(_("The door documentation has too many elements or is invalid."))
    identifiers: set[str] = set()
    for index, element in enumerate(elements, start=1):
        _validate_element(element, index, identifiers)

    notes = str(documentation.get("notes") or "")
    if len(notes) > MAX_NOTES_LENGTH:
        frappe.throw(_("Designer notes must not exceed {0} characters.").format(MAX_NOTES_LENGTH))
    if str(documentation.get("source") or "mixed") not in DOCUMENTATION_SOURCES:
        frappe.throw(_("The door documentation source is not supported."))
    template_id = documentation.get("templateId")
    if template_id not in (None, "") and str(template_id) not in DOCUMENTATION_TEMPLATES:
        frappe.throw(_("The selected ready-made shape is not supported."))
    if not documentation.get("reference") and not elements:
        frappe.throw(_("Add a reference image or at least one explanatory element before saving."))
    return documentation


__all__ = [
    "DOCUMENTATION_ELEMENT_TYPES",
    "DOCUMENTATION_SCHEMA",
    "DOCUMENTATION_TEMPLATES",
    "DOCUMENTATION_VERSION",
    "validate_special_shape_drawing",
]
