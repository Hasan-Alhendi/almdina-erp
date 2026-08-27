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
            frappe.throw(_("توثيق الدرفة كبير جدًا. بسّط الرسم ثم حاول مرة أخرى."))
        try:
            documentation = json.loads(raw_documentation)
        except (TypeError, ValueError):
            frappe.throw(_("توثيق الدرفة يحتوي JSON غير صالح."))
    elif isinstance(raw_documentation, dict):
        try:
            encoded = json.dumps(raw_documentation, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            frappe.throw(_("توثيق الدرفة يحتوي قيمًا غير قابلة للحفظ."))
        if len(encoded) > MAX_DRAWING_BYTES:
            frappe.throw(_("توثيق الدرفة كبير جدًا. بسّط الرسم ثم حاول مرة أخرى."))
        documentation = raw_documentation
    else:
        frappe.throw(_("توثيق الدرفة يجب أن يكون كائن JSON."))
    if not isinstance(documentation, dict):
        frappe.throw(_("توثيق الدرفة يجب أن يكون كائن JSON."))
    return documentation


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} يجب أن يكون رقمًا صالحًا.").format(label))
    if not math.isfinite(number) or abs(number) > MAX_COORDINATE_MM:
        frappe.throw(_("{0} خارج نطاق مساحة التوثيق.").format(label))
    if positive and number <= 0:
        frappe.throw(_("{0} يجب أن يكون أكبر من صفر.").format(label))
    return number


def _point(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        frappe.throw(_("{0} يجب أن يكون نقطة صالحة.").format(label))
    _finite(value.get("xMm"), _("إحداثي X"))
    _finite(value.get("yMm"), _("إحداثي Y"))


def _validate_reference(reference: Any) -> None:
    if reference in (None, {}):
        return
    if not isinstance(reference, dict):
        frappe.throw(_("بيانات الصورة المرجعية غير صالحة."))
    file_url = str(reference.get("fileUrl") or "").strip()
    if not file_url.startswith("/private/files/") or len(file_url) > MAX_REFERENCE_URL_LENGTH:
        frappe.throw(_("رابط الصورة المرجعية غير صالح."))
    rotation = _finite(reference.get("rotationDeg", 0), _("تدوير الصورة"))
    if rotation < -360 or rotation > 360:
        frappe.throw(_("زاوية تدوير الصورة غير صالحة."))
    try:
        opacity = float(reference.get("opacity", 1))
    except (TypeError, ValueError):
        frappe.throw(_("شفافية الصورة غير صالحة."))
    if not math.isfinite(opacity) or opacity < 0.1 or opacity > 1:
        frappe.throw(_("شفافية الصورة يجب أن تكون بين 10% و100%."))
    if not isinstance(reference.get("locked", True), bool):
        frappe.throw(_("حالة قفل الصورة غير صالحة."))
    crop = reference.get("crop")
    if crop is None:
        return
    if not isinstance(crop, dict):
        frappe.throw(_("بيانات اقتصاص الصورة غير صالحة."))
    try:
        x = float(crop.get("x"))
        y = float(crop.get("y"))
        width = float(crop.get("width"))
        height = float(crop.get("height"))
    except (TypeError, ValueError):
        frappe.throw(_("بيانات اقتصاص الصورة غير صالحة."))
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
        frappe.throw(_("حدود اقتصاص الصورة خارج نطاق الصورة الأصلية."))
    image_size = reference.get("imageSize")
    is_full_crop = x <= 0.000001 and y <= 0.000001 and width >= 0.999999 and height >= 0.999999
    if image_size is None and is_full_crop:
        return
    if not isinstance(image_size, dict):
        frappe.throw(_("أبعاد الصورة الأصلية مطلوبة لحفظ الاقتصاص."))
    try:
        width_px = float(image_size.get("widthPx"))
        height_px = float(image_size.get("heightPx"))
    except (TypeError, ValueError):
        frappe.throw(_("أبعاد الصورة الأصلية غير صالحة."))
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
        frappe.throw(_("أبعاد الصورة الأصلية غير صالحة."))


def _validate_element(element: Any, index: int, identifiers: set[str]) -> None:
    if not isinstance(element, dict):
        frappe.throw(_("عنصر التوثيق رقم {0} غير صالح.").format(index))
    element_id = str(element.get("id") or "").strip()
    if not element_id or len(element_id) > 80 or element_id in identifiers:
        frappe.throw(_("معرّف عنصر التوثيق رقم {0} غير صالح أو مكرر.").format(index))
    identifiers.add(element_id)
    element_type = str(element.get("type") or "")
    if element_type not in DOCUMENTATION_ELEMENT_TYPES:
        frappe.throw(_("نوع عنصر التوثيق رقم {0} غير مدعوم.").format(index))

    if element_type == "stroke":
        points = element.get("points")
        if not isinstance(points, list) or len(points) < 2 or len(points) > MAX_STROKE_POINTS:
            frappe.throw(_("ضربة القلم رقم {0} تحتوي عدد نقاط غير صالح.").format(index))
        for point_index, value in enumerate(points, start=1):
            _point(value, _("نقطة القلم {0}").format(point_index))
        return
    if element_type in {"line", "arrow", "dimension"}:
        _point(element.get("start"), _("بداية العنصر"))
        _point(element.get("end"), _("نهاية العنصر"))
        if element_type == "dimension":
            _finite(element.get("valueMm"), _("قيمة القياس"), positive=True)
            if str(element.get("unit") or "mm") not in {"mm", "cm"}:
                frappe.throw(_("وحدة القياس غير مدعومة."))
        return
    if element_type in {"rect", "ellipse"}:
        _finite(element.get("xMm"), _("موضع X"))
        _finite(element.get("yMm"), _("موضع Y"))
        _finite(element.get("widthMm"), _("العرض"), positive=True)
        _finite(element.get("heightMm"), _("الطول"), positive=True)
        return
    if element_type == "text":
        _point(element.get("position"), _("موضع الملاحظة"))
        text = str(element.get("text") or "").strip()
        if not text or len(text) > MAX_TEXT_LENGTH:
            frappe.throw(_("نص الملاحظة يجب ألا يتجاوز {0} حرفًا.").format(MAX_TEXT_LENGTH))


def validate_special_shape_drawing(
    raw_documentation: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate explanatory documentation; it is never manufacturing geometry."""

    if raw_documentation in (None, ""):
        return None
    documentation = _parse(raw_documentation)
    if documentation.get("schema") != DOCUMENTATION_SCHEMA:
        frappe.throw(_("عقد توثيق الدرفة غير مدعوم."))
    try:
        version = int(documentation.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version != DOCUMENTATION_VERSION:
        frappe.throw(_("إصدار توثيق الدرفة غير مدعوم."))
    canvas = documentation.get("canvas")
    if not isinstance(canvas, dict):
        frappe.throw(_("مقاس لوحة التوثيق غير صالح."))
    _finite(canvas.get("widthMm"), _("عرض الدرفة"), positive=True)
    _finite(canvas.get("heightMm"), _("طول الدرفة"), positive=True)
    _validate_reference(documentation.get("reference"))

    elements = documentation.get("elements")
    if not isinstance(elements, list) or len(elements) > MAX_DRAWING_ELEMENTS:
        frappe.throw(_("عناصر توثيق الدرفة كثيرة جدًا أو غير صالحة."))
    identifiers: set[str] = set()
    for index, element in enumerate(elements, start=1):
        _validate_element(element, index, identifiers)

    notes = str(documentation.get("notes") or "")
    if len(notes) > MAX_NOTES_LENGTH:
        frappe.throw(_("ملاحظات المصمم يجب ألا تتجاوز {0} حرفًا.").format(MAX_NOTES_LENGTH))
    if str(documentation.get("source") or "mixed") not in DOCUMENTATION_SOURCES:
        frappe.throw(_("مصدر توثيق الدرفة غير مدعوم."))
    template_id = documentation.get("templateId")
    if template_id not in (None, "") and str(template_id) not in DOCUMENTATION_TEMPLATES:
        frappe.throw(_("الشكل الجاهز المحدد غير مدعوم."))
    if not documentation.get("reference") and not elements:
        frappe.throw(_("أضف صورة مرجعية أو عنصرًا توضيحيًا واحدًا على الأقل قبل الحفظ."))
    return documentation


__all__ = [
    "DOCUMENTATION_ELEMENT_TYPES",
    "DOCUMENTATION_SCHEMA",
    "DOCUMENTATION_TEMPLATES",
    "DOCUMENTATION_VERSION",
    "validate_special_shape_drawing",
]
