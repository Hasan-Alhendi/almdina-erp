from __future__ import annotations

from typing import Any, Mapping

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    OptimizationOutcome,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    apply_calculation_outcome,
    plan_input_fingerprint,
)


_SETTING_TO_PLAN_FIELD = {
    "packing_mode": "optimization_mode",
    "cutting_machine_type": "machine_type",
    "kerf_mm": "kerf_mm",
    "trim_margin_mm": "trim_margin_mm",
    "optimization_time_limit_sec": "optimization_time_limit_sec",
}


def apply_exact_system_preview(
    order: Any,
    plan: Any,
    *,
    settings: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    expected_input_fingerprint: str,
) -> None:
    """Project one trusted preview onto a canonical System Draft exactly once.

    No optimizer is invoked here. The input fingerprint is recomputed after the
    preview settings are applied, so a changed order cannot accept an old
    geometry snapshot. Projection reuses the public calculation-outcome port,
    keeping this adapter independent from private workspace implementation APIs.
    """

    for setting_name, plan_field in _SETTING_TO_PLAN_FIELD.items():
        if setting_name in settings:
            setattr(plan, plan_field, settings[setting_name])

    live_fingerprint = plan_input_fingerprint(order, plan)
    if not expected_input_fingerprint or live_fingerprint != expected_input_fingerprint:
        frappe.throw(
            _(
                "تغيّرت بيانات الطلب أو إعدادات الخطة بعد إنشاء المعاينة. "
                "أعد معاينة الخطة قبل الحفظ."
            ),
            frappe.ValidationError,
        )

    trusted_snapshot = dict(snapshot)
    validation = trusted_snapshot.get("validation") or {}
    if not trusted_snapshot.get("sheets") or not validation.get("is_valid"):
        frappe.throw(
            _("المعاينة الحالية لم تنجح في التحقق الهندسي ولا يمكن حفظها."),
            frappe.ValidationError,
        )

    apply_calculation_outcome(
        order,
        plan,
        OptimizationOutcome(
            snapshot=trusted_snapshot,
            packing_score="",
            required_boards=len(trusted_snapshot.get("sheets") or []),
            method_label=str(trusted_snapshot.get("method_label") or ""),
            expanded_pieces=(),
        ),
        fingerprint=live_fingerprint,
    )


__all__ = ["apply_exact_system_preview"]
