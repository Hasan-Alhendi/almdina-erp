from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.services import export_validation_service as legacy_export


def _require_export_access(
    *,
    order_name: str | None,
    payload: dict[str, Any] | None,
) -> Any | None:
    """Authorize before geometry or plan data is loaded."""

    if order_name:
        order = frappe.get_doc("Door Cutting Order", order_name)
        require_document_capability(
            order,
            Capability.EXPORT_DXF,
            message=_("You do not have permission to export this order as DXF."),
        )
        return order

    name = str((payload or {}).get("name") or "").strip()
    if name and frappe.db.exists("Door Cutting Order", name):
        order = frappe.get_doc("Door Cutting Order", name)
        require_document_capability(
            order,
            Capability.EXPORT_DXF,
            message=_("You do not have permission to export this order as DXF."),
        )
        return order

    require_doctype_capability(
        Capability.EXPORT_DXF,
        message=_("You do not have permission to export an unsaved order as DXF."),
    )
    return None


def _approved_plan_manifest(order: Any, plan: Any) -> dict[str, Any]:
    return {
        "order": order.name,
        "customer": order.customer,
        "revision": cint(plan.revision),
        "cutting_plan": plan.name,
        "plan_kind": plan.plan_kind or "Order",
        "units": "mm",
        "engine_version": plan.engine_version,
        "method_key": plan.method_key,
        "method_label": plan.method_label,
        "sheet_count": len(plan.sources or []),
        "sources": [
            {
                "sheet_no": int(row.sheet_no),
                "source_type": row.source_type,
                "remnant": row.remnant,
                "board_item": row.board_item,
                "material": row.material or "",
                "color": row.color or "",
                "thickness_mm": flt(row.thickness_mm),
                "full_width_mm": flt(row.full_width_mm),
                "full_length_mm": flt(row.full_length_mm),
                "usable_width_mm": flt(row.usable_width_mm),
                "usable_length_mm": flt(row.usable_length_mm),
            }
            for row in (plan.sources or [])
        ],
    }


def _draft_manifest(order: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "order": order.name or "UNSAVED",
        "customer": order.customer,
        "revision": cint(order.revision or 1),
        "cutting_plan": None,
        "plan_kind": "Draft Preview",
        "units": "mm",
        "engine_version": snapshot.get("engine_version"),
        "method_key": snapshot.get("method_key"),
        "method_label": snapshot.get("method_label"),
        "sheet_count": len(snapshot.get("sheets") or []),
        "sources": [
            {
                "sheet_no": int(sheet.get("sheet_no") or index + 1),
                "source_type": sheet.get("source_type") or "Full Board",
                "remnant": sheet.get("remnant"),
                "board_item": order.board_item,
                "material": sheet.get("material") or order.board_material or "",
                "color": sheet.get("color") or order.board_color or "",
                "thickness_mm": flt(
                    sheet.get("thickness_mm") or order.board_thickness_mm
                ),
                "full_width_mm": flt(sheet.get("full_width_cm")) * 10,
                "full_length_mm": flt(sheet.get("full_length_cm")) * 10,
                "usable_width_mm": flt(sheet.get("usable_width_cm")) * 10,
                "usable_length_mm": flt(sheet.get("usable_length_cm")) * 10,
            }
            for index, sheet in enumerate(snapshot.get("sheets") or [])
        ],
    }


@frappe.whitelist()
def get_validated_dxf_plan(
    order_name: str | None = None,
    doc: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return validated geometry only after configurable document authorization."""

    payload = None
    if doc is not None:
        payload = frappe.parse_json(doc) if isinstance(doc, str) else dict(doc or {})
        if not isinstance(payload, dict):
            frappe.throw(_("Editable DXF export requires a valid order payload."))

    order = _require_export_access(order_name=order_name, payload=payload)

    if order_name and order:
        if order.approved_plan:
            plan = frappe.get_doc("Cutting Plan", order.approved_plan)
            errors = legacy_export.validate_cutting_plan_document(plan)
            if errors:
                frappe.throw(
                    _("DXF export blocked by geometry validation:\n{0}").format(
                        "\n".join(errors)
                    )
                )
            return {
                "plan": legacy_export._plan_to_export_snapshot(plan),
                "manifest": _approved_plan_manifest(order, plan),
            }

        snapshot = legacy_export._stored_order_export_snapshot(order)
        return {
            "plan": snapshot,
            "manifest": legacy_export._manifest_from_order_snapshot(
                order,
                snapshot,
                plan_kind="System Plan",
            ),
        }

    if payload is None:
        frappe.throw(
            _(
                "Editable DXF export requires the current Door Cutting Order "
                "document payload."
            )
        )

    editable, snapshot = legacy_export._strict_editable_snapshot(payload)
    return {
        "plan": snapshot,
        "manifest": _draft_manifest(editable, snapshot),
    }


__all__ = ["get_validated_dxf_plan"]
