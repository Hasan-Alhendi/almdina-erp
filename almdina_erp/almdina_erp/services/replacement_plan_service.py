from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.domain.replacements.planning import (
    calculate_edge_meters,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    approved_plan_for_order,
    plan_settings,
)
from almdina_erp.almdina_erp.infrastructure.frappe.replacements.plan_persistence import (
    approve_replacement_plan,
    insert_replacement_plan,
)


def _edge_rate(edge_type: str | None) -> float:
    if not edge_type:
        return 0.0
    return flt(
        frappe.db.get_value(
            "Edge Banding Type",
            edge_type,
            "rate_usd_per_meter",
        )
    )


def _approved_source_plan(order: Any) -> Any:
    plan = approved_plan_for_order(order)
    if plan:
        return plan
    frappe.throw(_("يجب وجود خطة قص معتمدة وصالحة قبل اعتماد قطعة التعويض."))


def create_mini_plan(
    order: Any,
    replacement: Any,
    snapshot: dict[str, Any],
) -> Any:
    existing = frappe.db.get_value(
        "Cutting Plan",
        {"replacement_piece": replacement.name, "status": "Approved"},
        "name",
    )
    if existing:
        return frappe.get_doc("Cutting Plan", existing)

    source_plan = _approved_source_plan(order)
    settings = plan_settings(source_plan)

    edge_meters = calculate_edge_meters(
        width_cm=flt(replacement.width_cm),
        length_cm=flt(replacement.length_cm),
        edge_long_right=bool(cint(replacement.edge_long_right)),
        edge_long_left=bool(cint(replacement.edge_long_left)),
        edge_width_top=bool(cint(replacement.edge_width_top)),
        edge_width_bottom=bool(cint(replacement.edge_width_bottom)),
    )
    edge_cost = edge_meters * _edge_rate(replacement.edge_type)
    material_cost = flt(source_plan.board_rate_usd)
    # Zero is a valid explicit approved cost. Never coerce it back to baseline 1.
    cutting_cost = flt(source_plan.cutting_cost_per_board_usd)
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
    plan.board_description = str(
        replacement.board_description or order.board_description or ""
    ).strip()
    plan.optimization_mode = settings.optimization_mode
    plan.machine_type = settings.machine_type
    plan.optimization_time_limit_sec = settings.optimization_time_limit_sec
    plan.kerf_mm = settings.kerf_mm
    plan.trim_margin_mm = settings.trim_margin_mm
    plan.full_board_width_mm = flt(source["full_width_cm"]) * 10
    plan.full_board_length_mm = flt(source["full_length_cm"]) * 10
    plan.usable_board_width_mm = flt(source["usable_width_cm"]) * 10
    plan.usable_board_length_mm = flt(source["usable_length_cm"]) * 10
    plan.required_boards = 1
    plan.used_area_m2 = flt(snapshot["used_area_m2"])
    plan.total_source_area_m2 = flt(snapshot["total_board_area_m2"])
    plan.waste_area_m2 = flt(snapshot["waste_area_m2"])
    plan.waste_percent = (
        flt(plan.waste_area_m2) / flt(plan.total_source_area_m2) * 100
        if flt(plan.total_source_area_m2)
        else 0
    )
    plan.board_rate_usd = flt(source_plan.board_rate_usd)
    plan.cutting_cost_per_board_usd = flt(source_plan.cutting_cost_per_board_usd)
    plan.mdf_cost_usd = material_cost
    plan.cutting_cost_usd = cutting_cost
    plan.edge_cost_usd = edge_cost
    plan.total_cost_usd = planned_total
    plan.snapshot_json = frappe.as_json(snapshot)

    plan.append(
        "sources",
        {
            "sheet_no": 1,
            "source_type": "Full Board",
            "board_description": str(
                replacement.board_description or order.board_description or ""
            ).strip(),
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

    insert_replacement_plan(plan)
    if plan.validation_status != "Valid":
        frappe.throw(_("Replacement Mini Cutting Plan did not pass independent validation."))

    plan.status = "Approved"
    plan.approved_by = frappe.session.user
    plan.approved_on = now_datetime()
    approve_replacement_plan(plan)
    return plan
