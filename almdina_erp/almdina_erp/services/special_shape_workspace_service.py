from __future__ import annotations

import base64
import binascii
import json
import math
import os
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime
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
    DOCUMENTATION_SCHEMA,
    DOCUMENTATION_VERSION,
    validate_special_shape_drawing,
)

_DIMENSION_TOLERANCE_MM = 0.01
_MAX_REFERENCE_IMAGE_BYTES = 8 * 1024 * 1024
_IMAGE_SIGNATURES = {
    ".jpg": lambda content: content.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda content: content.startswith(b"\xff\xd8\xff"),
    ".png": lambda content: content.startswith(b"\x89PNG\r\n\x1a\n"),
    ".webp": lambda content: content.startswith(b"RIFF") and content[8:12] == b"WEBP",
}


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
        message=_("You do not have permission to open the special door documentation workspace for this order."),
    )
    return order


def _piece(order: Any, piece_name: str) -> Any:
    name = _required(piece_name, _("Door Cutting Order Detail"))
    for row in order.pieces or []:
        if str(row.name) != name:
            continue
        if str(row.piece_type or "Regular") != "Special":
            frappe.throw(_("The documentation workspace is available for special doors only."))
        return row
    frappe.throw(_("The selected door does not belong to this order."), frappe.DoesNotExistError)


def _route_active(order: Any) -> bool:
    return bool(
        getattr(order, "current_production_stage", None)
        or getattr(order, "production_path", None)
    )


def _edit_state(order: Any) -> dict[str, Any]:
    if str(getattr(order, "status", "") or "").strip() == "Delivered":
        return {"can_edit": False, "reason": _("Delivered orders are read-only."), "stage": None}
    if not document_has_capability(order, Capability.EDIT_SPECIAL_DRAWING):
        return {"can_edit": False, "reason": _("You do not have permission to edit special door documentation."), "stage": None}
    if _route_active(order):
        stage = current_stage_operational_access(order)
        allowed = bool(stage.get("actor_holds_operational_role"))
        return {"can_edit": allowed, "reason": "" if allowed else str(stage.get("reason") or ""), "stage": stage}
    allowed = user_can_edit_order(
        getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
    )
    return {"can_edit": bool(allowed), "reason": "" if allowed else _("Documentation can be edited when the order state allows it."), "stage": None}


def _assert_editable(order: Any) -> None:
    if str(getattr(order, "status", "") or "").strip() == "Delivered":
        frappe.throw(_("Delivered orders are read-only."), frappe.PermissionError)
    require_document_capability(
        order,
        Capability.EDIT_SPECIAL_DRAWING,
        message=_("You are not allowed to edit special door documentation."),
    )
    if _route_active(order):
        require_stage_operational_access(order)
    else:
        assert_order_editable(order)


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validate_canvas(documentation: dict[str, Any], piece: Any) -> None:
    if documentation.get("schema") != DOCUMENTATION_SCHEMA or int(documentation.get("version") or 0) != DOCUMENTATION_VERSION:
        frappe.throw(_("The documentation workspace accepts only the current contract."))
    canvas = documentation.get("canvas") or {}
    expected_width = float(piece.width_cm or 0) * 10
    expected_height = float(piece.length_cm or 0) * 10
    if not math.isclose(float(canvas.get("widthMm") or 0), expected_width, rel_tol=0, abs_tol=_DIMENSION_TOLERANCE_MM):
        frappe.throw(_("The documentation width does not match the door width."))
    if not math.isclose(float(canvas.get("heightMm") or 0), expected_height, rel_tol=0, abs_tol=_DIMENSION_TOLERANCE_MM):
        frappe.throw(_("The documentation length does not match the door length."))


def _reference_file(file_url: str, piece: Any) -> Any:
    normalized = str(file_url or "").strip()
    file_row = frappe.db.get_value(
        "File",
        {"file_url": normalized},
        ["name", "file_url", "is_private", "attached_to_doctype", "attached_to_name"],
        as_dict=True,
    )
    if (
        not file_row
        or not int(file_row.is_private or 0)
        or str(file_row.attached_to_doctype or "") != "Door Cutting Order Detail"
        or str(file_row.attached_to_name or "") != str(piece.name)
    ):
        frappe.throw(_("The reference image does not belong to this door."), frappe.PermissionError)
    return file_row


def _validate_reference_scope(documentation: dict[str, Any], piece: Any) -> None:
    reference = documentation.get("reference") or {}
    if reference:
        _reference_file(str(reference.get("fileUrl") or ""), piece)


def _piece_payload(row: Any) -> dict[str, Any]:
    return {
        "name": row.name,
        "piece_no": row.piece_no or row.idx,
        "piece_type": row.piece_type or "Regular",
        "width_cm": row.width_cm,
        "length_cm": row.length_cm,
        "special_shape_drawing_json": row.special_shape_drawing_json or "",
        "special_shape_status": row.special_shape_status or "Needs Documentation",
        "documentation_updated_by": row.special_shape_drawing_updated_by,
        "documentation_updated_on": row.special_shape_drawing_updated_on,
    }


def _decode_image(file_name: str, content_base64: str) -> tuple[str, bytes]:
    safe_name = os.path.basename(str(file_name or "").strip().replace("\\", "/"))
    extension = os.path.splitext(safe_name)[1].lower()
    signature = _IMAGE_SIGNATURES.get(extension)
    if not safe_name or signature is None:
        frappe.throw(_("Use a JPG, PNG, or WEBP image only."))
    encoded = str(content_base64 or "")
    if "," in encoded and encoded.lstrip().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    if len(encoded) > ((_MAX_REFERENCE_IMAGE_BYTES * 4) // 3) + 16:
        frappe.throw(_("The image is larger than 8 MB."))
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        frappe.throw(_("Could not read the image content."))
    if not content or len(content) > _MAX_REFERENCE_IMAGE_BYTES:
        frappe.throw(_("The image is larger than 8 MB."))
    if not signature(content):
        frappe.throw(_("The image content does not match the file extension."))
    return safe_name, content


@frappe.whitelist()
def get_drawing_workspace(order_name: str, piece_name: str) -> dict[str, Any]:
    order = _order(order_name)
    piece = _piece(order, piece_name)
    edit = _edit_state(order)
    return {
        "order": {"name": order.name, "customer": order.customer, "status": order.status},
        "piece": _piece_payload(piece),
        "permissions": {"can_view": True, "can_edit": edit["can_edit"], "edit_reason": edit["reason"]},
        "stage": edit["stage"],
        "manufacturing_notice": _("This documents the customer order and is not a manufacturing file"),
    }


@frappe.whitelist()
def upload_reference_image(order_name: str, piece_name: str, file_name: str, content_base64: str) -> dict[str, Any]:
    order = _order(order_name)
    _assert_editable(order)
    piece = _piece(order, piece_name)
    safe_name, content = _decode_image(file_name, content_base64)
    file_doc = save_file(safe_name, content, "Door Cutting Order Detail", piece.name, is_private=1)
    return {"file_url": file_doc.file_url, "file_name": file_doc.file_name, "is_private": True}


@frappe.whitelist()
def remove_reference_image(order_name: str, piece_name: str, file_url: str) -> dict[str, Any]:
    order = _order(order_name)
    _assert_editable(order)
    piece = _piece(order, piece_name)
    file_row = _reference_file(file_url, piece)
    frappe.get_doc("File", file_row.name).delete()
    return {"removed": True}


@frappe.whitelist()
def save_documentation_workspace(
    order_name: str,
    piece_name: str,
    documentation_json: str | dict[str, Any],
) -> dict[str, Any]:
    order = _order(order_name)
    _assert_editable(order)
    piece = _piece(order, piece_name)
    documentation = validate_special_shape_drawing(documentation_json)
    if not documentation:
        frappe.throw(_("Add documentation before saving."))
    _validate_canvas(documentation, piece)
    _validate_reference_scope(documentation, piece)

    documentation_text = _serialize(documentation)
    changed = documentation_text != str(piece.special_shape_drawing_json or "")
    values: dict[str, Any] = {
        "special_shape_drawing_json": documentation_text,
        "special_shape_status": "Documented",
        "special_shape_drawing_updated_by": frappe.session.user,
        "special_shape_drawing_updated_on": now_datetime(),
    }
    frappe.db.set_value("Door Cutting Order Detail", piece.name, values, update_modified=True)
    saved = frappe.get_doc("Door Cutting Order Detail", piece.name)
    return {
        "order_name": order.name,
        "piece": _piece_payload(saved),
        "documentation_changed": changed,
    }


__all__ = [
    "get_drawing_workspace",
    "remove_reference_image",
    "save_documentation_workspace",
    "upload_reference_image",
]
