from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway


DXF_ROLES = ("عامل رسم", "Production Manager", "System Manager")


def _assert_order_at_drawing(order_name: str) -> None:
    from almdina_erp.almdina_erp.services.order_edit_policy import (
        is_order_at_drawing_stage,
    )

    row = frappe.db.get_value(
        "Door Cutting Order",
        order_name,
        ["name", "status", "production_path", "current_production_stage"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Order not found."))
    if not is_order_at_drawing_stage(row):
        frappe.throw(
            _("DXF actions are only available while the order is at Drawing.")
        )


@frappe.whitelist()
def mark_dxf_exported(order_name: str) -> dict[str, Any]:
    shop_floor_gateway.require_roles(*DXF_ROLES)
    _assert_order_at_drawing(order_name)
    current = (
        frappe.db.get_value(
            "Door Cutting Order",
            order_name,
            "drawing_dxf_status",
        )
        or "None"
    )
    if current in {"None", "Exported"}:
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            "drawing_dxf_status",
            "Exported",
            update_modified=True,
        )
    return {
        "name": order_name,
        "drawing_dxf_status": frappe.db.get_value(
            "Door Cutting Order",
            order_name,
            "drawing_dxf_status",
        ),
    }


@frappe.whitelist()
def upload_production_dxf(order_name: str, file_url: str) -> dict[str, Any]:
    shop_floor_gateway.require_roles(*DXF_ROLES)
    _assert_order_at_drawing(order_name)
    if not file_url:
        frappe.throw(_("Attach a DXF file."))
    if not str(file_url).lower().endswith(".dxf"):
        frappe.throw(_("Production file must be a .dxf attachment."))

    order = shop_floor_gateway.get_order(order_name)
    from almdina_erp.almdina_erp.services.dxf_import_service import (
        parse_production_dxf,
        validate_imported_plan,
    )

    custom_snapshot = parse_production_dxf(file_url, order)
    validation = validate_imported_plan(custom_snapshot, order)
    if not validation.get("is_valid"):
        frappe.throw(
            _("Imported DXF plan is invalid:\n{0}").format(
                "\n".join(validation.get("errors") or [])
            )
        )

    from almdina_erp.almdina_erp.services.dual_plan_fields import (
        has_dual_plan_field,
    )

    update_values: dict[str, Any] = {
        "production_dxf": file_url,
        "drawing_dxf_status": "Uploaded",
    }
    if has_dual_plan_field("custom_plan_json"):
        update_values["custom_plan_json"] = frappe.as_json(custom_snapshot)
    frappe.db.set_value(
        "Door Cutting Order",
        order_name,
        update_values,
        update_modified=True,
    )
    return {
        "name": order_name,
        "production_dxf": file_url,
        "drawing_dxf_status": "Uploaded",
        "custom_plan_json": frappe.as_json(custom_snapshot),
    }


@frappe.whitelist()
def recalculate_drawing_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
) -> dict[str, Any]:
    """Recalculate the system plan without granting full order-edit access."""

    shop_floor_gateway.require_roles(*DXF_ROLES)
    _assert_order_at_drawing(order_name)
    order = shop_floor_gateway.get_order(order_name)
    order.check_permission("read")
    if order.approved_plan:
        frappe.throw(_("This order already has a locked cutting plan."))

    if packing_mode:
        order.packing_mode = packing_mode
    if cutting_machine_type:
        order.cutting_machine_type = cutting_machine_type
    if kerf_mm is not None:
        order.kerf_mm = kerf_mm
    if trim_margin_mm is not None:
        order.trim_margin_mm = trim_margin_mm

    order.flags.force_cutting_plan_recalculation = True
    order.save(ignore_permissions=True)

    from almdina_erp.almdina_erp.api import _serialize_order_preview

    return _serialize_order_preview(order)


@frappe.whitelist()
def approve_production_dxf(order_name: str) -> dict[str, Any]:
    shop_floor_gateway.require_roles(*DXF_ROLES)
    _assert_order_at_drawing(order_name)
    from almdina_erp.almdina_erp.services.cutting_plan_service import (
        lock_cutting_plan,
    )

    return lock_cutting_plan(order_name, plan_source="Custom")


__all__ = [
    "approve_production_dxf",
    "mark_dxf_exported",
    "recalculate_drawing_plan",
    "upload_production_dxf",
]
