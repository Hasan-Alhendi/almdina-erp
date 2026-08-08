from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.security.drawing_action_policy import (
    DrawingActionDenied,
    DrawingActionState,
    required_upload_capability,
    validate_assigned_drawing_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)

MAX_DXF_FILE_SIZE = 10 * 1024 * 1024

_POLICY_MESSAGES = {
    "not_at_drawing": "DXF actions are only available while the order is at Drawing.",
    "designer_not_assigned": "Assign a designer to this order before using drawing actions.",
    "not_assigned_designer": "Only the designer assigned to this order can perform this drawing action.",
    "plan_already_approved": "This order already has a locked cutting plan.",
}


def _drawing_state(order: Any) -> DrawingActionState:
    return DrawingActionState(
        status=str(order.status or ""),
        production_path=str(order.production_path or ""),
        current_department=str(order.current_department or ""),
        current_assignee=str(order.current_assignee or ""),
        session_user=str(frappe.session.user or ""),
        approved_plan=str(order.approved_plan or ""),
        production_dxf=str(order.production_dxf or ""),
    )


def _throw_policy_error(error: DrawingActionDenied) -> None:
    frappe.throw(
        _(_POLICY_MESSAGES.get(error.code, "Drawing action is not allowed.")),
        frappe.PermissionError,
    )


def _get_authorized_order(
    order_name: str,
    capability: str,
    *,
    require_unlocked_plan: bool = True,
) -> Any:
    order = shop_floor_gateway.get_order(order_name)
    order.check_permission("read")
    require_document_capability(order, capability)
    try:
        validate_assigned_drawing_action(
            _drawing_state(order),
            require_unlocked_plan=require_unlocked_plan,
        )
    except DrawingActionDenied as error:
        _throw_policy_error(error)
    return order


def _validate_and_attach_dxf_file(order: Any, file_url: str) -> Any:
    normalized_url = str(file_url or "").strip()
    if not normalized_url:
        frappe.throw(_("Attach a DXF file."))
    if not normalized_url.lower().split("?", 1)[0].endswith(".dxf"):
        frappe.throw(_("Production file must be a .dxf attachment."))

    file_row = frappe.db.get_value(
        "File",
        {"file_url": normalized_url},
        [
            "name",
            "file_size",
            "is_private",
            "attached_to_doctype",
            "attached_to_name",
        ],
        as_dict=True,
    )
    if not file_row:
        frappe.throw(_("The uploaded DXF file could not be found."))
    if int(file_row.file_size or 0) > MAX_DXF_FILE_SIZE:
        frappe.throw(_("DXF file size cannot exceed 10 MB."))
    if file_row.attached_to_doctype and (
        file_row.attached_to_doctype != order.doctype
        or file_row.attached_to_name != order.name
    ):
        frappe.throw(_("The uploaded DXF file belongs to another document."))

    frappe.db.set_value(
        "File",
        file_row.name,
        {
            "is_private": 1,
            "attached_to_doctype": order.doctype,
            "attached_to_name": order.name,
            "attached_to_field": "production_dxf",
        },
        update_modified=False,
    )
    return file_row


@frappe.whitelist()
def mark_dxf_exported(order_name: str) -> dict[str, Any]:
    order = _get_authorized_order(order_name, Capability.EXPORT_DXF)
    current = order.drawing_dxf_status or "None"
    if current in {"None", "Exported"}:
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            "drawing_dxf_status",
            "Exported",
            update_modified=True,
        )
    return {
        "name": order.name,
        "drawing_dxf_status": frappe.db.get_value(
            "Door Cutting Order",
            order.name,
            "drawing_dxf_status",
        ),
    }


@frappe.whitelist()
def upload_production_dxf(order_name: str, file_url: str) -> dict[str, Any]:
    order = shop_floor_gateway.get_order(order_name)
    upload_capability = required_upload_capability(_drawing_state(order))
    order = _get_authorized_order(order_name, upload_capability)
    replacing_existing_file = bool(order.production_dxf)
    _validate_and_attach_dxf_file(order, file_url)

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
        order.name,
        update_values,
        update_modified=True,
    )
    order.add_comment(
        "Info",
        text=_("DXF file {0} by assigned designer {1}.").format(
            _("replaced") if replacing_existing_file else _("uploaded"),
            frappe.session.user,
        ),
    )
    return {
        "name": order.name,
        "production_dxf": file_url,
        "drawing_dxf_status": "Uploaded",
        "custom_plan_json": frappe.as_json(custom_snapshot),
        "required_capability": upload_capability,
    }


@frappe.whitelist()
def recalculate_drawing_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Compatibility facade for the canonical focused cutting-plan command."""

    from almdina_erp.almdina_erp.services.order_plan_permission_service import (
        recalculate_order,
    )

    return recalculate_order(
        order_name=order_name,
        packing_mode=packing_mode,
        cutting_machine_type=cutting_machine_type,
        kerf_mm=kerf_mm,
        trim_margin_mm=trim_margin_mm,
        optimization_time_limit_sec=optimization_time_limit_sec,
    )


@frappe.whitelist()
def approve_production_dxf(
    order_name: str,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Compatibility facade for the focused role-managed approval service."""

    from almdina_erp.almdina_erp.services.drawing_approval_service import (
        approve_production_dxf as approve_drawing_plan,
    )

    return approve_drawing_plan(order_name=order_name, plan_source=plan_source)


__all__ = [
    "approve_production_dxf",
    "mark_dxf_exported",
    "recalculate_drawing_plan",
    "upload_production_dxf",
]
