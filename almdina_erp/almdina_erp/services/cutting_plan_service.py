from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime


def require_any_role(*roles: str) -> None:
    user_roles = set(frappe.get_roles())
    if "System Manager" in user_roles:
        return
    if not user_roles.intersection(roles):
        frappe.throw(_("You do not have permission for this operation."), frappe.PermissionError)


def create_plan_from_order(order: Any) -> Any:
    """Persist the authoritative current order result as an immutable revision snapshot."""

    snapshot = frappe.parse_json(order.cutting_plan_json or "{}") or {}
    validation = snapshot.get("validation") or {}
    unplaced = snapshot.get("unplaced") or []

    if not snapshot.get("sheets"):
        frappe.throw(_("The order does not have a cutting plan to snapshot."))
    if not validation.get("is_valid"):
        frappe.throw(_("The cutting plan failed geometry validation and cannot be approved."))
    if unplaced:
        settings = frappe.get_single("Almdina ERP Settings")
        if not settings.allow_unplaced_approval:
            frappe.throw(_("The cutting plan contains unplaced pieces and cannot be approved."))

    revision = max(1, cint(order.revision))
    full_width_mm = flt(snapshot.get("full_board_width_cm")) * 10
    full_length_mm = flt(snapshot.get("full_board_length_cm")) * 10
    usable_width_mm = flt(snapshot.get("usable_board_width_cm")) * 10
    usable_length_mm = flt(snapshot.get("usable_board_length_cm")) * 10
    total_source_area = flt(snapshot.get("total_board_area_m2"))
    waste_area = flt(snapshot.get("waste_area_m2"))
    waste_percent = (waste_area / total_source_area * 100) if total_source_area else 0

    plan = frappe.new_doc("Cutting Plan")
    plan.door_cutting_order = order.name
    plan.revision = revision
    plan.status = "Draft"
    plan.method_key = snapshot.get("method_key") or ""
    plan.method_label = snapshot.get("method_label") or order.packing_method or ""
    plan.score = flt(snapshot.get("score"))
    plan.engine_version = snapshot.get("engine_version") or order.engine_version or ""
    plan.validation_status = "Valid" if validation.get("is_valid") else "Invalid"
    plan.validation_errors = "\n".join(validation.get("errors") or [])
    plan.board_item = order.board_item
    plan.full_board_width_mm = full_width_mm
    plan.full_board_length_mm = full_length_mm
    plan.usable_board_width_mm = usable_width_mm
    plan.usable_board_length_mm = usable_length_mm
    plan.kerf_mm = flt(order.kerf_mm)
    plan.trim_margin_mm = flt(order.trim_margin_mm)
    plan.required_boards = len(snapshot.get("sheets") or [])
    plan.used_area_m2 = flt(snapshot.get("used_area_m2"))
    plan.total_source_area_m2 = total_source_area
    plan.waste_area_m2 = waste_area
    plan.waste_percent = waste_percent
    plan.snapshot_json = frappe.as_json(snapshot)

    piece_groups = list(order.pieces or [])

    for sheet in snapshot.get("sheets") or []:
        sheet_pieces = sheet.get("pieces") or []
        used_area = sum(flt(piece.get("area_m2")) for piece in sheet_pieces)
        source_area = (usable_width_mm * usable_length_mm) / 1_000_000
        plan.append(
            "sources",
            {
                "sheet_no": sheet.get("sheet_no"),
                "source_type": "Full Board",
                "board_item": order.board_item,
                "full_width_mm": full_width_mm,
                "full_length_mm": full_length_mm,
                "usable_width_mm": usable_width_mm,
                "usable_length_mm": usable_length_mm,
                "source_area_m2": source_area,
                "used_area_m2": used_area,
                "waste_area_m2": max(0, source_area - used_area),
            },
        )

        for piece in sheet_pieces:
            source_no = int(piece.get("source_piece_no") or 0)
            source_row = piece_groups[source_no - 1] if 0 < source_no <= len(piece_groups) else None
            effective_edge_type = ""
            if source_row:
                effective_edge_type = source_row.edge_type or order.default_edge_type or ""

            plan.append(
                "placed_pieces",
                {
                    "sheet_no": sheet.get("sheet_no"),
                    "piece_id": piece.get("id"),
                    "piece_label": piece.get("label"),
                    "source_piece_no": source_no,
                    "copy_no": piece.get("copy_no"),
                    "x_mm": flt(piece.get("x")) * 10,
                    "y_mm": flt(piece.get("y")) * 10,
                    "width_mm": flt(piece.get("w")) * 10,
                    "height_mm": flt(piece.get("h")) * 10,
                    "original_width_cm": flt(piece.get("original_w")),
                    "original_length_cm": flt(piece.get("original_h")),
                    "rotated": 1 if piece.get("rotated") else 0,
                    "edge_long_right": 1 if piece.get("edge_long_right") else 0,
                    "edge_long_left": 1 if piece.get("edge_long_left") else 0,
                    "edge_width_top": 1 if piece.get("edge_width_top") else 0,
                    "edge_width_bottom": 1 if piece.get("edge_width_bottom") else 0,
                    "edge_type": effective_edge_type,
                    "notes": piece.get("notes") or "",
                },
            )

    plan.insert(ignore_permissions=True)
    return plan


def approve_plan(plan: Any) -> Any:
    if plan.status != "Draft":
        frappe.throw(_("Only Draft cutting plans can be approved."))
    if plan.validation_status != "Valid":
        frappe.throw(_("Only a geometrically valid cutting plan can be approved."))

    old_approved = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": plan.door_cutting_order,
            "status": "Approved",
            "name": ["!=", plan.name],
        },
        pluck="name",
    )
    for old_name in old_approved:
        old_plan = frappe.get_doc("Cutting Plan", old_name)
        old_plan.flags.allow_status_transition = True
        old_plan.status = "Superseded"
        old_plan.save(ignore_permissions=True)

    plan.flags.allow_status_transition = True
    plan.status = "Approved"
    plan.approved_by = frappe.session.user
    plan.approved_on = now_datetime()
    plan.save(ignore_permissions=True)
    return plan


@frappe.whitelist()
def submit_order_for_review(order_name: str) -> dict[str, Any]:
    require_any_role("Order Entry", "Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("write")
    if order.status not in {"Draft", "Rejected"}:
        frappe.throw(_("Only Draft or Rejected orders can be sent for review."))

    if order.status == "Rejected":
        order.revision = max(1, cint(order.revision)) + 1
    else:
        order.revision = max(1, cint(order.revision))

    order.status = "Pending Review"
    order.save()
    return {"name": order.name, "status": order.status, "revision": order.revision}


@frappe.whitelist()
def approve_order(order_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    if order.status != "Pending Review":
        frappe.throw(_("Only orders in Pending Review can be approved."))

    order.save(ignore_permissions=True)
    plan = create_plan_from_order(order)
    approve_plan(plan)

    from almdina_erp.almdina_erp.services.stock_service import validate_stock_for_order

    validate_stock_for_order(order.name, throw_on_shortage=True)

    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        {"status": "Approved", "approved_plan": plan.name},
        update_modified=True,
    )

    from almdina_erp.almdina_erp.services.production_service import ensure_default_stages

    ensure_default_stages(order.name, approved_by=frappe.session.user)

    return {
        "name": order.name,
        "status": "Approved",
        "cutting_plan": plan.name,
        "revision": plan.revision,
    }


@frappe.whitelist()
def reject_order(order_name: str, reason: str | None = None) -> dict[str, Any]:
    require_any_role("Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    if order.status != "Pending Review":
        frappe.throw(_("Only orders in Pending Review can be rejected."))

    frappe.db.set_value("Door Cutting Order", order.name, "status", "Rejected", update_modified=True)
    if reason:
        order.add_comment("Comment", text=_("Review rejection reason: {0}").format(reason))
    return {"name": order.name, "status": "Rejected", "revision": order.revision}
