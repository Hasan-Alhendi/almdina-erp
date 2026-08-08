from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.security.drawing_action_policy import (
    DrawingActionDenied,
    validate_plan_source,
)
from almdina_erp.almdina_erp.application.security.drawing_approval_policy import (
    DrawingApprovalDenied,
    DrawingApprovalState,
    approval_warning,
    validate_drawing_approval,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)


_POLICY_MESSAGES = {
    "not_at_drawing": "اعتماد خطة القص متاح فقط عندما يكون الطلب في مرحلة الرسم.",
    "unsupported_plan_source": "مصدر خطة القص المحدد غير مدعوم.",
    "system_plan_missing": "لا توجد خطة قص من النظام صالحة للاعتماد.",
    "custom_plan_missing": "ارفع خطة DXF صالحة وتحقق منها قبل اعتمادها.",
}


def _state(order: Any) -> DrawingApprovalState:
    return DrawingApprovalState(
        status=str(order.status or ""),
        production_path=str(order.production_path or ""),
        current_department=str(order.current_department or ""),
        approved_plan=str(order.approved_plan or ""),
    )


def _throw_policy_error(error: DrawingApprovalDenied | DrawingActionDenied) -> None:
    frappe.throw(
        _(_POLICY_MESSAGES.get(error.code, "لا يمكن اعتماد خطة القص في الحالة الحالية.")),
        frappe.PermissionError,
    )


def _authorized_order(order_name: str) -> Any:
    """Lock and authorize one order before any approval decision is made."""

    name = str(order_name or "").strip()
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = shop_floor_gateway.get_order(name)
    order.check_permission("read")

    # ``approve_dxf`` is the historical capability key. It authorizes approval
    # of the selected production cutting plan (system or validated DXF) and is
    # intentionally independent from cost visibility/editing capabilities.
    require_document_capability(
        order,
        Capability.APPROVE_DXF,
        message=_("لا تملك صلاحية اعتماد خطة القص لهذا الطلب."),
    )
    try:
        validate_drawing_approval(_state(order))
    except DrawingApprovalDenied as error:
        _throw_policy_error(error)
    return order


def _assert_reviewed_system_plan(order: Any) -> None:
    """Approval must freeze exactly the plan the approver reviewed.

    Recalculating inside the approval transaction can silently change board count,
    waste, rotations, and layout after the user has reviewed the plan. A stale or
    missing system plan therefore has to be recalculated explicitly first.
    """

    if cint(order.plan_needs_recalculation) or not order.cutting_plan_json:
        frappe.throw(
            _(
                "خطة القص بحاجة إلى إعادة حساب قبل الاعتماد. أعد حساب الخطة، راجع النتيجة الجديدة، ثم اعتمدها."
            ),
            frappe.ValidationError,
        )


@frappe.whitelist()
def approve_production_dxf(
    order_name: str,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Approve or replace the selected production cutting plan.

    Approval is capability-driven, row-locked, independent from cost permissions,
    and never recalculates a system plan implicitly. Assignment to the drawing
    stage is intentionally not an authorization requirement; the configurable
    approval capability is the business authority.
    """

    order = _authorized_order(order_name)
    state = _state(order)

    from almdina_erp.almdina_erp.services.dual_plan_fields import (
        get_custom_plan_json,
        get_system_plan_json,
    )

    try:
        validated_source = validate_plan_source(
            plan_source,
            has_system_plan=bool(get_system_plan_json(order) or order.cutting_plan_json),
            has_custom_plan=bool(get_custom_plan_json(order)),
            has_production_dxf=bool(order.production_dxf),
        )
    except DrawingActionDenied as error:
        _throw_policy_error(error)

    if validated_source == "System":
        _assert_reviewed_system_plan(order)

    from almdina_erp.almdina_erp.services.cutting_plan_service import (
        _lock_order_for_production,
    )

    result = _lock_order_for_production(
        order,
        preserve_status=True,
        plan_source=validated_source,
    )
    result.update(
        {
            "approved_by": frappe.session.user,
            "approved_plan_source": validated_source,
            "was_previously_approved": bool(state.approved_plan),
            "warning": approval_warning(state),
        }
    )
    order.add_comment(
        "Info",
        text=_("تم {0} خطة القص بواسطة {1} من المصدر {2}.").format(
            _("إعادة اعتماد") if state.approved_plan else _("اعتماد"),
            frappe.session.user,
            validated_source,
        ),
    )
    return result


__all__ = ["approve_production_dxf"]
