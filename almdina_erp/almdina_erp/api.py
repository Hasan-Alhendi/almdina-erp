from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt


@frappe.whitelist()
def preview_door_cutting_order(doc: str | dict[str, Any]) -> dict[str, Any]:
    """Calculate a Door Cutting Order without saving it.

    The legacy client script recalculated while the operator was typing.  The
    production app keeps that UX, but the authoritative implementation now runs
    on the server.  Preview intentionally tolerates incomplete rows so a newly
    added Excel-like grid row does not block the form while it is being filled.
    Strict validation still runs on normal document save/submit.
    """

    payload = frappe.parse_json(doc) if isinstance(doc, str) else dict(doc or {})
    payload["doctype"] = "Door Cutting Order"

    preview = frappe.get_doc(payload)

    # Preserve legacy live-calculation behaviour without invoking the strict
    # save-time input validator on partially entered rows.
    preview._set_piece_numbers()
    preview._calculate_piece_rows()

    has_complete_piece = any(
        flt(row.width_cm) > 0 and flt(row.length_cm) > 0 and cint(row.qty) > 0
        for row in (preview.pieces or [])
    )

    if preview.board_item and has_complete_piece:
        preview._load_board_snapshot()
        preview._calculate_cutting_plan()
    else:
        preview.required_boards = 0
        preview.mdf_cost_usd = 0
        preview.cutting_cost_usd = 0
        preview.total_cost_usd = flt(preview.edge_cost_usd)
        preview.waste_area_m2 = 0
        preview.waste_percent = 0
        preview.packing_method = ""
        preview.packing_score = ""
        preview.engine_version = ""
        preview.cutting_plan_json = ""

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
        "packing_method": preview.packing_method,
        "packing_score": preview.packing_score,
        "engine_version": preview.engine_version,
        "cutting_plan_json": preview.cutting_plan_json,
        "pieces": [
            {
                "piece_no": row.piece_no,
                "area_m2": row.area_m2,
                "edge_meters": row.edge_meters,
                "edge_rate_usd": row.edge_rate_usd,
                "edge_cost_usd": row.edge_cost_usd,
            }
            for row in (preview.pieces or [])
        ],
    }
