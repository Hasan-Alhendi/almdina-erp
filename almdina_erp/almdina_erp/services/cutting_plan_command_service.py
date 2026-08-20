from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.application.cutting.plan_revisions import (
    PlanSettings,
    UpdatePlanSettingsCommand,
    update_settings,
)
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SUPERSEDED,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    COST_SNAPSHOT_VERSION,
    apply_plan_costs,
    initialize_draft_plan_cost_snapshot,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    apply_validated_dxf_snapshot,
    calculate_system_plan,
    plan_input_fingerprint,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_assignment_access import (
    require_stage_assignment_access,
)
from almdina_erp.almdina_erp.services.order_edit_policy import (
    assert_order_editable,
    user_can_recalculate_drawing_system_plan,
)


_DCO_TO_PLAN_FIELDS = {
    "packing_mode": "optimization_mode",
    "cutting_machine_type": "machine_type",
    "optimization_time_limit_sec": "optimization_time_limit_sec",
    "kerf_mm": "kerf_mm",
    "trim_margin_mm": "trim_margin_mm",
}
_NUMERIC_SETTING_FIELDS = frozenset(
    {"optimization_time_limit_sec", "kerf_mm", "trim_margin_mm"}
)
_DXF_COMMAND_CAPABILITIES = frozenset({Capability.UPLOAD_DXF, Capability.REPLACE_DXF})


def _settings_from_plan(plan: Any, updates: dict[str, Any] | None = None) -> PlanSettings:
    values = updates or {}

    def value(dco_field: str) -> Any:
        plan_field = _DCO_TO_PLAN_FIELDS[dco_field]
        if dco_field in values:
            return values[dco_field]
        return getattr(plan, plan_field, None)

    return PlanSettings(
        optimization_mode=str(value("packing_mode") or "Auto Pro"),
        machine_type=str(value("cutting_machine_type") or "Auto"),
        optimization_time_limit_sec=flt(value("optimization_time_limit_sec")) or 10,
        kerf_mm=flt(value("kerf_mm")),
        trim_margin_mm=flt(value("trim_margin_mm")),
    )


def _same_value(fieldname: str, left: Any, right: Any) -> bool:
    if fieldname in _NUMERIC_SETTING_FIELDS:
        return abs(flt(left) - flt(right)) < 0.000001
    return str(left or "").strip() == str(right or "").strip()


def _changed_settings(plan: Any, updates: dict[str, Any]) -> list[str]:
    return [
        fieldname
        for fieldname, value in updates.items()
        if fieldname in _DCO_TO_PLAN_FIELDS
        and not _same_value(
            fieldname,
            getattr(plan, _DCO_TO_PLAN_FIELDS[fieldname], None),
            value,
        )
    ]


def _requested_updates(
    *,
    packing_mode: str | None,
    cutting_machine_type: str | None,
    kerf_mm: float | None,
    trim_margin_mm: float | None,
    optimization_time_limit_sec: float | None,
) -> dict[str, Any]:
    raw = {
        "packing_mode": packing_mode,
        "cutting_machine_type": cutting_machine_type,
        "kerf_mm": kerf_mm,
        "trim_margin_mm": trim_margin_mm,
        "optimization_time_limit_sec": optimization_time_limit_sec,
    }
    updates: dict[str, Any] = {}
    for fieldname, value in raw.items():
        if value is None:
            continue
        if fieldname in _NUMERIC_SETTING_FIELDS:
            try:
                normalized = float(value)
            except (TypeError, ValueError):
                frappe.throw(
                    _("إحدى قيم إعدادات خطة القص غير صالحة."),
                    frappe.ValidationError,
                )
            if normalized < 0:
                frappe.throw(
                    _("لا يمكن أن تكون إعدادات خطة القص الرقمية سالبة."),
                    frappe.ValidationError,
                )
            updates[fieldname] = flt(normalized)
        else:
            normalized = str(value or "").strip()
            if not normalized:
                frappe.throw(
                    _("يجب تحديد قيمة صالحة لإعدادات خطة القص."),
                    frappe.ValidationError,
                )
            updates[fieldname] = normalized
    return updates


def _assert_recalculation_state(order: Any) -> None:
    drawing_recalculation_allowed = user_can_recalculate_drawing_system_plan(order)

    if getattr(order, "approved_plan", None) and not drawing_recalculation_allowed:
        frappe.throw(
            _("خطة القص المعتمدة لا يمكن إعادة حسابها خارج مرحلة الرسم."),
            frappe.ValidationError,
        )

    if getattr(order, "current_production_stage", None) or getattr(
        order, "production_path", None
    ):
        require_stage_assignment_access(order)
        return

    if drawing_recalculation_allowed:
        return

    assert_order_editable(order)


def _set_drawing_dxf_status(order: Any, status: str) -> None:
    """Persist only the DCO-owned drawing workflow signal, never Plan data."""

    meta = frappe.get_meta("Door Cutting Order")
    if not meta.has_field("drawing_dxf_status"):
        return
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "drawing_dxf_status",
        status,
        update_modified=False,
    )
    order.drawing_dxf_status = status


def _set_approved_plan_relation(order: Any, plan: Any) -> None:
    """Persist the real aggregate relation without mirroring Plan snapshot state."""

    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "approved_plan",
        plan.name,
        update_modified=False,
    )
    order.approved_plan = plan.name
    if str(plan.source_type or SYSTEM) == UPLOADED_DXF:
        _set_drawing_dxf_status(order, "Approved by Drawing")


def _legacy_plan_source(source_type: str) -> str:
    return "Custom" if source_type == UPLOADED_DXF else "System"


def _canonical_plan_source(plan_source: str) -> str:
    normalized = str(plan_source or "System").strip().lower()
    if normalized == "system":
        return SYSTEM
    if normalized in {"custom", "uploaded dxf", "uploaded_dxf", "dxf"}:
        return UPLOADED_DXF
    frappe.throw(_("مصدر خطة القص المحدد غير مدعوم."), frappe.ValidationError)
    raise AssertionError("unreachable")


def _assert_plan_ready_for_approval(order: Any, plan: Any) -> None:
    if str(plan.status or "") != DRAFT:
        frappe.throw(_("يمكن اعتماد خطة قص في حالة المسودة فقط."), frappe.ValidationError)
    if str(plan.validation_status or "") != "Valid" or not str(plan.snapshot_json or "").strip():
        frappe.throw(
            _("خطة القص غير موجودة أو لم تنجح في التحقق الهندسي."),
            frappe.ValidationError,
        )
    if cint(plan.plan_needs_recalculation):
        frappe.throw(
            _("خطة القص قديمة. أعد حسابها أو ارفع DXF جديدًا ثم راجع النتيجة قبل الاعتماد."),
            frappe.ValidationError,
        )
    if cint(getattr(plan, "cost_snapshot_version", 0)) < COST_SNAPSHOT_VERSION:
        frappe.throw(
            _("تكلفة خطة القص قديمة. حدّث الخطة أو احفظ إعدادات التكلفة ثم راجع النتيجة قبل الاعتماد."),
            frappe.ValidationError,
        )

    expected_fingerprint = plan_input_fingerprint(order, plan)
    if not str(plan.input_fingerprint or "").strip() or plan.input_fingerprint != expected_fingerprint:
        frappe.throw(
            _("خطة القص لم تعد مطابقة لبيانات الطلب الحالية. حدّث الخطة ثم اعتمدها."),
            frappe.ValidationError,
        )

    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    if snapshot.get("unplaced"):
        settings = frappe.get_single("Almdina ERP Settings")
        if not cint(settings.allow_unplaced_approval):
            frappe.throw(
                _("خطة القص تحتوي قطعًا غير موضوعة ولا يمكن اعتمادها."),
                frappe.ValidationError,
            )

    if str(plan.source_type or SYSTEM) == UPLOADED_DXF:
        if not str(plan.dxf_file or "").strip() or str(plan.dxf_status or "") != "Validated":
            frappe.throw(
                _("ارفع ملف DXF صالحًا وتحقق منه قبل اعتماد الخطة."),
                frappe.ValidationError,
            )


def plan_payload(plan: Any, order: Any | None = None) -> dict[str, Any]:
    snapshot_json = str(plan.snapshot_json or "")
    payload = {
        "name": getattr(order, "name", None) or plan.door_cutting_order,
        "cutting_plan": plan.name,
        "plan_revision": int(plan.revision or 0),
        "plan_status": str(plan.status or ""),
        "plan_source_type": str(plan.source_type or ""),
        "required_boards": plan.required_boards,
        "waste_area_m2": plan.waste_area_m2,
        "waste_percent": plan.waste_percent,
        "packing_method": plan.method_label,
        "packing_score": (
            f"ألواح: {int(plan.required_boards or 0)} | "
            f"هدر: {flt(plan.waste_percent):.2f}% | "
            f"الخوارزمية: {plan.method_label or plan.optimization_mode or ''}"
        ),
        "packing_mode": plan.optimization_mode,
        "cutting_machine_type": plan.machine_type,
        "kerf_mm": plan.kerf_mm,
        "trim_margin_mm": plan.trim_margin_mm,
        "optimization_time_limit_sec": plan.optimization_time_limit_sec,
        "plan_needs_recalculation": int(plan.plan_needs_recalculation or 0),
        "cutting_plan_json": sanitize_plan_snapshot_json(snapshot_json),
        "system_plan_json": sanitize_plan_snapshot_json(snapshot_json),
    }
    if order is not None:
        payload["total_area_m2"] = getattr(order, "total_area_m2", 0)
        payload["total_edge_meters"] = getattr(order, "total_edge_meters", 0)
        approved_plan = getattr(order, "approved_plan", None)
        payload["approved_plan"] = approved_plan
        payload["approved_plan_source"] = (
            _legacy_plan_source(str(plan.source_type or SYSTEM))
            if approved_plan == plan.name
            else getattr(order, "approved_plan_source", None)
        )
    return payload


def current_uploaded_dxf_file(order_name: str) -> str:
    repository = FrappeCuttingPlanCommandRepository(Capability.UPLOAD_DXF)
    plan = repository.latest_document(
        order_name,
        source_type=UPLOADED_DXF,
        status=DRAFT,
    )
    return str(getattr(plan, "dxf_file", None) or "") if plan else ""


def save_uploaded_dxf_plan(
    order: Any,
    snapshot: dict[str, Any],
    file_url: str,
    *,
    capability: str,
) -> Any:
    if capability not in _DXF_COMMAND_CAPABILITIES:
        frappe.throw(
            _("صلاحية رفع DXF غير صالحة لهذا الأمر."),
            frappe.PermissionError,
        )
    require_cutting_plan_capability(
        order,
        capability,
        message=_("لا تملك صلاحية رفع أو استبدال DXF لهذا الطلب."),
    )

    repository = FrappeCuttingPlanCommandRepository(capability)
    plan = repository.ensure_uploaded_dxf_draft(order)
    initialize_draft_plan_cost_snapshot(order, plan)
    apply_validated_dxf_snapshot(order, plan, snapshot)
    apply_plan_costs(plan, edge_cost_usd=flt(getattr(order, "edge_cost_usd", 0)))
    plan.dxf_file = str(file_url or "").strip()
    plan.dxf_status = "Validated"
    plan.dxf_uploaded_by = frappe.session.user
    plan.dxf_uploaded_on = now_datetime()
    repository.save_document(plan)
    return plan


def finalize_uploaded_dxf_order_state(order: Any, plan: Any) -> None:
    """Refresh only order-owned state after canonical DXF Plan persistence."""

    _set_drawing_dxf_status(order, "Uploaded")
    refresh_order_commercial_totals(order, plan)


def approve_order_plan(order: Any, plan_source: str) -> dict[str, Any]:
    """Approve the reviewed Draft Cutting Plan without recalculation or DCO save."""

    require_cutting_plan_capability(
        order,
        Capability.APPROVE_DXF,
        message=_("لا تملك صلاحية اعتماد خطة القص لهذا الطلب."),
    )
    source_type = _canonical_plan_source(plan_source)
    repository = FrappeCuttingPlanCommandRepository(Capability.APPROVE_DXF)
    plan = repository.latest_document(
        order.name,
        source_type=source_type,
        status=DRAFT,
    )
    if not plan:
        message = (
            _("لا توجد خطة قص من النظام جاهزة للاعتماد. أعد حساب الخطة أولًا.")
            if source_type == SYSTEM
            else _("لا توجد خطة DXF صالحة جاهزة للاعتماد. ارفع DXF أولًا.")
        )
        frappe.throw(message, frappe.ValidationError)

    _assert_plan_ready_for_approval(order, plan)
    order.ensure_special_shapes_documented()
    order.ensure_special_prices_approved()

    for previous in repository.approved_documents(order.name, exclude=plan.name):
        previous.status = SUPERSEDED
        repository.save_document(previous, allow_status_transition=True)

    plan.status = APPROVED
    plan.approved_by = frappe.session.user
    plan.approved_on = now_datetime()
    repository.save_document(plan, allow_status_transition=True)
    _set_approved_plan_relation(order, plan)
    refresh_order_commercial_totals(order, plan)

    return {
        "name": order.name,
        "status": "Approved",
        "cutting_plan": plan.name,
        "revision": cint(plan.revision),
        "approved_plan_source": _legacy_plan_source(source_type),
    }


def save_system_plan_settings(
    order: Any,
    updates: dict[str, Any],
) -> dict[str, Any]:
    require_cutting_plan_capability(
        order,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        message=_("لا تملك صلاحية تعديل إعدادات خطة القص لهذا الطلب."),
    )
    repository = FrappeCuttingPlanCommandRepository(Capability.EDIT_OPTIMIZER_SETTINGS)
    plan = repository.ensure_system_draft(order)
    changed = _changed_settings(plan, updates)
    if changed:
        update_settings(
            UpdatePlanSettingsCommand(
                plan_name=plan.name,
                settings=_settings_from_plan(plan, updates),
            ),
            repository,
        )
        plan = repository.get_document(plan.name)
    result = plan_payload(plan, order)
    result["changed_fields"] = changed
    return result


def recalculate_system_plan(
    order: Any,
    updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_cutting_plan_capability(
        order,
        Capability.RECALCULATE_PLAN,
        message=_("لا تملك صلاحية إعادة حساب خطة القص لهذا الطلب."),
    )
    repository = FrappeCuttingPlanCommandRepository(Capability.RECALCULATE_PLAN)
    plan = repository.ensure_system_draft(order)
    initialize_draft_plan_cost_snapshot(order, plan)
    changed = _changed_settings(plan, updates or {})
    if changed:
        require_cutting_plan_capability(
            order,
            Capability.EDIT_OPTIMIZER_SETTINGS,
            message=_("لا تملك صلاحية تغيير خوارزمية أو إعدادات محسن خطة القص."),
        )
        edit_repository = FrappeCuttingPlanCommandRepository(
            Capability.EDIT_OPTIMIZER_SETTINGS
        )
        update_settings(
            UpdatePlanSettingsCommand(
                plan_name=plan.name,
                settings=_settings_from_plan(plan, updates),
            ),
            edit_repository,
        )
        plan = repository.get_document(plan.name)
        initialize_draft_plan_cost_snapshot(order, plan)

    calculate_system_plan(order, plan)
    apply_plan_costs(plan, edge_cost_usd=flt(getattr(order, "edge_cost_usd", 0)))
    repository.save_document(plan)
    refresh_order_commercial_totals(order, plan)
    result = plan_payload(plan, order)
    result["changed_fields"] = changed
    return result


@frappe.whitelist()
def recalculate_order_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Canonical plan-owned replacement for the legacy DCO recalculation save."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_cutting_plan_capability(
        order,
        Capability.RECALCULATE_PLAN,
        message=_("لا تملك صلاحية إعادة حساب خطة القص لهذا الطلب."),
    )
    _assert_recalculation_state(order)

    result = recalculate_system_plan(
        order,
        _requested_updates(
            packing_mode=packing_mode,
            cutting_machine_type=cutting_machine_type,
            kerf_mm=kerf_mm,
            trim_margin_mm=trim_margin_mm,
            optimization_time_limit_sec=optimization_time_limit_sec,
        ),
    )
    order.add_comment(
        "Info",
        text=_("تمت إعادة حساب خطة القص {0} بواسطة {1}.").format(
            result.get("cutting_plan") or "",
            frappe.session.user,
        ),
    )
    return result


__all__ = [
    "approve_order_plan",
    "current_uploaded_dxf_file",
    "finalize_uploaded_dxf_order_state",
    "plan_payload",
    "recalculate_order_plan",
    "recalculate_system_plan",
    "save_system_plan_settings",
    "save_uploaded_dxf_plan",
]
