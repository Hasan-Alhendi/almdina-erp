from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.orders.piece_policy import reset_price_values
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
from almdina_erp.almdina_erp.services.order_edit_policy import assert_order_editable, user_can_edit_order
from almdina_erp.almdina_erp.services.special_shape_drawing_validation_service import validate_special_shape_drawing
from almdina_erp.almdina_erp.services.special_shape_service import validate_special_shape_geometry

_DRAWING_SCHEMA = "almdina.door-drawing"
_DRAWING_VERSION = 4
_DIMENSION_TOLERANCE_MM = 0.01


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
            frappe.throw(_("مساحة الرسم متاحة للدرف الخاصة فقط."))
        return row
    frappe.throw(_("الدرفة المحددة لا تنتمي إلى هذا الطلب."), frappe.DoesNotExistError)


def _route_active(order: Any) -> bool:
    return bool(getattr(order, "current_production_stage", None) or getattr(order, "production_path", None))


def _edit_state(order: Any) -> dict[str, Any]:
    if not document_has_capability(order, Capability.EDIT_SPECIAL_DRAWING):
        return {"can_edit": False, "reason": _("ليس لديك صلاحية تعديل رسومات الدرف الخاصة."), "stage": None}
    if _route_active(order):
        stage = current_stage_operational_access(order)
        allowed = bool(stage.get("actor_holds_operational_role"))
        return {"can_edit": allowed, "reason": "" if allowed else str(stage.get("reason") or ""), "stage": stage}
    allowed = user_can_edit_order(getattr(order, "status", None), revision_state=getattr(order, "revision_state", None))
    return {"can_edit": bool(allowed), "reason": "" if allowed else _("يمكن تعديل الرسم عندما يسمح وضع الطلب بذلك."), "stage": None}


def _assert_editable(order: Any) -> None:
    require_document_capability(order, Capability.EDIT_SPECIAL_DRAWING, message=_("لا تملك صلاحية تعديل رسومات الدرف الخاصة."))
    if _route_active(order):
        require_stage_operational_access(order)
    else:
        assert_order_editable(order)


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _validate_blank(drawing: dict[str, Any], piece: Any) -> None:
    if drawing.get("schema") != _DRAWING_SCHEMA or int(drawing.get("version") or 0) != _DRAWING_VERSION:
        frappe.throw(_("مساحة الرسم تقبل Drawing V4 فقط."))
    blank = drawing.get("blank") or {}
    expected_width = float(piece.width_cm or 0) * 10
    expected_height = float(piece.length_cm or 0) * 10
    if not math.isclose(float(blank.get("widthMm") or 0), expected_width, rel_tol=0, abs_tol=_DIMENSION_TOLERANCE_MM):
        frappe.throw(_("عرض الرسم لا يطابق عرض الدرفة."))
    if not math.isclose(float(blank.get("heightMm") or 0), expected_height, rel_tol=0, abs_tol=_DIMENSION_TOLERANCE_MM):
        frappe.throw(_("طول الرسم لا يطابق طول الدرفة."))


def _piece_payload(row: Any) -> dict[str, Any]:
    return {
        "name": row.name,
        "piece_no": row.piece_no or row.idx,
        "piece_type": row.piece_type or "Regular",
        "width_cm": row.width_cm,
        "length_cm": row.length_cm,
        "special_shape_drawing_json": row.special_shape_drawing_json or "",
        "special_shape_geometry_json": row.special_shape_geometry_json or "",
        "special_shape_status": row.special_shape_status or "Needs Documentation",
    }


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
    }


@frappe.whitelist()
def save_drawing_workspace(order_name: str, piece_name: str, drawing_json: str | dict[str, Any], geometry_json: str | dict[str, Any]) -> dict[str, Any]:
    order = _order(order_name)
    _assert_editable(order)
    piece = _piece(order, piece_name)
    drawing = validate_special_shape_drawing(drawing_json)
    if not drawing:
        frappe.throw(_("ارسم محيط الدرفة قبل الحفظ."))
    _validate_blank(drawing, piece)
    geometry = validate_special_shape_geometry(geometry_json, expected_width_cm=piece.width_cm, expected_length_cm=piece.length_cm)
    if not geometry:
        frappe.throw(_("تعذر إنشاء هندسة تصنيع صالحة من الرسم."))

    drawing_text = _serialize(drawing)
    geometry_text = _serialize(geometry)
    changed = drawing_text != str(piece.special_shape_drawing_json or "") or geometry_text != str(piece.special_shape_geometry_json or "")
    values: dict[str, Any] = {
        "special_shape_drawing_json": drawing_text,
        "special_shape_geometry_json": geometry_text,
        "special_shape_status": "Documented",
        "special_shape_drawing_updated_by": frappe.session.user,
        "special_shape_drawing_updated_on": now_datetime(),
    }
    if changed:
        values.update(reset_price_values("Special"))
    frappe.db.set_value("Door Cutting Order Detail", piece.name, values, update_modified=True)
    if changed:
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            {"plan_needs_recalculation": 1, "calculated_plan_input_hash": "", "calculated_plan_metadata_hash": ""},
            update_modified=True,
        )
    saved = frappe.get_doc("Door Cutting Order Detail", piece.name)
    return {"order_name": order.name, "piece": _piece_payload(saved), "plan_needs_recalculation": 1 if changed else int(getattr(order, "plan_needs_recalculation", 0) or 0)}


__all__ = ["get_drawing_workspace", "save_drawing_workspace"]
