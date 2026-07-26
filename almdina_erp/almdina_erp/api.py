from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt


EDITABLE_ORDER_STATES = {"Draft", "Pending Review", "Rejected"}


def _serialize_order_preview(preview: Any, *, cutting_plan_json: str | None = None) -> dict[str, Any]:
    return {
        "board_material": preview.board_material,
        "board_color": preview.board_color,
        "board_thickness_mm": preview.board_thickness_mm,
        "full_board_length_mm": preview.full_board_length_mm,
        "full_board_width_mm": preview.full_board_width_mm,
        "total_area_m2": preview.total_area_m2,
        "total_edge_meters": preview.total_edge_meters,
        "required_boards": preview.required_boards,
        "waste_area_m2": preview.waste_area_m2,
        "waste_percent": preview.waste_percent,
        "mdf_cost_usd": preview.mdf_cost_usd,
        "cutting_cost_usd": preview.cutting_cost_usd,
        "edge_cost_usd": preview.edge_cost_usd,
        "total_cost_usd": preview.total_cost_usd,
        "special_shapes_baseline_cost_usd": preview.special_shapes_baseline_cost_usd,
        "special_shapes_estimated_total_usd": preview.special_shapes_estimated_total_usd,
        "special_shapes_final_total_usd": preview.special_shapes_final_total_usd,
        "customer_quote_total_usd": preview.customer_quote_total_usd,
        "customer_quote_status": preview.customer_quote_status,
        "packing_method": preview.packing_method,
        "packing_score": preview.packing_score,
        "engine_version": preview.engine_version,
        "cutting_plan_json": cutting_plan_json if cutting_plan_json is not None else preview.cutting_plan_json,
        "pieces": [
            {
                "piece_no": row.piece_no,
                "area_m2": row.area_m2,
                "edge_meters": row.edge_meters,
                "edge_rate_usd": row.edge_rate_usd,
                "edge_cost_usd": row.edge_cost_usd,
                "special_shape_status": row.special_shape_status,
                "special_shape_estimated_unit_price_usd": row.special_shape_estimated_unit_price_usd,
                "special_shape_custom_unit_price_usd": row.special_shape_custom_unit_price_usd,
                "special_shape_final_unit_price_usd": row.special_shape_final_unit_price_usd,
                "special_shape_price_status": row.special_shape_price_status,
                "special_shape_price_note": row.special_shape_price_note,
                "special_shape_price_approved_by": row.special_shape_price_approved_by,
                "special_shape_price_approved_on": row.special_shape_price_approved_on,
            }
            for row in (preview.pieces or [])
        ],
    }


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
    return frappe.db.get_value("Cutting Plan", plan_name, "snapshot_json")


@frappe.whitelist()
def preview_door_cutting_order(doc: str | dict[str, Any]) -> dict[str, Any]:
    """Calculate an editable order without saving; locked orders use the Approved Order Snapshot."""

    payload = frappe.parse_json(doc) if isinstance(doc, str) else dict(doc or {})
    payload["doctype"] = "Door Cutting Order"

    status = payload.get("status") or "Draft"
    name = payload.get("name") or ""

    # Once approved, never regenerate a historical production plan from the
    # current engine. Replacement Mini Plans are intentionally excluded: the
    # order's linked immutable Order Plan is the only rendering/printing source.
    if status not in EDITABLE_ORDER_STATES and name and not name.startswith("new-"):
        stored = frappe.get_doc("Door Cutting Order", name)
        stored.check_permission("read")
        approved_snapshot = _approved_snapshot_for_order(name)
        return _serialize_order_preview(
            stored,
            cutting_plan_json=approved_snapshot or stored.cutting_plan_json,
        )

    preview = frappe.get_doc(payload)
    if name and not name.startswith("new-") and frappe.db.exists("Door Cutting Order", name):
        stored = frappe.get_doc("Door Cutting Order", name)
        stored.check_permission("read")
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

    if preview.board_item and has_complete_piece:
        preview._load_board_snapshot()

        # The high-performance save refactor made plan calculation explicit and
        # requires the cached settings plus a deterministic input fingerprint.
        # Preview is an explicit calculation path, so provide both arguments
        # instead of calling the old no-argument method signature.
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

    return _serialize_order_preview(preview)


@frappe.whitelist()
def get_approved_cutting_plan_snapshot(order_name: str) -> dict[str, Any]:
    """Return immutable Order Plan metadata used by official print/DXF consumers."""
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    plan_name = _approved_order_plan_name(order_name)
    if not plan_name:
        return {"cutting_plan": None, "snapshot_json": order.cutting_plan_json}
    plan = frappe.get_doc("Cutting Plan", plan_name)
    return {
        "cutting_plan": plan.name,
        "revision": plan.revision,
        "approved_by": plan.approved_by,
        "approved_on": plan.approved_on,
        "engine_version": plan.engine_version,
        "snapshot_json": plan.snapshot_json,
    }
