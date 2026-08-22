from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
    CuttingPlanPreviewSession,
    optimizer_settings_fingerprint,
)
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT, SYSTEM
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    apply_plan_costs,
    initialize_draft_plan_cost_snapshot,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_commit import (
    apply_exact_system_preview,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_store import (
    FrappeCuttingPlanPreviewStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    calculate_system_plan,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_assignment_access import (
    require_stage_assignment_access,
)
from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
    _assert_recalculation_state,
    plan_payload,
)
from almdina_erp.almdina_erp.services.plan_settings_edit_service import (
    assert_plan_settings_edit_lifecycle,
    normalize_plan_settings_updates,
)


_SETTING_TO_PLAN_FIELD = {
    "packing_mode": "optimization_mode",
    "cutting_machine_type": "machine_type",
    "kerf_mm": "kerf_mm",
    "trim_margin_mm": "trim_margin_mm",
    "optimization_time_limit_sec": "optimization_time_limit_sec",
}


def _require_preview_capabilities(order: Any) -> None:
    require_cutting_plan_capability(
        order,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        message=_("لا تملك صلاحية تعديل إعدادات خطة القص لهذا الطلب."),
    )
    require_cutting_plan_capability(
        order,
        Capability.RECALCULATE_PLAN,
        message=_("لا تملك صلاحية معاينة خطة القص لهذا الطلب."),
    )


def _normalized_settings(values: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_plan_settings_updates(values)
    missing = [name for name in _SETTING_TO_PLAN_FIELD if name not in normalized]
    if missing:
        frappe.throw(
            _("إعدادات معاينة خطة القص غير مكتملة. أعد تحميل الصفحة ثم حاول مرة أخرى."),
            frappe.ValidationError,
        )
    return normalized


def _apply_settings(plan: Any, settings: dict[str, Any]) -> None:
    for setting_name, plan_field in _SETTING_TO_PLAN_FIELD.items():
        setattr(plan, plan_field, settings[setting_name])


def _preview_summary(plan: Any) -> dict[str, Any]:
    return {
        "settings": {
            "packing_mode": str(plan.optimization_mode or ""),
            "cutting_machine_type": str(plan.machine_type or ""),
            "kerf_mm": plan.kerf_mm,
            "trim_margin_mm": plan.trim_margin_mm,
            "optimization_time_limit_sec": plan.optimization_time_limit_sec,
        },
        "engine": {
            "method_key": str(plan.method_key or ""),
            "method_label": str(plan.method_label or ""),
            "attempts": int(plan.attempts or 0),
            "solver_status": str(plan.solver_status or ""),
            "elapsed_sec": float(plan.search_elapsed_sec or 0),
        },
        "quality": {
            "estimated_cut_count": int(plan.estimated_cut_count or 0),
            "estimated_cut_length_m": float(plan.estimated_cut_length_m or 0),
            "largest_reusable_free_area_m2": float(
                plan.largest_reusable_free_area_m2 or 0
            ),
            "rotation_count": int(plan.rotation_count or 0),
        },
        "totals": {
            "required_boards": int(plan.required_boards or 0),
            "used_area_m2": float(plan.used_area_m2 or 0),
            "total_source_area_m2": float(plan.total_source_area_m2 or 0),
            "waste_area_m2": float(plan.waste_area_m2 or 0),
            "waste_percent": float(plan.waste_percent or 0),
        },
        "cost": {
            "board_rate_usd": flt(plan.board_rate_usd),
            "cutting_cost_per_board_usd": flt(plan.cutting_cost_per_board_usd),
            "mdf_cost_usd": flt(plan.mdf_cost_usd),
            "cutting_cost_usd": flt(plan.cutting_cost_usd),
            "edge_cost_usd": flt(plan.edge_cost_usd),
            "total_cost_usd": flt(plan.total_cost_usd),
        },
        "validation": {
            "status": str(plan.validation_status or ""),
            "errors": str(plan.validation_errors or ""),
            "needs_recalculation": bool(plan.plan_needs_recalculation),
        },
    }


def _system_draft(order: Any, capability: str) -> Any:
    repository = FrappeCuttingPlanCommandRepository(capability)
    plan = repository.latest_document(
        order.name,
        source_type=SYSTEM,
        status=DRAFT,
    )
    if not plan:
        frappe.throw(
            _("لم تُنشأ خطة نظام بعد. استخدم «حساب خطة القص» لإنشاء الخطة الأولى ثم ابدأ المعاينة والتعديل."),
            frappe.ValidationError,
        )
    return plan


@frappe.whitelist()
def preview_cutting_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Calculate a disposable System-plan preview without any DB mutation."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    _require_preview_capabilities(order)
    require_stage_assignment_access(order)
    assert_plan_settings_edit_lifecycle(order)
    _assert_recalculation_state(order)

    source_plan = _system_draft(order, Capability.RECALCULATE_PLAN)
    settings = _normalized_settings(
        {
            "packing_mode": packing_mode,
            "cutting_machine_type": cutting_machine_type,
            "kerf_mm": kerf_mm,
            "trim_margin_mm": trim_margin_mm,
            "optimization_time_limit_sec": optimization_time_limit_sec,
        }
    )

    preview_plan = frappe.copy_doc(source_plan)
    _apply_settings(preview_plan, settings)
    calculate_system_plan(order, preview_plan)
    # The preview stays fully in memory, but its financial projection must use the
    # same calculator as a committed Plan so the operator can compare board-count
    # alternatives without mistaking the persisted Cost workspace for the preview.
    apply_plan_costs(preview_plan, edge_cost_usd=flt(getattr(order, "edge_cost_usd", 0)))
    snapshot = sanitize_plan_snapshot(
        frappe.parse_json(preview_plan.snapshot_json or "{}") or {}
    )
    if not snapshot.get("sheets"):
        frappe.throw(
            _("لم تنتج الخوارزمية خطة قابلة للعرض بهذه الإعدادات."),
            frappe.ValidationError,
        )

    preview_id = frappe.generate_hash(length=32)
    session = CuttingPlanPreviewSession(
        preview_id=preview_id,
        order_name=order.name,
        user=frappe.session.user,
        source_plan_name=source_plan.name,
        source_plan_modified=str(source_plan.modified or ""),
        input_fingerprint=str(preview_plan.input_fingerprint or ""),
        settings_fingerprint=optimizer_settings_fingerprint(settings),
        settings=settings,
        snapshot=dict(snapshot),
        created_at=str(now_datetime()),
    )
    FrappeCuttingPlanPreviewStore().put(session)

    return {
        "preview_id": session.preview_id,
        "settings_fingerprint": session.settings_fingerprint,
        "input_fingerprint": session.input_fingerprint,
        "plan": session.snapshot,
        "summary": _preview_summary(preview_plan),
        "is_preview": True,
    }


@frappe.whitelist()
def commit_cutting_plan_preview(order_name: str, preview_id: str) -> dict[str, Any]:
    """Commit exactly one trusted preview; never execute the optimizer again."""

    name = str(order_name or "").strip()
    token = str(preview_id or "").strip()
    if not name or not token:
        frappe.throw(_("معاينة خطة القص غير صالحة للحفظ."), frappe.ValidationError)

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    _require_preview_capabilities(order)
    require_stage_assignment_access(order)
    assert_plan_settings_edit_lifecycle(order)
    _assert_recalculation_state(order)

    session = FrappeCuttingPlanPreviewStore().consume(token)
    if not session:
        frappe.throw(
            _("انتهت صلاحية معاينة خطة القص أو تم استخدامها مسبقًا. أعد المعاينة ثم احفظ."),
            frappe.ValidationError,
        )
    if session.order_name != order.name or session.user != frappe.session.user:
        frappe.throw(_("معاينة خطة القص لا تخص هذا المستخدم أو الطلب."), frappe.PermissionError)

    repository = FrappeCuttingPlanCommandRepository(Capability.RECALCULATE_PLAN)
    plan = repository.latest_document(
        order.name,
        source_type=SYSTEM,
        status=DRAFT,
    )
    if not plan or plan.name != session.source_plan_name:
        frappe.throw(
            _("تغيّرت نسخة خطة القص بعد المعاينة. أعد المعاينة قبل الحفظ."),
            frappe.ValidationError,
        )
    if str(plan.modified or "") != session.source_plan_modified:
        frappe.throw(
            _("تم تعديل خطة القص بعد المعاينة. أعد المعاينة لحماية آخر التغييرات."),
            frappe.ValidationError,
        )

    initialize_draft_plan_cost_snapshot(order, plan)
    apply_exact_system_preview(
        order,
        plan,
        settings=session.settings,
        snapshot=session.snapshot,
        expected_input_fingerprint=session.input_fingerprint,
    )
    apply_plan_costs(plan, edge_cost_usd=flt(getattr(order, "edge_cost_usd", 0)))
    repository.save_document(plan)
    refresh_order_commercial_totals(order, plan)
    order.add_comment(
        "Info",
        text=_("تم حفظ معاينة خطة القص {0} بواسطة {1}.").format(
            plan.name,
            frappe.session.user,
        ),
    )

    result = plan_payload(plan, order)
    result["committed_preview_id"] = token
    result["exact_preview_commit"] = True
    return result


__all__ = ["commit_cutting_plan_preview", "preview_cutting_plan"]
