from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt, now_datetime


def create_mini_plan(order: Any, replacement: Any, snapshot: dict[str, Any], remnant: Any | None) -> Any:
    existing = frappe.db.get_value(
        "Cutting Plan",
        {"replacement_piece": replacement.name, "status": "Approved"},
        "name",
    )
    if existing:
        return frappe.get_doc("Cutting Plan", existing)

    from almdina_erp.almdina_erp.services.replacement_service import (
        _edge_meters,
        _edge_rate,
        _remnant_material_cost,
    )

    edge_meters = _edge_meters(replacement)
    edge_cost = edge_meters * _edge_rate(replacement.edge_type)
    material_cost = (
        _remnant_material_cost(order, flt(snapshot["used_area_m2"]))
        if remnant
        else flt(order.board_rate_usd)
    )
    # Zero is a valid explicit approved cost. Never coerce it back to baseline 1.
    cutting_cost = flt(order.cutting_cost_per_board_usd)
    planned_total = material_cost + cutting_cost + edge_cost

    source = snapshot["sheets"][0]
    plan = frappe.new_doc("Cutting Plan")
    plan.plan_kind = "Replacement"
    plan.door_cutting_order = order.name
    plan.replacement_piece = replacement.name
    plan.revision = 1
    plan.status = "Draft"
    plan.method_key = snapshot["method_key"]
    plan.method_label = snapshot["method_label"]
    plan.score = flt(snapshot["score"])
    plan.engine_version = snapshot["engine_version"]
    # The DocType validator independently derives Valid/Invalid on insert.
    plan.validation_status = "Pending"
    plan.validation_errors = ""
    plan.board_item = replacement.board_item
    plan.full_board_width_mm = flt(source["full_width_cm"]) * 10
    plan.full_board_length_mm = flt(source["full_length_cm"]) * 10
    plan.usable_board_width_mm = flt(source["usable_width_cm"]) * 10
    plan.usable_board_length_mm = flt(source["usable_length_cm"]) * 10
    plan.kerf_mm = flt(order.kerf_mm)
    plan.trim_margin_mm = flt(order.trim_margin_mm)
    plan.required_boards = cint(snapshot["required_full_boards"])
    plan.used_area_m2 = flt(snapshot["used_area_m2"])
    plan.total_source_area_m2 = flt(snapshot["total_board_area_m2"])
    plan.waste_area_m2 = flt(snapshot["waste_area_m2"])
    plan.waste_percent = (
        flt(plan.waste_area_m2) / flt(plan.total_source_area_m2) * 100
        if flt(plan.total_source_area_m2)
        else 0
    )
    plan.board_rate_usd = flt(order.board_rate_usd)
    plan.cutting_cost_per_board_usd = flt(order.cutting_cost_per_board_usd)
    plan.mdf_cost_usd = material_cost
    plan.cutting_cost_usd = cutting_cost
    plan.edge_cost_usd = edge_cost
    plan.total_cost_usd = planned_total
    plan.snapshot_json = frappe.as_json(snapshot)

    plan.append(
        "sources",
        {
            "sheet_no": 1,
            "source_type": source["source_type"],
            "board_item": replacement.board_item,
            "remnant": source.get("remnant"),
            "material": source.get("material") or order.board_material or "",
            "color": source.get("color") or order.board_color or "",
            "thickness_mm": flt(source.get("thickness_mm") or order.board_thickness_mm),
            "full_width_mm": flt(source["full_width_cm"]) * 10,
            "full_length_mm": flt(source["full_length_cm"]) * 10,
            "usable_width_mm": flt(source["usable_width_cm"]) * 10,
            "usable_length_mm": flt(source["usable_length_cm"]) * 10,
            "source_area_m2": flt(source["source_area_m2"]),
            "used_area_m2": flt(snapshot["used_area_m2"]),
            "waste_area_m2": flt(snapshot["waste_area_m2"]),
        },
    )

    piece = source["pieces"][0]
    plan.append(
        "placed_pieces",
        {
            "sheet_no": 1,
            "piece_id": 1,
            "piece_label": piece["label"],
            "source_piece_no": 1,
            "copy_no": 1,
            "x_mm": flt(piece["x"]) * 10,
            "y_mm": flt(piece["y"]) * 10,
            "width_mm": flt(piece["w"]) * 10,
            "height_mm": flt(piece["h"]) * 10,
            "original_width_cm": flt(piece["original_w"]),
            "original_length_cm": flt(piece["original_h"]),
            "rotated": cint(piece["rotated"]),
            "edge_long_right": cint(piece["edge_long_right"]),
            "edge_long_left": cint(piece["edge_long_left"]),
            "edge_width_top": cint(piece["edge_width_top"]),
            "edge_width_bottom": cint(piece["edge_width_bottom"]),
            "edge_type": piece.get("edge_type") or "",
            "notes": piece.get("notes") or "",
        },
    )

    plan.insert(ignore_permissions=True)
    if plan.validation_status != "Valid":
        frappe.throw("Replacement Mini Cutting Plan did not pass independent validation.")

    plan.flags.allow_status_transition = True
    plan.status = "Approved"
    plan.approved_by = frappe.session.user
    plan.approved_on = now_datetime()
    plan.save(ignore_permissions=True)
    return plan
