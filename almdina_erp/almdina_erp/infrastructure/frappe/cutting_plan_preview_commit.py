from __future__ import annotations

from typing import Any, Mapping

import frappe
from frappe import _

from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_workspace


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
    geometry snapshot.
    """

    for setting_name, plan_field in _SETTING_TO_PLAN_FIELD.items():
        if setting_name in settings:
            setattr(plan, plan_field, settings[setting_name])

    live_fingerprint = cutting_plan_workspace.plan_input_fingerprint(order, plan)
    if not expected_input_fingerprint or live_fingerprint != expected_input_fingerprint:
        frappe.throw(
            _(
                "تغيّرت بيانات الطلب أو إعدادات الخطة بعد إنشاء المعاينة. "
                "أعد معاينة الخطة قبل الحفظ."
            ),
            frappe.ValidationError,
        )

    # This module is the persistence adapter paired with cutting_plan_workspace;
    # using its single snapshot mapper keeps preview commit byte-for-byte aligned
    # with normal System-plan projection without duplicating geometry mapping.
    cutting_plan_workspace._apply_snapshot(  # noqa: SLF001
        order,
        plan,
        dict(snapshot),
        fingerprint=live_fingerprint,
    )


__all__ = ["apply_exact_system_preview"]
