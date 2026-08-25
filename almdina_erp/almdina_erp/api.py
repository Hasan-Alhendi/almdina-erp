from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.orders.editability import can_edit_order
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
    require_any_document_capability,
    require_doctype_capability,
    require_document_capability,
)


def _use_locked_preview(status: str) -> bool:
    # The persisted lifecycle state is authoritative. Only Draft is editable;
    # every later state renders the immutable approved/stored plan.
    return not can_edit_order(status)


def _board_ready_for_plan(preview: Any) -> bool:
    return bool(str(getattr(preview, "board_description", "") or "").strip())


def _prepare_text_board_preview(preview: Any) -> bool:
    """Prepare the free-text board snapshot without touching the Item master.

    Live preview runs automatically while a form is opened or partially edited.
    It must therefore never call the historical Item-based board loader, which
    requires the hidden ``board_item`` Link field and interrupts the operator with
    "Board Item is required.". Invalid or incomplete preview values simply mean
    that no layout is calculated yet; strict validation remains on Save.
    """

    description = str(getattr(preview, "board_description", "") or "").strip()
    if not description:
        return False

    raw_length = getattr(preview, "board_length_cm", None)
    raw_width = getattr(preview, "board_width_cm", None)
    length_cm = flt(244 if raw_length in (None, "") else raw_length)
    width_cm = flt(122 if raw_width in (None, "") else raw_width)
    trim_mm = flt(getattr(preview, "trim_margin_mm", 0))

    values = (length_cm, width_cm, trim_mm)
    if not all(math.isfinite(value) for value in values):
        return False
    if length_cm <= 0 or width_cm <= 0 or trim_mm < 0:
        return False

    full_length_mm = length_cm * 10
    full_width_mm = width_cm * 10
    if full_length_mm - (trim_mm * 2) <= 0:
        return False
    if full_width_mm - (trim_mm * 2) <= 0:
        return False

    preview.board_description = description
    preview.board_length_cm = length_cm
    preview.board_width_cm = width_cm
    preview.full_board_length_mm = full_length_mm
    preview.full_board_width_mm = full_width_mm

    # The legacy fingerprint builder still reads board_item. Keep this alias only
    # on the in-memory preview document; it is never returned or persisted.
    preview.board_item = description
    return True


def _can_view_preview_costs(document: Any | None = None) -> bool:
    """Resolve financial preview visibility from the canonical capability matrix."""

    if document is None:
        return doctype_has_capability(Capability.VIEW_COSTS)
    return document_has_capability(document, Capability.VIEW_COSTS)


def _serialize_order_preview(
    preview: Any,
    *,
    cutting_plan_json: str | None = None,
    include_financial: bool = False,
) -> dict[str, Any]:
    board_description = (
        str(getattr(preview, "board_description", "") or "").strip()
        or str(getattr(preview, "board_item", "") or "").strip()
    )

    pieces: list[dict[str, Any]] = []
    for row in (preview.pieces or []):
        piece = {
            "piece_no": row.piece_no,
            "area_m2": row.area_m2,
            "edge_meters": row.edge_meters,
            "special_shape_status": row.special_shape_status,
        }
        if include_financial:
            piece.update(
                {
                    "edge_rate_usd": row.edge_rate_usd,
                    "edge_cost_usd": row.edge_cost_usd,
                    "special_shape_estimated_unit_price_usd": row.special_shape_estimated_unit_price_usd,
                    "special_shape_custom_unit_price_usd": row.special_shape_custom_unit_price_usd,
                    "special_shape_final_unit_price_usd": row.special_shape_final_unit_price_usd,
                    "special_shape_price_status": row.special_shape_price_status,
                    "special_shape_price_note": row.special_shape_price_note,
                    "special_shape_price_approved_by": row.special_shape_price_approved_by,
                    "special_shape_price_approved_on": row.special_shape_price_approved_on,
                    "extra_double_unit_price_usd": getattr(row, "extra_double_unit_price_usd", 0),
                    "extra_double_total_usd": getattr(row, "extra_double_total_usd", 0),
                    "extra_liner_unit_price_usd": getattr(row, "extra_liner_unit_price_usd", 0),
                    "extra_liner_total_usd": getattr(row, "extra_liner_total_usd", 0),
                    "extra_recessed_handle_cutout_unit_price_usd": getattr(
                        row,
                        "extra_recessed_handle_cutout_unit_price_usd",
                        0,
                    ),
                    "extra_recessed_handle_cutout_total_usd": getattr(
                        row,
                        "extra_recessed_handle_cutout_total_usd",
                        0,
                    ),
                    "extra_addons_total_usd": getattr(row, "extra_addons_total_usd", 0),
                }
            )
        pieces.append(piece)

    selected_plan = (
        cutting_plan_json
        if cutting_plan_json is not None
        else getattr(preview, "cutting_plan_json", None)
    )
    system_plan = (
        getattr(preview, "system_plan_json", None)
        or getattr(preview, "cutting_plan_json", None)
        or ""
    )
    custom_plan = getattr(preview, "custom_plan_json", None) or ""

    payload: dict[str, Any] = {
        "board_description": board_description,
        "board_length_cm": flt(getattr(preview, "board_length_cm", 0)),
        "board_width_cm": flt(getattr(preview, "board_width_cm", 0)),
        "full_board_length_mm": preview.full_board_length_mm,
        "full_board_width_mm": preview.full_board_width_mm,
        "total_area_m2": preview.total_area_m2,
        "total_edge_meters": preview.total_edge_meters,
        "required_boards": preview.required_boards,
        "waste_area_m2": preview.waste_area_m2,
        "waste_percent": preview.waste_percent,
        "packing_method": preview.packing_method,
        "packing_score": preview.packing_score,
        "packing_mode": getattr(preview, "packing_mode", None),
        "engine_version": preview.engine_version,
        "cutting_plan_json": sanitize_plan_snapshot_json(selected_plan or ""),
        "system_plan_json": sanitize_plan_snapshot_json(system_plan),
        "custom_plan_json": sanitize_plan_snapshot_json(custom_plan),
        "approved_plan_source": getattr(preview, "approved_plan_source", None) or "System",
        "approved_plan": getattr(preview, "approved_plan", None),
        "pieces": pieces,
    }

    if include_financial:
        payload.update(
            {
                "mdf_cost_usd": preview.mdf_cost_usd,
                "cutting_cost_usd": preview.cutting_cost_usd,
                "edge_cost_usd": preview.edge_cost_usd,
                "total_cost_usd": preview.total_cost_usd,
                "special_shapes_baseline_cost_usd": preview.special_shapes_baseline_cost_usd,
                "special_shapes_estimated_total_usd": preview.special_shapes_estimated_total_usd,
                "special_shapes_final_total_usd": preview.special_shapes_final_total_usd,
                "extra_addons_total_usd": getattr(preview, "extra_addons_total_usd", 0),
                "customer_quote_total_usd": preview.customer_quote_total_usd,
                "customer_quote_status": preview.customer_quote_status,
            }
        )

    return payload


def _approved_order_plan_name(order_name: str) -> str | None:
    if not order_name or order_name.startswith("new-"):
        return None

    linked = frappe.db.get_value("Door Cutting Order", order_name, "approved_plan")
    if linked:
        valid = frappe.db.get_value(
            "Cutting Plan",
            linked,
            ["name", "status", "plan_kind"],
            as_dict=True,
        )
        if valid and valid.status == "Approved" and (valid.plan_kind or "Order") == "Order":
            return valid.name

    return frappe.db.get_value(
        "Cutting Plan",
        {
            "door_cutting_order": order_name,
            "status": "Approved",
            "plan_kind": "Order",
        },
        "name",
        order_by="revision desc, modified desc",
    )


def _approved_snapshot_for_order(order_name: str) -> str | None:
    plan_name = _approved_order_plan_name(order_name)
    if not plan_name:
        return None
    raw = frappe.db.get_value("Cutting Plan", plan_name, "snapshot_json")
    return sanitize_plan_snapshot_json(raw or "")


def _existing_preview_order(name: str) -> Any | None:
    if not name or name.startswith("new-"):
        return None
    # Never turn an attacker-supplied non-existent persistent name into an
    # unsaved document. get_doc fails closed if the record is absent.
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    return order


def _require_live_preview_access(order: Any | None) -> None:
    if order is None:
        require_doctype_capability(
            Capability.CREATE_ORDER,
            message=_("لا تملك صلاحية إنشاء طلب ومعاينته."),
        )
        return
    require_document_capability(
        order,
        Capability.EDIT_ORDER,
        message=_("لا تملك صلاحية تعديل هذا الطلب أو إعادة حساب معاينته."),
    )


@frappe.whitelist()
def preview_door_cutting_order(doc: str | dict[str, Any]) -> dict[str, Any]:
    """Preview authorized Draft edits; non-Draft orders render canonical approved plan only."""

    payload = frappe.parse_json(doc) if isinstance(doc, str) else dict(doc or {})
    payload["doctype"] = "Door Cutting Order"
    name = str(payload.get("name") or "").strip()
    stored = _existing_preview_order(name)

    # Security decisions use the persisted status, never the client payload.
    if stored is not None and _use_locked_preview(stored.status):
        approved_snapshot = _approved_snapshot_for_order(stored.name)
        return _serialize_order_preview(
            stored,
            cutting_plan_json=approved_snapshot or "",
            include_financial=_can_view_preview_costs(stored),
        )

    _require_live_preview_access(stored)
    preview = frappe.get_doc(payload)
    if stored is not None:
        preview._doc_before_save = stored

    # Preserve legacy live-calculation behaviour without invoking the strict
    # save-time input validator on partially entered rows.
    preview._set_piece_numbers()
    preview._validate_special_shape_rows()
    preview._calculate_piece_rows()

    has_complete_piece = any(
        flt(row.width_cm) > 0 and flt(row.length_cm) > 0 and cint(row.qty) > 0
        for row in (preview.pieces or [])
    )

    if _board_ready_for_plan(preview) and has_complete_piece and _prepare_text_board_preview(preview):
        settings = preview._get_settings()
        input_fingerprint = preview._plan_input_fingerprint(settings)
        preview._calculate_cutting_plan(settings, input_fingerprint)
    else:
        preview.required_boards = 0
        preview.mdf_cost_usd = 0
        preview.cutting_cost_usd = 0
        preview.total_cost_usd = flt(preview.edge_cost_usd)
        preview.special_shapes_baseline_cost_usd = 0
        preview.special_shapes_estimated_total_usd = 0
        preview.special_shapes_final_total_usd = 0
        preview.customer_quote_total_usd = preview.total_cost_usd
        preview.customer_quote_status = "Estimated" if any(
            (row.piece_type or "Regular") == "Special" for row in (preview.pieces or [])
        ) else "Automatic"
        preview.waste_area_m2 = 0
        preview.waste_percent = 0
        preview.packing_method = ""
        preview.packing_score = ""
        preview.engine_version = ""
        preview.cutting_plan_json = ""

    return _serialize_order_preview(
        preview,
        include_financial=_can_view_preview_costs(stored),
    )


@frappe.whitelist()
def get_approved_cutting_plan_snapshot(order_name: str) -> dict[str, Any]:
    """Return immutable non-financial Order Plan metadata to plan consumers."""

    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_any_document_capability(
        order,
        (
            Capability.VIEW_CUTTING_PLAN,
            Capability.VIEW_APPROVED_CUTTING_PLAN,
            Capability.PRINT_CUTTING_PLAN,
            Capability.EXPORT_DXF,
        ),
        message=_("لا تملك صلاحية الوصول إلى خطة القص المعتمدة لهذا الطلب."),
    )
    plan_name = _approved_order_plan_name(order_name)
    if not plan_name:
        return {
            "cutting_plan": None,
            "snapshot_json": "",
        }
    plan = frappe.get_doc("Cutting Plan", plan_name)
    return {
        "cutting_plan": plan.name,
        "revision": plan.revision,
        "approved_by": plan.approved_by,
        "approved_on": plan.approved_on,
        "engine_version": plan.engine_version,
        "snapshot_json": sanitize_plan_snapshot_json(plan.snapshot_json or ""),
    }
