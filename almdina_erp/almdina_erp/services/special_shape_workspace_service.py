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
    document_has_capability,
    require_any_document_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import (
    current_stage_operational_access,
    require_stage_operational_access,
)
from almdina_erp.almdina_erp.services.order_edit_policy import (
    assert_order_editable,
    user_can_edit_order,
)
from almdina_erp.almdina_erp.services.special_shape_drawing_validation_service import (
    validate_special_shape_drawing,
)
from almdina_erp.almdina_erp.services.special_shape_service import (
    validate_special_shape_geometry,
)


_DRAWING_SCHEMA = "almdina.door-drawing"
_DRAWING_VERSION = 4
_DIMENSION_TOLERANCE_MM = 0.01
_REFERENCE_IMAGE_VERSION = 1
_REFERENCE_IMAGE_MAX_BYTES = 8 * 1024 * 1024
_REFERENCE_METADATA_MAX_BYTES = 8 * 1024
_REFERENCE_IMAGE_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)
_REFERENCE_IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
_REFERENCE_IMAGE_SOURCES = frozenset({"device", "scanner", "recrop"})


def _required_text(value: Any, label: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        frappe.throw(_("{0} is required.").format(label))
    return resolved


def _get_order(order_name: str) -> Any:
    name = _required_text(order_name, _("Door Cutting Order"))
    order = frappe.get_doc("Door Cutting Order", name)
    require_any_document_capability(
        order,
        (Capability.VIEW_DRAWING_WORKSPACE, Capability.EDIT_SPECIAL_DRAWING),
        message=_("لا تملك صلاحية فتح مساحة رسم الدرفة الخاصة لهذا الطلب."),
    )
    return order


def _get_piece(order: Any, piece_name: str) -> Any:
    name = _required_text(piece_name, _("Door Cutting Order Detail"))
    for row in order.pieces or []:
        if str(row.name) == name:
            if str(row.piece_type or "Regular") != "Special":
                frappe.throw(_("مساحة الرسم المستقلة متاحة للدرف الخاصة فقط."))
            return row
    frappe.throw(
        _("الدرفة المحددة لا تنتمي إلى الطلب {0}.").format(order.name),
        frappe.DoesNotExistError,
    )


def _route_is_active(order: Any) -> bool:
    return bool(
        getattr(order, "current_production_stage", None)
        or getattr(order, "production_path", None)
    )


def _edit_state(order: Any) -> dict[str, Any]:
    if not document_has_capability(order, Capability.EDIT_SPECIAL_DRAWING):
        return {
            "can_edit": False,
            "reason": _("ليس لديك صلاحية تعديل رسومات الدرف الخاصة."),
            "stage": None,
        }

    if _route_is_active(order):
        stage = current_stage_operational_access(order)
        return {
            "can_edit": bool(stage["actor_holds_operational_role"]),
            "reason": "" if stage["actor_holds_operational_role"] else str(stage.get("reason") or ""),
            "stage": stage,
        }

    can_edit = user_can_edit_order(
        getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
    )
    return {
        "can_edit": bool(can_edit),
        "reason": "" if can_edit else _("يمكن تعديل الرسم قبل الإنتاج عندما يكون الطلب في حالة المسودة."),
        "stage": None,
    }


def _documentation_mode(row: Any) -> str:
    mode = str(getattr(row, "special_shape_documentation_mode", None) or "").strip()
    if mode == "Image" and getattr(row, "special_shape_reference_image", None):
        return "Image"
    return "Drawing"


def _piece_payload(row: Any) -> dict[str, Any]:
    return {
        "name": row.name,
        "piece_no": row.piece_no or row.idx,
        "piece_type": row.piece_type or "Regular",
        "width_cm": row.width_cm,
        "length_cm": row.length_cm,
        "special_shape_drawing_json": row.special_shape_drawing_json or "",
        "special_shape_geometry_json": row.special_shape_geometry_json or "",
        "special_shape_documentation_mode": _documentation_mode(row),
        "special_shape_reference_image": getattr(row, "special_shape_reference_image", None) or "",
        "special_shape_reference_image_meta_json": getattr(row, "special_shape_reference_image_meta_json", None) or "",
        "special_shape_status": row.special_shape_status or "Needs Documentation",
        "special_shape_drawing_updated_by": row.special_shape_drawing_updated_by,
        "special_shape_drawing_updated_on": row.special_shape_drawing_updated_on,
    }


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validate_v4_piece_dimensions(drawing: dict[str, Any], piece: Any) -> None:
    if drawing.get("schema") != _DRAWING_SCHEMA or int(drawing.get("version") or 0) != _DRAWING_VERSION:
        frappe.throw(_("مساحة الرسم المستقلة تقبل مستند Drawing V4 فقط."))

    blank = drawing.get("blank") or {}
    width_mm = float(blank.get("widthMm") or 0)
    height_mm = float(blank.get("heightMm") or 0)
    expected_width_mm = float(piece.width_cm or 0) * 10
    expected_height_mm = float(piece.length_cm or 0) * 10
    if not math.isclose(width_mm, expected_width_mm, rel_tol=0, abs_tol=_DIMENSION_TOLERANCE_MM):
        frappe.throw(_("عرض الرسم لا يطابق عرض الدرفة الحالية."))
    if not math.isclose(height_mm, expected_height_mm, rel_tol=0, abs_tol=_DIMENSION_TOLERANCE_MM):
        frappe.throw(_("طول الرسم لا يطابق طول الدرفة الحالية."))


def _assert_editable(order: Any) -> None:
    require_document_capability(
        order,
        Capability.EDIT_SPECIAL_DRAWING,
        message=_("لا تملك صلاحية تعديل رسومات الدرف الخاصة."),
    )
    if _route_is_active(order):
        require_stage_operational_access(order)
        return
    assert_order_editable(order)


def _lock_order(order_name: str) -> str:
    name = _required_text(order_name, _("Door Cutting Order"))
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    return name


def _save_order(order: Any) -> None:
    if _route_is_active(order):
        order.flags.allow_approved_edit = True
    order.save(ignore_permissions=True)


def _decode_reference_image(image_data_url: Any) -> tuple[bytes, str, str]:
    raw = _required_text(image_data_url, _("Reference Image"))
    match = _REFERENCE_IMAGE_DATA_URL.fullmatch(raw)
    if not match:
        frappe.throw(_("صيغة صورة الدرفة غير مدعومة. استخدم PNG أو JPEG."))
    mime = match.group(1).lower()
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        frappe.throw(_("بيانات صورة الدرفة غير صالحة."))
    if not content:
        frappe.throw(_("صورة الدرفة فارغة."))
    if len(content) > _REFERENCE_IMAGE_MAX_BYTES:
        frappe.throw(_("حجم صورة الدرفة بعد القص يتجاوز 8 MB."))
    if mime == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        frappe.throw(_("بيانات PNG غير صالحة."))
    if mime == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
        frappe.throw(_("بيانات JPEG غير صالحة."))
    return content, mime, _REFERENCE_IMAGE_EXTENSIONS[mime]


def _finite_metadata_number(value: Any, label: str, *, minimum: float = 0, maximum: float = 100_000) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} في بيانات الصورة غير صالح.").format(label))
    if not math.isfinite(number) or number < minimum or number > maximum:
        frappe.throw(_("{0} في بيانات الصورة خارج النطاق المسموح.").format(label))
    return number


def _validate_reference_metadata(metadata_json: Any, image_mime: str) -> dict[str, Any]:
    if isinstance(metadata_json, str):
        if len(metadata_json.encode("utf-8")) > _REFERENCE_METADATA_MAX_BYTES:
            frappe.throw(_("بيانات وصف صورة الدرفة كبيرة جدًا."))
        try:
            raw = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            frappe.throw(_("بيانات وصف صورة الدرفة غير صالحة."))
    elif isinstance(metadata_json, dict):
        raw = metadata_json
        if len(_serialize(raw).encode("utf-8")) > _REFERENCE_METADATA_MAX_BYTES:
            frappe.throw(_("بيانات وصف صورة الدرفة كبيرة جدًا."))
    else:
        frappe.throw(_("بيانات وصف صورة الدرفة غير صالحة."))

    if int(raw.get("version") or 0) != _REFERENCE_IMAGE_VERSION:
        frappe.throw(_("إصدار بيانات صورة الدرفة غير مدعوم."))
    source = str(raw.get("source") or "").strip().lower()
    if source not in _REFERENCE_IMAGE_SOURCES:
        frappe.throw(_("مصدر صورة الدرفة غير صالح."))

    source_width = _finite_metadata_number(raw.get("source_width_px"), "source_width_px", minimum=1)
    source_height = _finite_metadata_number(raw.get("source_height_px"), "source_height_px", minimum=1)
    crop = raw.get("crop") or {}
    crop_x = _finite_metadata_number(crop.get("x"), "crop.x")
    crop_y = _finite_metadata_number(crop.get("y"), "crop.y")
    crop_width = _finite_metadata_number(crop.get("width"), "crop.width", minimum=1)
    crop_height = _finite_metadata_number(crop.get("height"), "crop.height", minimum=1)
    if crop_x + crop_width > source_width + 2 or crop_y + crop_height > source_height + 2:
        frappe.throw(_("منطقة قص الصورة تتجاوز حدود الصورة الأصلية."))

    output = raw.get("output") or {}
    output_width = int(_finite_metadata_number(output.get("width_px"), "output.width_px", minimum=1, maximum=4000))
    output_height = int(_finite_metadata_number(output.get("height_px"), "output.height_px", minimum=1, maximum=4000))
    output_mime = str(output.get("mime") or "").strip().lower()
    if output_mime != image_mime:
        frappe.throw(_("نوع الصورة المحفوظة لا يطابق بيانات وصف الصورة."))

    normalized: dict[str, Any] = {
        "version": _REFERENCE_IMAGE_VERSION,
        "source": source,
        "original_name": str(raw.get("original_name") or "image")[:180],
        "original_mime": str(raw.get("original_mime") or "")[:80],
        "source_width_px": int(round(source_width)),
        "source_height_px": int(round(source_height)),
        "crop": {
            "x": round(crop_x, 3),
            "y": round(crop_y, 3),
            "width": round(crop_width, 3),
            "height": round(crop_height, 3),
        },
        "output": {
            "width_px": output_width,
            "height_px": output_height,
            "mime": output_mime,
        },
    }
    scanner = raw.get("scanner")
    if source == "scanner" and isinstance(scanner, dict):
        normalized["scanner"] = {
            "provider": str(scanner.get("provider") or "local-wia-bridge")[:80],
            "device": str(scanner.get("device") or "")[:180],
            "dpi": int(_finite_metadata_number(scanner.get("dpi") or 0, "scanner.dpi", maximum=2400)),
        }
    return normalized


def _delete_reference_file(file_url: str, order_name: str, *, exclude_name: str = "") -> None:
    if not file_url:
        return
    names = frappe.get_all(
        "File",
        filters={
            "file_url": file_url,
            "attached_to_doctype": "Door Cutting Order",
            "attached_to_name": order_name,
        },
        pluck="name",
    )
    for name in names:
        if name == exclude_name:
            continue
        try:
            frappe.delete_doc("File", name, ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title="Special door reference image cleanup failed",
                message=frappe.get_traceback(),
            )


@frappe.whitelist()
def get_drawing_workspace(order_name: str, piece_name: str) -> dict[str, Any]:
    """Return one isolated special-door drawing session context."""

    order = _get_order(order_name)
    piece = _get_piece(order, piece_name)
    edit = _edit_state(order)
    return {
        "order": {
            "name": order.name,
            "customer": order.customer,
            "status": order.status,
            "revision": getattr(order, "revision", None),
            "revision_state": getattr(order, "revision_state", None),
        },
        "piece": _piece_payload(piece),
        "permissions": {
            "can_view": True,
            "can_edit": edit["can_edit"],
            "edit_reason": edit["reason"],
        },
        "stage": edit["stage"],
    }


@frappe.whitelist()
def save_drawing_workspace(
    order_name: str,
    piece_name: str,
    drawing_json: str | dict[str, Any],
    geometry_json: str | dict[str, Any],
) -> dict[str, Any]:
    """Persist one V4 drawing without granting broad order-edit authority."""

    name = _lock_order(order_name)
    order = _get_order(name)
    _assert_editable(order)
    piece = _get_piece(order, piece_name)

    drawing = validate_special_shape_drawing(drawing_json)
    if not drawing:
        frappe.throw(_("ارسم محيط الدرفة قبل الحفظ."))
    _validate_v4_piece_dimensions(drawing, piece)

    geometry = validate_special_shape_geometry(
        geometry_json,
        expected_width_cm=piece.width_cm,
        expected_length_cm=piece.length_cm,
    )
    if not geometry:
        frappe.throw(_("تعذر إنشاء هندسة تصنيع صالحة من الرسم."))

    previous_image = getattr(piece, "special_shape_reference_image", None) or ""
    piece.special_shape_drawing_json = _serialize(drawing)
    piece.special_shape_geometry_json = _serialize(geometry)
    piece.special_shape_documentation_mode = "Drawing"
    piece.special_shape_reference_image = ""
    piece.special_shape_reference_image_meta_json = ""
    piece.special_shape_status = "Documented"
    _save_order(order)
    if previous_image:
        _delete_reference_file(previous_image, order.name)

    saved_piece = _get_piece(order, piece.name)
    return {
        "order_name": order.name,
        "piece": _piece_payload(saved_piece),
        "plan_needs_recalculation": getattr(order, "plan_needs_recalculation", None),
        "special_shape_price_status": saved_piece.special_shape_price_status,
    }


@frappe.whitelist()
def save_reference_image(
    order_name: str,
    piece_name: str,
    image_data_url: str,
    metadata_json: str | dict[str, Any],
) -> dict[str, Any]:
    """Persist a cropped private image as the official documentation source."""

    name = _lock_order(order_name)
    order = _get_order(name)
    _assert_editable(order)
    piece = _get_piece(order, piece_name)

    content, mime, extension = _decode_reference_image(image_data_url)
    metadata = _validate_reference_metadata(metadata_json, mime)
    previous_image = getattr(piece, "special_shape_reference_image", None) or ""

    file_doc = save_file(
        f"special-door-{order.name}-{piece.name}{extension}",
        content,
        "Door Cutting Order",
        order.name,
        is_private=1,
    )
    try:
        piece.special_shape_documentation_mode = "Image"
        piece.special_shape_reference_image = file_doc.file_url
        piece.special_shape_reference_image_meta_json = _serialize(metadata)
        # A reference image is documentation, not exact manufacturing geometry.
        # Clear old vector geometry so a changed image can never silently reuse
        # stale CNC/cutting geometry from a previous drawing.
        piece.special_shape_drawing_json = ""
        piece.special_shape_geometry_json = ""
        piece.special_shape_status = "Documented"
        _save_order(order)
    except Exception:
        try:
            frappe.delete_doc("File", file_doc.name, ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title="Failed to rollback special door reference image",
                message=frappe.get_traceback(),
            )
        raise

    if previous_image and previous_image != file_doc.file_url:
        _delete_reference_file(previous_image, order.name, exclude_name=file_doc.name)

    saved_piece = _get_piece(order, piece.name)
    return {
        "order_name": order.name,
        "piece": _piece_payload(saved_piece),
        "plan_needs_recalculation": getattr(order, "plan_needs_recalculation", None),
        "special_shape_price_status": saved_piece.special_shape_price_status,
    }


@frappe.whitelist()
def remove_reference_image(order_name: str, piece_name: str) -> dict[str, Any]:
    """Remove the official reference image and return the piece to drawing mode."""

    name = _lock_order(order_name)
    order = _get_order(name)
    _assert_editable(order)
    piece = _get_piece(order, piece_name)
    previous_image = getattr(piece, "special_shape_reference_image", None) or ""

    piece.special_shape_documentation_mode = "Drawing"
    piece.special_shape_reference_image = ""
    piece.special_shape_reference_image_meta_json = ""
    _save_order(order)
    if previous_image:
        _delete_reference_file(previous_image, order.name)

    saved_piece = _get_piece(order, piece.name)
    return {
        "order_name": order.name,
        "piece": _piece_payload(saved_piece),
        "plan_needs_recalculation": getattr(order, "plan_needs_recalculation", None),
        "special_shape_price_status": saved_piece.special_shape_price_status,
    }


__all__ = [
    "get_drawing_workspace",
    "remove_reference_image",
    "save_drawing_workspace",
    "save_reference_image",
]
