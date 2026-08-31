from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    PlanSettingsValidationError,
    canonical_default_plan_settings,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.orders.editability import DRAFT_LIKE_STATUSES
from almdina_erp.almdina_erp.domain.orders.lifecycle import SHOP_FLOOR_ORDER_STATUSES
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.optimization_mode_validation import (
    require_executable_optimization_mode,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_assignment_access import (
    require_stage_assignment_access,
)
from almdina_erp.almdina_erp.services.order_edit_policy import is_order_at_drawing_stage


PLAN_SETTING_FIELDS = (
    "packing_mode",
    "cutting_machine_type",
    "kerf_mm",
    "trim_margin_mm",
    "optimization_time_limit_sec",
)
_PLAN_META_FIELDS = {
    "packing_mode": "optimization_mode",
    "cutting_machine_type": "machine_type",
    "kerf_mm": "kerf_mm",
    "trim_margin_mm": "trim_margin_mm",
    "optimization_time_limit_sec": "optimization_time_limit_sec",
}
_ACTIVE_ROUTED_ORDER_STATUSES = frozenset(SHOP_FLOOR_ORDER_STATUSES.values())


def _has_active_production_stage(doc: Any) -> bool:
    return bool(str(getattr(doc, "current_production_stage", None) or "").strip())


def _has_production_route(doc: Any) -> bool:
    return bool(
        _has_active_production_stage(doc)
        or str(getattr(doc, "production_path", None) or "").strip()
    )


def _has_active_routed_lifecycle(doc: Any) -> bool:
    if _has_active_production_stage(doc):
        return True
    status = str(getattr(doc, "status", None) or "").strip()
    return status in _ACTIVE_ROUTED_ORDER_STATUSES


def assert_plan_settings_edit_lifecycle(doc: Any) -> None:
    """Keep focused plan editing inside the plan-settings lifecycle boundary."""

    if int(getattr(doc, "docstatus", 0) or 0) != 0:
        frappe.throw(
            _("لا يمكن تعديل إعدادات خطة القص بعد اعتماد المستند."),
            frappe.ValidationError,
        )
    if str(getattr(doc, "revision_state", "Current") or "Current") == "Superseded":
        frappe.throw(
            _("لا يمكن تعديل إعدادات خطة القص في نسخة طلب مستبدلة."),
            frappe.ValidationError,
        )

    if getattr(doc, "approved_plan", None) and not is_order_at_drawing_stage(doc):
        frappe.throw(
            _("خطة القص المعتمدة لا يمكن تعديل إعداداتها خارج مرحلة الرسم."),
            frappe.ValidationError,
        )

    if _has_production_route(doc):
        if _has_active_routed_lifecycle(doc):
            return
        frappe.throw(
            _("انتهى المسار الإنتاجي الحالي ولا يمكن تعديل إعدادات خطة القص."),
            frappe.PermissionError,
        )

    status = str(getattr(doc, "status", None) or "Draft").strip()
    if status not in DRAFT_LIKE_STATUSES:
        frappe.throw(
            _("حالة الطلب الحالية لا تسمح بتعديل إعدادات خطة القص."),
            frappe.PermissionError,
        )


def _canonical_field(meta: Any, workspace_fieldname: str) -> Any:
    canonical = _PLAN_META_FIELDS[workspace_fieldname]
    return meta.get_field(canonical) if meta else None


def normalize_plan_settings_updates(values: dict[str, Any]) -> dict[str, Any]:
    """Validate a partial edit through the canonical Domain PlanSettings contract.

    Frappe metadata is consulted only for the field mapping/presentation boundary;
    Select options and metadata constraints never act as business-rule authority.
    Defaults fill fields omitted from this patch only and are never returned as
    updates, so an explicit numeric zero remains zero.
    """

    provided = {
        fieldname: values[fieldname]
        for fieldname in PLAN_SETTING_FIELDS
        if fieldname in values and values[fieldname] is not None
    }
    if not provided:
        return {}

    # A known but non-executable ID remains a valid persisted historical value,
    # but an explicit user/API selection must fail closed before metadata or DB
    # mutation. Legacy low-level modes with real implementations stay compatible.
    if "packing_mode" in provided:
        require_executable_optimization_mode(provided["packing_mode"])

    plan_meta = frappe.get_meta("Cutting Plan")
    for fieldname in provided:
        _canonical_field(plan_meta, fieldname)

    defaults = canonical_default_plan_settings()
    try:
        normalized = normalize_plan_settings(
            optimization_mode=provided.get(
                "packing_mode",
                defaults.optimization_mode,
            ),
            machine_type=provided.get(
                "cutting_machine_type",
                defaults.machine_type,
            ),
            optimization_time_limit_sec=provided.get(
                "optimization_time_limit_sec",
                defaults.optimization_time_limit_sec,
            ),
            kerf_mm=provided.get("kerf_mm", defaults.kerf_mm),
            preferred_trim_mm=provided.get(
                "trim_margin_mm",
                defaults.preferred_trim_mm,
            ),
        )
    except PlanSettingsValidationError:
        frappe.throw(
            _("إحدى قيم إعدادات خطة القص غير صالحة."),
            frappe.ValidationError,
        )
        raise AssertionError("unreachable")

    canonical_values = {
        "packing_mode": normalized.optimization_mode,
        "cutting_machine_type": normalized.machine_type,
        "optimization_time_limit_sec": normalized.optimization_time_limit_sec,
        "kerf_mm": normalized.kerf_mm,
        "trim_margin_mm": normalized.preferred_trim_mm,
    }
    return {fieldname: canonical_values[fieldname] for fieldname in provided}


@frappe.whitelist()
def save_plan_settings(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Persist optimizer settings on the canonical Draft Cutting Plan."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    doc = frappe.get_doc("Door Cutting Order", name)
    doc.check_permission("read")
    require_cutting_plan_capability(
        doc,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        message=_("لا تملك صلاحية تعديل إعدادات خطة القص لهذا الطلب."),
    )
    require_stage_assignment_access(doc)
    assert_plan_settings_edit_lifecycle(doc)

    updates = normalize_plan_settings_updates(
        {
            "packing_mode": packing_mode,
            "cutting_machine_type": cutting_machine_type,
            "kerf_mm": kerf_mm,
            "trim_margin_mm": trim_margin_mm,
            "optimization_time_limit_sec": optimization_time_limit_sec,
        },
    )

    from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
        save_system_plan_settings,
    )

    return save_system_plan_settings(doc, updates)


__all__ = [
    "PLAN_SETTING_FIELDS",
    "assert_plan_settings_edit_lifecycle",
    "normalize_plan_settings_updates",
    "save_plan_settings",
]
