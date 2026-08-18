from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.orders.editability import DRAFT_LIKE_STATUSES
from almdina_erp.almdina_erp.domain.orders.lifecycle import SHOP_FLOOR_ORDER_STATUSES
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
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
_NUMERIC_FIELDS = frozenset(
    {"kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"}
)
_SELECT_FIELDS = frozenset({"packing_mode", "cutting_machine_type"})
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


def _assert_edit_lifecycle(doc: Any) -> None:
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


def _number(value: Any, field_label: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        frappe.throw(
            _("القيمة المدخلة في «{0}» غير صالحة.").format(field_label),
            frappe.ValidationError,
        )
    if normalized < 0:
        frappe.throw(
            _("لا يمكن أن تكون قيمة «{0}» سالبة.").format(field_label),
            frappe.ValidationError,
        )
    return flt(normalized)


def _canonical_field(meta: Any, workspace_fieldname: str) -> Any:
    canonical = _PLAN_META_FIELDS[workspace_fieldname]
    return meta.get_field(canonical) if meta else None


def _allowed_select_values(meta: Any, workspace_fieldname: str) -> set[str]:
    field = _canonical_field(meta, workspace_fieldname)
    return {
        line.strip()
        for line in str(getattr(field, "options", "") or "").splitlines()
        if line.strip()
    }


def _normalize_updates(values: dict[str, Any]) -> dict[str, Any]:
    """Validate workspace aliases against the canonical Cutting Plan schema."""

    plan_meta = frappe.get_meta("Cutting Plan")
    updates: dict[str, Any] = {}
    for fieldname in PLAN_SETTING_FIELDS:
        if fieldname not in values or values[fieldname] is None:
            continue

        field = _canonical_field(plan_meta, fieldname)
        label = str(getattr(field, "label", None) or fieldname)
        value = values[fieldname]

        if fieldname in _NUMERIC_FIELDS:
            updates[fieldname] = _number(value, label)
            continue

        normalized = str(value or "").strip()
        if not normalized:
            frappe.throw(
                _("يجب تحديد قيمة «{0}».").format(label),
                frappe.ValidationError,
            )
        if fieldname in _SELECT_FIELDS:
            allowed = _allowed_select_values(plan_meta, fieldname)
            if not allowed or normalized not in allowed:
                frappe.throw(
                    _("القيمة المحددة في «{0}» غير معتمدة.").format(label),
                    frappe.ValidationError,
                )
        updates[fieldname] = normalized
    return updates


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
    _assert_edit_lifecycle(doc)

    updates = _normalize_updates(
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


__all__ = ["PLAN_SETTING_FIELDS", "save_plan_settings"]
