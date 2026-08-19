from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.security.drawing_approval_policy import (
    DrawingApprovalState,
    approval_warning,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import (
    require_stage_operational_access,
)


def _state(order: Any) -> DrawingApprovalState:
    return DrawingApprovalState(
        status=str(order.status or ""),
        production_path=str(order.production_path or ""),
        current_department=str(order.current_department or ""),
        approved_plan=str(order.approved_plan or ""),
    )


def _authorized_order(order_name: str) -> Any:
    """Lock and authorize one parent order before any Plan approval decision."""

    name = str(order_name or "").strip()
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = shop_floor_gateway.get_order(name)
    order.check_permission("read")
    require_cutting_plan_capability(
        order,
        Capability.APPROVE_DXF,
        message=_("لا تملك صلاحية اعتماد خطة القص لهذا الطلب."),
    )
    require_stage_operational_access(order)
    return order


@frappe.whitelist()
def approve_production_dxf(
    order_name: str,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Approve the reviewed canonical Cutting Plan revision.

    This boundary never recalculates, snapshots, or saves the Door Cutting Order.
    Missing/stale plans fail closed in the Cutting Plan command; the approver must
    explicitly refresh the plan and review it before trying again.
    """

    order = _authorized_order(order_name)
    state = _state(order)

    from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
        approve_order_plan,
    )

    result = approve_order_plan(order, plan_source)
    approved_source = result.get("approved_plan_source") or "System"
    result.update(
        {
            "approved_by": frappe.session.user,
            "was_previously_approved": bool(state.approved_plan),
            "warning": approval_warning(state),
        }
    )
    order.add_comment(
        "Info",
        text=_("تم {0} خطة القص بواسطة {1} من المصدر {2}.").format(
            _("إعادة اعتماد") if state.approved_plan else _("اعتماد"),
            frappe.session.user,
            approved_source,
        ),
    )
    return result


@frappe.whitelist()
def cancel_production_plan_approval(order_name: str) -> dict[str, Any]:
    """Cancel the current production approval through the focused Plan command."""

    order = _authorized_order(order_name)
    state = _state(order)
    if not state.approved_plan:
        frappe.throw(_("لا توجد خطة قص معتمدة لإلغاء اعتمادها."), frappe.ValidationError)

    from almdina_erp.almdina_erp.services.cutting_plan_approval_cancellation_service import (
        cancel_approved_order_plan,
    )

    result = cancel_approved_order_plan(order)
    order.add_comment(
        "Info",
        text=_("تم إلغاء اعتماد خطة القص {0} بواسطة {1}.").format(
            state.approved_plan,
            frappe.session.user,
        ),
    )
    return result


__all__ = ["approve_production_dxf", "cancel_production_plan_approval"]
