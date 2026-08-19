from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    DRAFT,
    UPLOADED_DXF,
    cancel_approval_transition,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)


def _reset_drawing_dxf_status(order: Any, repository: FrappeCuttingPlanCommandRepository) -> None:
    meta = frappe.get_meta("Door Cutting Order")
    if not meta.has_field("drawing_dxf_status"):
        return

    uploaded = repository.latest_document(
        order.name,
        source_type=UPLOADED_DXF,
        status=DRAFT,
    )
    has_valid_uploaded_dxf = bool(
        uploaded
        and str(getattr(uploaded, "dxf_file", None) or "").strip()
        and str(getattr(uploaded, "dxf_status", None) or "") == "Validated"
    )
    status = "Uploaded" if has_valid_uploaded_dxf else "None"
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "drawing_dxf_status",
        status,
        update_modified=False,
    )
    order.drawing_dxf_status = status


def cancel_approved_order_plan(order: Any) -> dict[str, Any]:
    """Cancel the current immutable production approval while preserving history.

    The approved Cutting Plan is transitioned to ``Cancelled`` and the aggregate
    relation on Door Cutting Order is cleared. Geometry is never mutated back into
    Draft; a later edit/recalculation creates or reuses a proper Draft revision.
    """

    require_cutting_plan_capability(
        order,
        Capability.APPROVE_DXF,
        message=_("لا تملك صلاحية إلغاء اعتماد خطة القص لهذا الطلب."),
    )

    approved_name = str(getattr(order, "approved_plan", None) or "").strip()
    if not approved_name:
        frappe.throw(_("لا توجد خطة قص معتمدة لإلغاء اعتمادها."), frappe.ValidationError)

    repository = FrappeCuttingPlanCommandRepository(Capability.APPROVE_DXF)
    plan = repository.get_document(approved_name)
    if str(getattr(plan, "door_cutting_order", None) or "") != str(order.name):
        frappe.throw(_("الخطة المعتمدة لا تتبع هذا الطلب."), frappe.ValidationError)

    _before, after = cancel_approval_transition(getattr(plan, "status", None))
    plan.status = after
    repository.save_document(plan, allow_status_transition=True)

    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "approved_plan",
        None,
        update_modified=False,
    )
    order.approved_plan = None
    _reset_drawing_dxf_status(order, repository)

    return {
        "name": order.name,
        "cancelled_plan": plan.name,
        "plan_status": after,
        "approved_plan": None,
    }


__all__ = ["cancel_approved_order_plan"]
