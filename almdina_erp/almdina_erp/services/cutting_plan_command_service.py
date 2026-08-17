from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from almdina_erp.almdina_erp.application.cutting.plan_revisions import (
    PlanSettings,
    UpdatePlanSettingsCommand,
    update_settings,
)
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    calculate_system_plan,
)


_DCO_TO_PLAN_FIELDS = {
    "packing_mode": "optimization_mode",
    "cutting_machine_type": "machine_type",
    "optimization_time_limit_sec": "optimization_time_limit_sec",
    "kerf_mm": "kerf_mm",
    "trim_margin_mm": "trim_margin_mm",
}


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
    if fieldname in {"kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"}:
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


def _set_order_projection(order: Any, plan: Any, *, include_snapshot: bool) -> None:
    """Maintain the legacy DCO UI as a read projection during A2 migration.

    Cutting Plan remains authoritative. These fields exist only so the current
    Door Cutting Order form can keep rendering until A4/A5 remove the legacy
    plan fields from the order UI.
    """

    values: dict[str, Any] = {
        "packing_mode": plan.optimization_mode,
        "cutting_machine_type": plan.machine_type,
        "optimization_time_limit_sec": plan.optimization_time_limit_sec,
        "kerf_mm": plan.kerf_mm,
        "trim_margin_mm": plan.trim_margin_mm,
        "plan_needs_recalculation": int(plan.plan_needs_recalculation or 0),
    }
    if include_snapshot:
        snapshot_json = str(plan.snapshot_json or "")
        values.update(
            {
                "required_boards": plan.required_boards,
                "waste_area_m2": plan.waste_area_m2,
                "waste_percent": plan.waste_percent,
                "packing_method": plan.method_label,
                "packing_score": (
                    f"ألواح: {int(plan.required_boards or 0)} | "
                    f"هدر: {flt(plan.waste_percent):.2f}% | "
                    f"الخوارزمية: {plan.method_label or plan.optimization_mode or ''}"
                ),
                "engine_version": plan.engine_version,
                "calculated_plan_input_hash": plan.input_fingerprint,
                "calculated_plan_metadata_hash": plan.metadata_fingerprint or "",
                "cutting_plan_json": snapshot_json,
                "system_plan_json": snapshot_json,
            }
        )

    meta = frappe.get_meta("Door Cutting Order")
    values = {key: value for key, value in values.items() if meta.has_field(key)}
    if values:
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            values,
            update_modified=False,
        )
        for fieldname, value in values.items():
            setattr(order, fieldname, value)


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
        payload["approved_plan"] = getattr(order, "approved_plan", None)
        payload["approved_plan_source"] = getattr(order, "approved_plan_source", None)
    return payload


def save_system_plan_settings(
    order: Any,
    updates: dict[str, Any],
) -> dict[str, Any]:
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
    _set_order_projection(order, plan, include_snapshot=False)
    result = plan_payload(plan, order)
    result["changed_fields"] = changed
    return result


def recalculate_system_plan(
    order: Any,
    updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repository = FrappeCuttingPlanCommandRepository(Capability.RECALCULATE_PLAN)
    plan = repository.ensure_system_draft(order)
    changed = _changed_settings(plan, updates or {})
    if changed:
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

    calculate_system_plan(order, plan)
    repository.save_document(plan)
    _set_order_projection(order, plan, include_snapshot=True)
    result = plan_payload(plan, order)
    result["changed_fields"] = changed
    return result


__all__ = [
    "plan_payload",
    "recalculate_system_plan",
    "save_system_plan_settings",
]
