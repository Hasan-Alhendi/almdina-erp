from __future__ import annotations

import base64
import binascii
import json
import math
import re
from typing import Any

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_any_document_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import require_stage_operational_access
from almdina_erp.almdina_erp.services.order_edit_policy import assert_order_editable

_REFERENCE_VERSION = 1
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_METADATA_BYTES = 8 * 1024
_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=\r\n]+)$", re.IGNORECASE)
_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg"}
_SOURCES = frozenset({"upload", "scanner", "recrop"})


def _required(value: Any, label: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        frappe.throw(_("{0} is required.").format(label))
    return resolved


def _order(order_name: str) -> Any:
    order = frappe.get_doc("Door Cutting Order", _required(order_name, _("Door Cutting Order")))
    require_any_document_capability(
        order,
        (Capability.VIEW_DRAWING_WORKSPACE, Capability.EDIT_SPECIAL_DRAWING),
        message=_("لا تملك صلاحية فتح مساحة رسم الدرفة الخاصة لهذا الطلب."),
    )
    return order


def _piece(order: Any, piece_name: str) -> Any:
    name = _required(piece_name, _("Door Cutting Order Detail"))
    for row in order.pieces or []:
        if str(row.name) != name:
            continue
        if str(row.piece_type or "Regular") != "Special":
            frappe.throw(_("الصورة المرجعية متاحة للدرف الخاصة فقط."))
        return row
    frappe.throw(_("الدرفة المحددة لا تنتمي إلى هذا الطلب."), frappe.DoesNotExistError)


def _route_active(order: Any) -> bool:
    return bool(getattr(order, "current_production_stage", None) or getattr(order, "production_path", None))


def _assert_editable(order: Any) -> None:
    require_document_capability(
        order,
        Capability.EDIT_SPECIAL_DRAWING,
        message=_("لا تملك صلاحية تعديل توثيق الدرفة الخاصة."),
    )
    if _route_active(order):
        require_stage_operational_access(order)
    else:
        assert_order_editable(order)


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _payload(row: Any) -> dict[str, Any]:
    return {
        "file_url": getattr(row, "special_shape_reference_image", None) or "",
        "metadata_json": getattr(row, "special_shape_reference_image_meta_json", None) or "",
    }


def _decode_image(data_url: Any) -> tuple[bytes, str, str]:
    raw = _required(data_url, _("Reference Image"))
    match = _DATA_URL.fullmatch(raw)
    if not match:
        frappe.throw(_("صيغة الصورة غير مدعومة. استخدم PNG أو JPEG."))
    mime = match.group(1).lower()
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        frappe.throw(_("بيانات الصورة غير صالحة."))
    if not content:
        frappe.throw(_("الصورة فارغة."))
    if len(content) > _MAX_IMAGE_BYTES:
        frappe.throw(_("حجم الصورة بعد الاقتصاص يتجاوز 8 MB."))
    if mime == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        frappe.throw(_("بيانات PNG غير صالحة."))
    if mime == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
        frappe.throw(_("بيانات JPEG غير صالحة."))
    return content, mime, _EXTENSIONS[mime]


def _number(value: Any, label: str, *, minimum: float = 0, maximum: float = 100_000) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} في بيانات الصورة غير صالح.").format(label))
    if not math.isfinite(number) or number < minimum or number > maximum:
        frappe.throw(_("{0} في بيانات الصورة خارج النطاق المسموح.").format(label))
    return number


def _metadata(value: Any, mime: str) -> dict[str, Any]:
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_METADATA_BYTES:
            frappe.throw(_("بيانات وصف الصورة كبيرة جدًا."))
        try:
            raw = json.loads(value or "{}")
        except json.JSONDecodeError:
            frappe.throw(_("بيانات وصف الصورة غير صالحة."))
    elif isinstance(value, dict):
        raw = value
        if len(_serialize(raw).encode("utf-8")) > _MAX_METADATA_BYTES:
            frappe.throw(_("بيانات وصف الصورة كبيرة جدًا."))
    else:
        frappe.throw(_("بيانات وصف الصورة غير صالحة."))

    if int(raw.get("version") or 0) != _REFERENCE_VERSION:
        frappe.throw(_("إصدار بيانات الصورة غير مدعوم."))
    source = str(raw.get("source") or "").strip().lower()
    if source not in _SOURCES:
        frappe.throw(_("مصدر الصورة غير صالح."))

    source_width = _number(raw.get("source_width_px"), "source_width_px", minimum=1)
    source_height = _number(raw.get("source_height_px"), "source_height_px", minimum=1)
    rotation = int(_number(raw.get("rotation_deg") or 0, "rotation_deg", maximum=359))
    if rotation not in (0, 90, 180, 270):
        frappe.throw(_("زاوية تدوير الصورة غير مدعومة."))

    crop = raw.get("crop") or {}
    crop_x = _number(crop.get("x"), "crop.x")
    crop_y = _number(crop.get("y"), "crop.y")
    crop_width = _number(crop.get("width"), "crop.width", minimum=1)
    crop_height = _number(crop.get("height"), "crop.height", minimum=1)
    rotated_width = source_height if rotation in (90, 270) else source_width
    rotated_height = source_width if rotation in (90, 270) else source_height
    if crop_x + crop_width > rotated_width + 2 or crop_y + crop_height > rotated_height + 2:
        frappe.throw(_("منطقة الاقتصاص تتجاوز حدود الصورة."))

    output = raw.get("output") or {}
    output_width = int(_number(output.get("width_px"), "output.width_px", minimum=1, maximum=3200))
    output_height = int(_number(output.get("height_px"), "output.height_px", minimum=1, maximum=3200))
    output_mime = str(output.get("mime") or "").strip().lower()
    if output_mime != mime:
        frappe.throw(_("نوع الصورة لا يطابق بيانات وصفها."))

    normalized: dict[str, Any] = {
        "version": _REFERENCE_VERSION,
        "source": source,
        "original_name": str(raw.get("original_name") or "image")[:180],
        "original_mime": str(raw.get("original_mime") or "")[:80],
        "source_width_px": int(round(source_width)),
        "source_height_px": int(round(source_height)),
        "rotation_deg": rotation,
        "crop": {
            "x": round(crop_x, 3),
            "y": round(crop_y, 3),
            "width": round(crop_width, 3),
            "height": round(crop_height, 3),
        },
        "output": {"width_px": output_width, "height_px": output_height, "mime": output_mime},
    }
    scanner = raw.get("scanner")
    if source == "scanner" and isinstance(scanner, dict):
        normalized["scanner"] = {
            "provider": str(scanner.get("provider") or "local-wia-bridge")[:80],
            "device": str(scanner.get("device") or "")[:180],
            "dpi": int(_number(scanner.get("dpi") or 0, "scanner.dpi", maximum=2400)),
        }
    return normalized


def _cleanup_previous(file_url: str, order_name: str, exclude_name: str = "") -> None:
    if not file_url:
        return
    names = frappe.get_all(
        "File",
        filters={"file_url": file_url, "attached_to_doctype": "Door Cutting Order", "attached_to_name": order_name},
        pluck="name",
    )
    for name in names:
        if name == exclude_name:
            continue
        try:
            frappe.delete_doc("File", name)
        except Exception:
            frappe.log_error(title="Reference image cleanup failed", message=frappe.get_traceback())


@frappe.whitelist()
def get_reference_image(order_name: str, piece_name: str) -> dict[str, Any]:
    order = _order(order_name)
    piece = _piece(order, piece_name)
    return {"order_name": order.name, "piece_name": piece.name, "reference": _payload(piece)}


@frappe.whitelist()
def save_reference_image(order_name: str, piece_name: str, image_data_url: str, metadata_json: str | dict[str, Any]) -> dict[str, Any]:
    order = _order(order_name)
    _assert_editable(order)
    piece = _piece(order, piece_name)
    content, mime, extension = _decode_image(image_data_url)
    metadata = _metadata(metadata_json, mime)
    previous_url = getattr(piece, "special_shape_reference_image", None) or ""

    file_doc = save_file(
        f"special-door-reference-{order.name}-{piece.name}{extension}",
        content,
        "Door Cutting Order",
        order.name,
        is_private=1,
    )
    try:
        frappe.db.set_value(
            "Door Cutting Order Detail",
            piece.name,
            {
                "special_shape_reference_image": file_doc.file_url,
                "special_shape_reference_image_meta_json": _serialize(metadata),
            },
            update_modified=True,
        )
    except Exception:
        try:
            frappe.delete_doc("File", file_doc.name)
        except Exception:
            frappe.log_error(title="Reference image rollback failed", message=frappe.get_traceback())
        raise

    if previous_url and previous_url != file_doc.file_url:
        _cleanup_previous(previous_url, order.name, exclude_name=file_doc.name)
    saved = frappe.get_doc("Door Cutting Order Detail", piece.name)
    return {"order_name": order.name, "piece_name": piece.name, "reference": _payload(saved)}


@frappe.whitelist()
def remove_reference_image(order_name: str, piece_name: str) -> dict[str, Any]:
    order = _order(order_name)
    _assert_editable(order)
    piece = _piece(order, piece_name)
    previous_url = getattr(piece, "special_shape_reference_image", None) or ""
    frappe.db.set_value(
        "Door Cutting Order Detail",
        piece.name,
        {"special_shape_reference_image": "", "special_shape_reference_image_meta_json": ""},
        update_modified=True,
    )
    if previous_url:
        _cleanup_previous(previous_url, order.name)
    return {"order_name": order.name, "piece_name": piece.name, "reference": {"file_url": "", "metadata_json": ""}}


__all__ = ["get_reference_image", "save_reference_image", "remove_reference_image"]
