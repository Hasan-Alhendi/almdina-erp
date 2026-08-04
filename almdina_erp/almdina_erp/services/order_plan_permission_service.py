from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.services.order_edit_policy import assert_order_editable


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
_NUMERIC_OPTIMIZER_FIELDS = frozenset(
    {"kerf_mm", "trim_margin_mm", "optimization_time_limit_sec"}
)


def _capability_allowed(doc: Any, capability: str) -> bool:
    if getattr(doc, "is_new", lambda: False)():
        return doctype_has_capability(capability)
    return document_has_capability(doc, capability)


def _same_value(fieldname: str, left: Any, right: Any) -> bool:
    if fieldname in _NUMERIC_OPTIMIZER_FIELDS:
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
    it no longer grants optimizer or special-drawing authority implicitly.
    """

    del method
    old = None if doc.is_new() else doc.get_doc_before_save()

    if not _capability_allowed(doc, Capability.EDIT_OPTIMIZER_SETTINGS):
        changed = _optimizer_changes(doc, old)
        if changed:
            frappe.throw(
                _(
                    "You do not have permission to edit cutting-plan optimizer settings. "
                    "Protected fields: {0}."
                ).format(", ".join(changed)),
                frappe.PermissionError,
            )

    if not _capability_allowed(doc, Capability.EDIT_SPECIAL_DRAWING):
        if _drawing_changed(doc, old):
            frappe.throw(
                _("You do not have permission to edit special-door drawings."),
                frappe.PermissionError,
            )


def _recalculation_result(doc: Any) -> dict[str, Any]:
    return {
        "name": doc.name,
        "required_boards": doc.required_boards,
        "waste_area_m2": doc.waste_area_m2,
        "waste_percent": doc.waste_percent,
        "packing_method": doc.packing_method,
        "packing_score": doc.packing_score,
        "total_area_m2": doc.total_area_m2,
        "total_edge_meters": doc.total_edge_meters,
        "mdf_cost_usd": doc.mdf_cost_usd,
        "cutting_cost_usd": doc.cutting_cost_usd,
        "edge_cost_usd": doc.edge_cost_usd,
        "total_cost_usd": doc.total_cost_usd,
        "special_shapes_baseline_cost_usd": doc.special_shapes_baseline_cost_usd,
        "special_shapes_estimated_total_usd": doc.special_shapes_estimated_total_usd,
        "special_shapes_final_total_usd": doc.special_shapes_final_total_usd,
        "customer_quote_total_usd": doc.customer_quote_total_usd,
        "customer_quote_status": doc.customer_quote_status,
        "plan_needs_recalculation": doc.plan_needs_recalculation,
        "cutting_plan_json": doc.cutting_plan_json,
    }


@frappe.whitelist()
def recalculate_order(order_name: str) -> dict[str, Any]:
    """Run the optimizer only after explicit document capability authorization."""

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
        message=_("You do not have permission to recalculate this cutting plan."),
    )
    assert_order_editable(doc)
    doc.flags.force_cutting_plan_recalculation = True
    doc.save(ignore_permissions=True)
    doc.add_comment(
        "Info",
        text=_("Cutting plan recalculated by {0}.").format(frappe.session.user),
    )
    return _recalculation_result(doc)


__all__ = [
    "enforce_plan_and_drawing_permissions",
    "recalculate_order",
]
