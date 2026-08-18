from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cutting_plan_capability_allowed,
    require_cutting_plan_capability,
)


_PLAN_FIELDS = (
    "name",
    "source_type",
    "revision",
    "based_on_plan",
    "status",
    "approved_by",
    "approved_on",
    "optimization_mode",
    "machine_type",
    "optimization_time_limit_sec",
    "method_key",
    "method_label",
    "ordering_strategy",
    "score",
    "engine_version",
    "attempts",
    "solver_status",
    "search_elapsed_sec",
    "validation_status",
    "validated_on",
    "validation_errors",
    "board_description",
    "full_board_width_mm",
    "full_board_length_mm",
    "usable_board_width_mm",
    "usable_board_length_mm",
    "kerf_mm",
    "trim_margin_mm",
    "plan_needs_recalculation",
    "estimated_cut_count",
    "estimated_cut_length_m",
    "largest_reusable_free_area_m2",
    "rotation_count",
    "required_boards",
    "used_area_m2",
    "total_source_area_m2",
    "waste_area_m2",
    "waste_percent",
    "dxf_file",
    "dxf_status",
    "dxf_uploaded_by",
    "dxf_uploaded_on",
    "snapshot_json",
    "modified",
)


def _authorized_order(order_name: str) -> Any:
    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_cutting_plan_capability(
        order,
        Capability.VIEW_CUTTING_PLAN,
        message=_("لا تملك صلاحية عرض خطة القص لهذا الطلب."),
    )
    return order


def _capabilities(order: Any) -> dict[str, bool]:
    return {
        "view_system": cutting_plan_capability_allowed(order, Capability.VIEW_SYSTEM_CUTTING_PLAN),
        "view_uploaded": cutting_plan_capability_allowed(order, Capability.VIEW_UPLOADED_CUTTING_PLAN),
        "view_approved": cutting_plan_capability_allowed(order, Capability.VIEW_APPROVED_CUTTING_PLAN),
        "edit_settings": cutting_plan_capability_allowed(order, Capability.EDIT_OPTIMIZER_SETTINGS),
        "recalculate": cutting_plan_capability_allowed(order, Capability.RECALCULATE_PLAN),
        "upload_dxf": cutting_plan_capability_allowed(order, Capability.UPLOAD_DXF),
        "replace_dxf": cutting_plan_capability_allowed(order, Capability.REPLACE_DXF),
        "approve": cutting_plan_capability_allowed(order, Capability.APPROVE_DXF),
        "print": cutting_plan_capability_allowed(order, Capability.PRINT_CUTTING_PLAN),
        "export_dxf": cutting_plan_capability_allowed(order, Capability.EXPORT_DXF),
    }


def _plan_row(plan: Any) -> dict[str, Any]:
    snapshot_json = sanitize_plan_snapshot_json(str(plan.get("snapshot_json") or ""))
    return {
        "name": plan.get("name"),
        "source_type": str(plan.get("source_type") or ""),
        "revision": cint(plan.get("revision")),
        "based_on_plan": plan.get("based_on_plan"),
        "status": str(plan.get("status") or ""),
        "approved_by": plan.get("approved_by"),
        "approved_on": plan.get("approved_on"),
        "settings": {
            "packing_mode": str(plan.get("optimization_mode") or "Auto Pro"),
            "cutting_machine_type": str(plan.get("machine_type") or "Auto"),
            "optimization_time_limit_sec": flt(plan.get("optimization_time_limit_sec")),
            "kerf_mm": flt(plan.get("kerf_mm")),
            "trim_margin_mm": flt(plan.get("trim_margin_mm")),
        },
        "engine": {
            "method_key": plan.get("method_key"),
            "method_label": plan.get("method_label"),
            "ordering_strategy": plan.get("ordering_strategy"),
            "score": flt(plan.get("score")),
            "engine_version": plan.get("engine_version"),
            "attempts": cint(plan.get("attempts")),
            "solver_status": plan.get("solver_status"),
            "search_elapsed_sec": flt(plan.get("search_elapsed_sec")),
        },
        "validation": {
            "status": str(plan.get("validation_status") or "Pending"),
            "validated_on": plan.get("validated_on"),
            "errors": plan.get("validation_errors"),
            "needs_recalculation": bool(cint(plan.get("plan_needs_recalculation"))),
        },
        "board": {
            "description": plan.get("board_description"),
            "full_width_mm": flt(plan.get("full_board_width_mm")),
            "full_length_mm": flt(plan.get("full_board_length_mm")),
            "usable_width_mm": flt(plan.get("usable_board_width_mm")),
            "usable_length_mm": flt(plan.get("usable_board_length_mm")),
        },
        "quality": {
            "estimated_cut_count": cint(plan.get("estimated_cut_count")),
            "estimated_cut_length_m": flt(plan.get("estimated_cut_length_m")),
            "largest_reusable_free_area_m2": flt(plan.get("largest_reusable_free_area_m2")),
            "rotation_count": cint(plan.get("rotation_count")),
        },
        "totals": {
            "required_boards": cint(plan.get("required_boards")),
            "used_area_m2": flt(plan.get("used_area_m2")),
            "total_source_area_m2": flt(plan.get("total_source_area_m2")),
            "waste_area_m2": flt(plan.get("waste_area_m2")),
            "waste_percent": flt(plan.get("waste_percent")),
        },
        "dxf": {
            "file": plan.get("dxf_file"),
            "status": str(plan.get("dxf_status") or "None"),
            "uploaded_by": plan.get("dxf_uploaded_by"),
            "uploaded_on": plan.get("dxf_uploaded_on"),
        },
        "snapshot_json": snapshot_json,
        "modified": plan.get("modified"),
    }


def _latest(rows: list[Any], *, status: str, source_type: str | None = None) -> Any | None:
    for row in rows:
        if str(row.get("status") or "") != status:
            continue
        if source_type is not None and str(row.get("source_type") or "") != source_type:
            continue
        return row
    return None


def _approved(rows: list[Any], order: Any) -> Any | None:
    approved_name = str(getattr(order, "approved_plan", None) or "").strip()
    if approved_name:
        for row in rows:
            if row.get("name") == approved_name and str(row.get("status") or "") == APPROVED:
                return row
    return _latest(rows, status=APPROVED)


@frappe.whitelist()
def get_plan_workspace_snapshot(order_name: str) -> dict[str, Any]:
    """Return a plan-only read model for the unified order workspace.

    The payload intentionally excludes every monetary field. Capability filtering
    happens before individual source snapshots are exposed; mutation endpoints keep
    their own stricter lifecycle/stage authorization.
    """

    order = _authorized_order(order_name)
    capabilities = _capabilities(order)
    rows = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
        },
        fields=list(_PLAN_FIELDS),
        order_by="revision desc, modified desc",
    )

    system = _latest(rows, status=DRAFT, source_type=SYSTEM) if capabilities["view_system"] else None
    uploaded = (
        _latest(rows, status=DRAFT, source_type=UPLOADED_DXF)
        if capabilities["view_uploaded"]
        else None
    )
    approved = _approved(rows, order) if capabilities["view_approved"] else None

    return {
        "order_name": order.name,
        "order_status": str(getattr(order, "status", None) or "Draft"),
        "revision_state": str(getattr(order, "revision_state", None) or "Current"),
        "current_production_stage": getattr(order, "current_production_stage", None),
        "production_path": getattr(order, "production_path", None),
        "approved_plan": getattr(order, "approved_plan", None),
        "capabilities": capabilities,
        "plans": {
            "system_draft": _plan_row(system) if system else None,
            "uploaded_draft": _plan_row(uploaded) if uploaded else None,
            "approved": _plan_row(approved) if approved else None,
        },
    }


__all__ = ["get_plan_workspace_snapshot"]
