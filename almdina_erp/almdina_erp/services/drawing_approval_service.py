from __future__ import annotations

from typing import Any

import frappe
from frappe import _

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
    "not_at_drawing": "Drawing approval is only available while the order is at Drawing.",
    "unsupported_plan_source": "Unsupported drawing plan source.",
    "system_plan_missing": "The system cutting plan is not available for approval.",
    "custom_plan_missing": "Upload and validate a DXF plan before approving it.",
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
        _(_POLICY_MESSAGES.get(error.code, "Drawing approval is not allowed.")),
        frappe.PermissionError,
    )


def _authorized_order(order_name: str) -> Any:
    order = shop_floor_gateway.get_order(order_name)
    order.check_permission("read")
    require_document_capability(order, Capability.APPROVE_DXF)
    try:
        validate_drawing_approval(_state(order))
    except DrawingApprovalDenied as error:
        _throw_policy_error(error)
    return order


@frappe.whitelist()
def approve_production_dxf(
    order_name: str,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Approve or replace the selected drawing plan through a role capability.

    The administrator decides which roles own ``approve_dxf``. Assignment to the
    drawing stage is intentionally not part of this command. A previous approval
    is accepted and superseded; callers receive a warning flag for transparent UX.
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
        text=_("Drawing plan {0} by {1} using {2}.").format(
            _("re-approved") if state.approved_plan else _("approved"),
            frappe.session.user,
            validated_source,
        ),
    )
    return result


__all__ = ["approve_production_dxf"]
