from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    DRAFT,
    UPLOADED_DXF,
    cancel_approval_transition,
    prefer_plan_tab_for_source,
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
    ) or repository.latest_document(
        order.name,
        source_type=UPLOADED_DXF,
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


def _clear_order_approved_plan(order: Any) -> None:
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "approved_plan",
        None,
        update_modified=False,
    )
    order.approved_plan = None


def cancel_approved_order_plan(order: Any) -> dict[str, Any]:
    """Cancel the current immutable production approval while preserving history.

    The approved Cutting Plan is transitioned to ``Cancelled`` and the aggregate
    relation on Door Cutting Order is cleared. Geometry is never mutated back into
    Draft on that historical revision. Instead a geometry-preserving Draft copy is
    created (or an already newer Draft of the same source is reused) so the same
    distribution can be re-approved without recalculation when still compatible.
    A stale ``approved_plan`` pointing at another order is cleared without touching
    that foreign plan.
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
        _clear_order_approved_plan(order)
        _reset_drawing_dxf_status(order, repository)
        return {
            "name": order.name,
            "cancelled_plan": None,
            "plan_status": str(getattr(plan, "status", None) or ""),
            "approved_plan": None,
            "draft_plan": None,
            "draft_source_type": None,
            "prefer_plan_tab": "System",
            "draft_reused": False,
        }

    source_type = str(getattr(plan, "source_type", None) or "").strip()
    existing_draft = repository.find_newer_draft(
        order.name,
        source_type=source_type,
        min_revision=int(getattr(plan, "revision", 0) or 0),
    )
    draft_reused = bool(existing_draft)
    # Create the working Draft while the tip is still Approved so DocType lineage
    # validation and based_on_plan contracts stay intact.
    draft = existing_draft or repository.create_geometry_preserving_draft(plan, order=order)

    _before, after = cancel_approval_transition(getattr(plan, "status", None))
    plan.status = after
    repository.save_document(plan, allow_status_transition=True)

    _clear_order_approved_plan(order)
    _reset_drawing_dxf_status(order, repository)

    from almdina_erp.almdina_erp.services.final_price_approval_service import (
        maybe_invalidate_final_price_approval,
    )

    # Cancelling production approval can move cost authority to another plan.
    maybe_invalidate_final_price_approval(
        order.name,
        reason="cost_plan_authority_changed",
        only_if_basis_changed=True,
        order=order,
    )

    draft_name = str(getattr(draft, "name", None) or "").strip() or None
    return {
        "name": order.name,
        "cancelled_plan": plan.name,
        "plan_status": after,
        "approved_plan": None,
        "draft_plan": draft_name,
        "draft_source_type": source_type or None,
        "prefer_plan_tab": prefer_plan_tab_for_source(source_type),
        "draft_reused": draft_reused,
    }


__all__ = ["cancel_approved_order_plan"]
