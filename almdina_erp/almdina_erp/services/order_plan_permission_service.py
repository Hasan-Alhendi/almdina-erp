from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import (
    require_stage_operational_access,
)
from almdina_erp.almdina_erp.services.order_edit_policy import (
    assert_order_editable,
    user_can_recalculate_drawing_system_plan,
)


_OPTIMIZER_FIELDS = (
    "packing_mode",
    "cutting_machine_type",
    "kerf_mm",
    "trim_margin_mm",
    "optimization_time_limit_sec",
)
_OPTIMIZER_DEFAULTS = {
    "packing_mode": "default_packing_mode",
    "cutting_machine_type": "default_cutting_machine_type",
    "kerf_mm": "default_kerf_mm",
    "trim_margin_mm": "default_trim_margin_mm",
    "optimization_time_limit_sec": "default_optimization_time_limit_sec",
}
_NUMERIC_PLAN_INPUT_FIELDS = frozenset(
    {"kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"}
)


def _capability_allowed(doc: Any, capability: str) -> bool:
    if getattr(doc, "is_new", lambda: False)():
        return doctype_has_capability(capability)
    return document_has_capability(doc, capability)


def _same_value(fieldname: str, left: Any, right: Any) -> bool:
    if fieldname in _NUMERIC_PLAN_INPUT_FIELDS:
        return abs(flt(left) - flt(right)) < 0.000001
    return str(left or "").strip() == str(right or "").strip()


def _optimizer_changes(doc: Any, old: Any | None) -> list[str]:
    if old:
        return [
            fieldname
            for fieldname in _OPTIMIZER_FIELDS
            if not _same_value(fieldname, doc.get(fieldname), old.get(fieldname))
        ]

    settings = frappe.get_single("Almdina ERP Settings")
    changes: list[str] = []
    for fieldname, default_field in _OPTIMIZER_DEFAULTS.items():
        current = doc.get(fieldname)
        if current in (None, ""):
            continue
        if not _same_value(fieldname, current, settings.get(default_field)):
            changes.append(fieldname)
    return changes


def _piece_key(row: Any, index: int) -> str:
    return str(row.get("name") or f"idx:{index}")


def _drawing_snapshot(row: Any | None) -> tuple[str, str, str]:
    """Return only meaningful drawing state, not normal-row default statuses."""

    if not row:
        return ("", "", "")
    drawing = str(row.get("special_shape_drawing_json") or "")
    geometry = str(row.get("special_shape_geometry_json") or "")
    raw_status = str(row.get("special_shape_status") or "")
    status = raw_status if drawing or geometry or raw_status == "Documented" else ""
    return (drawing, geometry, status)


def _drawing_changed(doc: Any, old: Any | None) -> bool:
    current_rows = list(doc.get("pieces") or [])
    old_rows = list(old.get("pieces") or []) if old else []
    old_by_key = {
        _piece_key(row, index): row
        for index, row in enumerate(old_rows, start=1)
    }
    current_keys: set[str] = set()

    for index, row in enumerate(current_rows, start=1):
        key = _piece_key(row, index)
        current_keys.add(key)
        previous = old_by_key.get(key)
        if _drawing_snapshot(row) != _drawing_snapshot(previous):
            return True

    for index, row in enumerate(old_rows, start=1):
        key = _piece_key(row, index)
        if key not in current_keys and any(_drawing_snapshot(row)):
            return True
    return False


def enforce_plan_and_drawing_permissions(doc: Any, method: str | None = None) -> None:
    """Protect capability-bound fields before any Door Cutting Order save.

    Standard ``write`` permission remains necessary for ordinary order edits, but
    it never grants optimizer or special-drawing authority implicitly. Focused
    plan commands may save with ``ignore_permissions`` only after the same
    capability checks have succeeded here.
    """

    del method
    old = None if doc.is_new() else doc.get_doc_before_save()

    optimizer_changed = False
    if not _capability_allowed(doc, Capability.EDIT_OPTIMIZER_SETTINGS):
        changed = _optimizer_changes(doc, old)
        if changed:
            frappe.throw(
                _(
                    "لا تملك صلاحية تعديل إعدادات محسن خطة القص. الحقول المحمية: {0}."
                ).format(", ".join(changed)),
                frappe.PermissionError,
            )
    else:
        optimizer_changed = bool(_optimizer_changes(doc, old))

    drawing_changed = False
    if not _capability_allowed(doc, Capability.EDIT_SPECIAL_DRAWING):
        if _drawing_changed(doc, old):
            frappe.throw(
                _("لا تملك صلاحية تعديل رسومات الدرف الخاصة."),
                frappe.PermissionError,
            )
    else:
        drawing_changed = _drawing_changed(doc, old)

    # Once the order has entered (or left) a production route, capability alone
    # is not enough: the actor must hold the current stage's operational role.
    if (optimizer_changed or drawing_changed) and (
        getattr(doc, "current_production_stage", None)
        or getattr(doc, "production_path", None)
    ):
        require_stage_operational_access(doc)


def _requested_optimizer_updates(
    *,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if packing_mode is not None:
        updates["packing_mode"] = str(packing_mode).strip()
    if cutting_machine_type is not None:
        updates["cutting_machine_type"] = str(cutting_machine_type).strip()
    if kerf_mm is not None:
        updates["kerf_mm"] = flt(kerf_mm)
    if trim_margin_mm is not None:
        updates["trim_margin_mm"] = flt(trim_margin_mm)
    if optimization_time_limit_sec is not None:
        updates["optimization_time_limit_sec"] = flt(optimization_time_limit_sec)
    return updates


def _apply_optimizer_updates(doc: Any, updates: dict[str, Any]) -> list[str]:
    changed = [
        fieldname
        for fieldname, value in updates.items()
        if not _same_value(fieldname, doc.get(fieldname), value)
    ]
    if not changed:
        return []

    optimizer_changed = [
        fieldname for fieldname in changed if fieldname in _OPTIMIZER_FIELDS
    ]
    if optimizer_changed:
        require_document_capability(
            doc,
            Capability.EDIT_OPTIMIZER_SETTINGS,
            message=_("لا تملك صلاحية تغيير خوارزمية أو إعدادات محسن خطة القص."),
        )
        if getattr(doc, "current_production_stage", None) or getattr(
            doc, "production_path", None
        ):
            require_stage_operational_access(doc)

    for fieldname in changed:
        doc.set(fieldname, updates[fieldname])
    return optimizer_changed


def _assert_recalculation_state(doc: Any) -> None:
    drawing_recalculation_allowed = user_can_recalculate_drawing_system_plan(doc)

    # Approval freezes the production snapshot, not Drawing's ability to prepare
    # an explicit replacement. Only the Drawing-stage exception may recalculate
    # while an approved plan exists; later production stages remain hard-locked.
    if getattr(doc, "approved_plan", None) and not drawing_recalculation_allowed:
        frappe.throw(
            _("خطة القص المعتمدة لا يمكن إعادة حسابها خارج مرحلة الرسم."),
            frappe.ValidationError,
        )

    # On a production route, recalculation is a stage-scoped mutation:
    # capability + current stage operational role (denied after the route ends).
    if getattr(doc, "current_production_stage", None) or getattr(
        doc, "production_path", None
    ):
        require_stage_operational_access(doc)
        return

    # Drawing-stage planners are intentionally allowed to recalculate through
    # the focused capability without receiving full EDIT_ORDER authority.
    if drawing_recalculation_allowed:
        return

    # Before production, keep the existing lifecycle boundary. This checks state,
    # not cost permissions, and does not require a full document write grant for
    # draft-like orders.
    assert_order_editable(doc)


def _recalculation_result(doc: Any) -> dict[str, Any]:
    """Return production-plan data only; financial data never crosses this API."""

    cutting_plan = getattr(doc, "cutting_plan_json", None) or ""
    system_plan = getattr(doc, "system_plan_json", None) or cutting_plan
    return {
        "name": doc.name,
        "required_boards": doc.required_boards,
        "waste_area_m2": doc.waste_area_m2,
        "waste_percent": doc.waste_percent,
        "packing_method": doc.packing_method,
        "packing_score": doc.packing_score,
        "total_area_m2": doc.total_area_m2,
        "total_edge_meters": doc.total_edge_meters,
        "packing_mode": doc.packing_mode,
        "cutting_machine_type": doc.cutting_machine_type,
        "kerf_mm": doc.kerf_mm,
        "trim_margin_mm": doc.trim_margin_mm,
        "optimization_time_limit_sec": doc.optimization_time_limit_sec,
        "plan_needs_recalculation": doc.plan_needs_recalculation,
        "cutting_plan_json": sanitize_plan_snapshot_json(cutting_plan),
        "system_plan_json": sanitize_plan_snapshot_json(system_plan),
        "approved_plan": doc.approved_plan,
        "approved_plan_source": doc.approved_plan_source,
    }


@frappe.whitelist()
def recalculate_order(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Recalculate one plan through granular plan capabilities only.

    ``RECALCULATE_PLAN`` authorizes running the engine. Changing packing mode,
    machine type, kerf, trim margin, or time limit additionally requires
    ``EDIT_OPTIMIZER_SETTINGS``. Neither operation requires cost visibility or
    cost editing authority.
    """

    name = str(order_name or "").strip()
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    doc = frappe.get_doc("Door Cutting Order", name)
    doc.check_permission("read")
    require_document_capability(
        doc,
        Capability.RECALCULATE_PLAN,
        message=_("لا تملك صلاحية إعادة حساب خطة القص لهذا الطلب."),
    )
    _assert_recalculation_state(doc)

    updates = _requested_optimizer_updates(
        packing_mode=packing_mode,
        cutting_machine_type=cutting_machine_type,
        kerf_mm=kerf_mm,
        trim_margin_mm=trim_margin_mm,
        optimization_time_limit_sec=optimization_time_limit_sec,
    )
    changed = _apply_optimizer_updates(doc, updates)

    doc.flags.force_cutting_plan_recalculation = True
    doc.save(ignore_permissions=True)
    doc.add_comment(
        "Info",
        text=_("تمت إعادة حساب خطة القص بواسطة {0}{1}.").format(
            frappe.session.user,
            _(" مع تحديث إعدادات المحسن") if changed else "",
        ),
    )
    return _recalculation_result(doc)


@frappe.whitelist()
def simulate_optimizer_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Run the engine on a throwaway copy and return the result without saving.

    Comparing algorithms is an inspection, not an edit, so this answers to
    ``EDIT_OPTIMIZER_SETTINGS`` alone: no stage operational role, no lifecycle
    state, and no approved-plan unlock. Nothing is persisted, which is what
    keeps the wide audience safe on live production orders.
    """

    name = str(order_name or "").strip()
    stored = frappe.get_doc("Door Cutting Order", name)
    stored.check_permission("read")
    require_document_capability(
        stored,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        message=_("لا تملك صلاحية تجربة خوارزمية القص على هذا الطلب."),
    )

    preview = frappe.copy_doc(stored)
    preview.name = stored.name
    for fieldname, value in _requested_optimizer_updates(
        packing_mode=packing_mode,
        cutting_machine_type=cutting_machine_type,
        kerf_mm=kerf_mm,
        trim_margin_mm=trim_margin_mm,
        optimization_time_limit_sec=optimization_time_limit_sec,
    ).items():
        preview.set(fieldname, value)

    settings = preview._get_settings()
    preview._calculate_piece_rows()
    preview._calculate_cutting_plan(
        settings,
        preview._plan_input_fingerprint(settings),
    )

    result = _recalculation_result(preview)
    result["is_preview"] = True
    return result


__all__ = [
    "enforce_plan_and_drawing_permissions",
    "recalculate_order",
    "simulate_optimizer_plan",
]
