from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _

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

    name = _required_text(order_name, _("Door Cutting Order"))
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
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

    piece.special_shape_drawing_json = _serialize(drawing)
    piece.special_shape_geometry_json = _serialize(geometry)
    piece.special_shape_status = "Documented"

    # A focused drawing mutation may be allowed at the active drawing/production
    # stage even though broad in-place order editing is locked. The endpoint has
    # already enforced both capability and stage-role boundaries, and it mutates
    # drawing fields only before handing the document back to the canonical save
    # pipeline for pricing/plan invalidation and audit metadata.
    if _route_is_active(order):
        order.flags.allow_approved_edit = True
    order.save(ignore_permissions=True)

    saved_piece = _get_piece(order, piece.name)
    return {
        "order_name": order.name,
        "piece": _piece_payload(saved_piece),
        "plan_needs_recalculation": getattr(order, "plan_needs_recalculation", None),
        "special_shape_price_status": saved_piece.special_shape_price_status,
    }


__all__ = ["get_drawing_workspace", "save_drawing_workspace"]
