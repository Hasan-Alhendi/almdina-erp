from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.services.advanced_cutting_optimizer import enrich_plan_metrics, optimize_plan
from almdina_erp.almdina_erp.services.cutting_engine import (
    create_sheet,
    expand_piece_groups,
    find_best_position_guillotine,
    find_best_position_maxrects,
    place_piece_guillotine,
    place_piece_maxrects,
    sort_pieces,
)


def _piece_rows(order: Any) -> list[dict[str, Any]]:
    return [
        {
            "width_cm": flt(row.width_cm),
            "length_cm": flt(row.length_cm),
            "qty": cint(row.qty),
            "allow_rotation": cint(row.allow_rotation),
            "edge_long_right": cint(row.edge_long_right),
            "edge_long_left": cint(row.edge_long_left),
            "edge_width_top": cint(row.edge_width_top),
            "edge_width_bottom": cint(row.edge_width_bottom),
            "edge_type": row.edge_type or "",
            "edge_rate_usd": flt(row.edge_rate_usd),
            "edge_cost_usd": flt(row.edge_cost_usd),
            "notes": row.notes or "",
        }
        for row in (order.pieces or [])
    ]


def _lock_available_remnants(order: Any) -> list[dict[str, Any]]:
    return frappe.db.sql(
        """
        select name, board_item, length_mm, width_mm, thickness_mm, material, color, area_m2,
               warehouse, location, parent_remnant
        from `tabBoard Remnant`
        where board_item = %s
          and status = 'Available'
          and coalesce(material, '') = %s
          and coalesce(color, '') = %s
          and abs(coalesce(thickness_mm, 0) - %s) <= 0.001
        order by area_m2 asc, creation asc
        for update
        """,
        (
            order.board_item,
            order.board_material or "",
            order.board_color or "",
            flt(order.board_thickness_mm),
        ),
        as_dict=True,
    )


def _pack_one_remnant(
    remaining: list[dict[str, Any]],
    remnant: dict[str, Any],
    kerf_cm: float,
    trim_cm: float,
    machine_type: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    usable_w = flt(remnant["width_mm"]) / 10 - (trim_cm * 2)
    usable_h = flt(remnant["length_mm"]) / 10 - (trim_cm * 2)
    if usable_w <= 0 or usable_h <= 0:
        return None, remaining

    sheet = create_sheet(1, usable_w, usable_h)
    placed_ids: set[int] = set()

    for piece in sort_pieces(remaining, "area_desc"):
        if machine_type == "Panel Saw":
            position = find_best_position_guillotine(sheet, piece, "best_area")
            if not position:
                continue
            place_piece_guillotine(sheet, piece, position, kerf_cm, "short_axis")
        else:
            position = find_best_position_maxrects(sheet, piece, "best_short_side")
            if not position:
                continue
            place_piece_maxrects(sheet, piece, position, kerf_cm)
        placed_ids.add(int(piece["id"]))

    if not placed_ids:
        return None, remaining

    sheet.pop("free_rects", None)
    sheet["source_type"] = "Remnant"
    sheet["remnant"] = remnant["name"]
    sheet["board_item"] = remnant["board_item"]
    sheet["material"] = remnant.get("material") or ""
    sheet["color"] = remnant.get("color") or ""
    sheet["thickness_mm"] = flt(remnant.get("thickness_mm"))
    sheet["full_width_cm"] = flt(remnant["width_mm"]) / 10
    sheet["full_length_cm"] = flt(remnant["length_mm"]) / 10
    sheet["usable_width_cm"] = usable_w
    sheet["usable_length_cm"] = usable_h
    sheet["source_area_m2"] = usable_w * usable_h / 10000

    return sheet, [piece for piece in remaining if int(piece["id"]) not in placed_ids]


def _validate_variable_plan(plan: dict[str, Any], requested_pieces: list[dict[str, Any]], order: Any) -> list[str]:
    errors: list[str] = []
    expected = {int(piece["id"]): piece for piece in requested_pieces}
    seen: dict[int, int] = {}
    tolerance = 1e-7

    for sheet in plan.get("sheets") or []:
        board_w = flt(sheet.get("w"))
        board_h = flt(sheet.get("h"))
        pieces = sheet.get("pieces") or []

        if sheet.get("board_item") != order.board_item:
            errors.append(_("Source sheet {0} uses a different Board Item.").format(sheet.get("sheet_no")))
        if (sheet.get("material") or "") != (order.board_material or ""):
            errors.append(_("Source sheet {0} material does not match the order snapshot.").format(sheet.get("sheet_no")))
        if (sheet.get("color") or "") != (order.board_color or ""):
            errors.append(_("Source sheet {0} color does not match the order snapshot.").format(sheet.get("sheet_no")))
        if abs(flt(sheet.get("thickness_mm")) - flt(order.board_thickness_mm)) > 0.001:
            errors.append(_("Source sheet {0} thickness does not match the order snapshot.").format(sheet.get("sheet_no")))

        for placed in pieces:
            piece_id = int(placed["id"])
            seen[piece_id] = seen.get(piece_id, 0) + 1
            x, y, w, h = map(flt, (placed.get("x"), placed.get("y"), placed.get("w"), placed.get("h")))
            if x < -tolerance or y < -tolerance or x + w > board_w + tolerance or y + h > board_h + tolerance:
                errors.append(_("Piece {0} exceeds source bounds on sheet {1}.").format(placed.get("label"), sheet.get("sheet_no")))

            source = expected.get(piece_id)
            if source:
                normal = abs(w - flt(source["width_cm"])) <= tolerance and abs(h - flt(source["length_cm"])) <= tolerance
                rotated = (
                    bool(source.get("allow_rotation"))
                    and abs(w - flt(source["length_cm"])) <= tolerance
                    and abs(h - flt(source["width_cm"])) <= tolerance
                )
                if not (normal or rotated):
                    errors.append(_("Piece {0} has an invalid orientation/dimension.").format(placed.get("label")))
            else:
                errors.append(_("Unknown piece id {0} exists in plan.").format(piece_id))

        for i, a in enumerate(pieces):
            ax1, ay1 = flt(a.get("x")), flt(a.get("y"))
            ax2, ay2 = ax1 + flt(a.get("w")), ay1 + flt(a.get("h"))
            for b in pieces[i + 1 :]:
                bx1, by1 = flt(b.get("x")), flt(b.get("y"))
                bx2, by2 = bx1 + flt(b.get("w")), by1 + flt(b.get("h"))
                overlap_w = min(ax2, bx2) - max(ax1, bx1)
                overlap_h = min(ay2, by2) - max(ay1, by1)
                if overlap_w > tolerance and overlap_h > tolerance:
                    errors.append(_("Pieces {0} and {1} overlap on sheet {2}.").format(a.get("label"), b.get("label"), sheet.get("sheet_no")))

    for piece_id, piece in expected.items():
        count = seen.get(piece_id, 0)
        if count == 0:
            errors.append(_("Piece {0} is missing from the plan.").format(piece.get("label")))
        elif count > 1:
            errors.append(_("Piece {0} appears more than once in the plan.").format(piece.get("label")))

    if plan.get("unplaced"):
        errors.append(_("The plan still contains unplaced pieces."))
    return errors


def build_approval_plan(order: Any) -> dict[str, Any]:
    """Build approval plan, preferring physically matching remnants when enabled."""
    pieces = expand_piece_groups(_piece_rows(order))
    full_board_w_cm = flt(order.full_board_width_mm) / 10
    full_board_h_cm = flt(order.full_board_length_mm) / 10
    kerf_cm = flt(order.kerf_mm) / 10
    trim_cm = flt(order.trim_margin_mm) / 10
    usable_full_w = full_board_w_cm - (trim_cm * 2)
    usable_full_h = full_board_h_cm - (trim_cm * 2)

    settings = frappe.get_single("Almdina ERP Settings")
    machine_type = order.cutting_machine_type or settings.default_cutting_machine_type or "Auto"
    remaining = list(pieces)
    sheets: list[dict[str, Any]] = []
    used_remnants: list[str] = []

    if cint(settings.prefer_remnants_before_full_boards):
        for remnant in _lock_available_remnants(order):
            if not remaining:
                break
            sheet, remaining = _pack_one_remnant(remaining, remnant, kerf_cm, trim_cm, machine_type)
            if not sheet:
                continue
            sheet["sheet_no"] = len(sheets) + 1
            sheets.append(sheet)
            used_remnants.append(remnant["name"])

    full_plan = optimize_plan(
        remaining,
        usable_full_w,
        usable_full_h,
        kerf_cm,
        selected_mode=order.packing_mode or "Auto Pro",
        machine_type=machine_type,
        time_limit_sec=flt(order.optimization_time_limit_sec) or flt(settings.default_optimization_time_limit_sec) or 10,
        exact_piece_limit=cint(settings.optimal_search_piece_limit) or 40,
        min_remnant_width_cm=flt(settings.min_remnant_width_mm) / 10,
        min_remnant_length_cm=flt(settings.min_remnant_length_mm) / 10,
        min_remnant_area_m2=flt(settings.min_remnant_area_m2),
    ) if remaining else {
        "method_key": order.packing_mode or "Auto Pro",
        "method_label": "No full board required",
        "optimization_mode": order.packing_mode or "Auto Pro",
        "sheets": [],
        "unplaced": [],
        "score": 0,
        "attempts": 0,
        "industrial_metrics": {},
    }

    for full_sheet in full_plan.get("sheets") or []:
        full_sheet["sheet_no"] = len(sheets) + 1
        full_sheet["source_type"] = "Full Board"
        full_sheet["remnant"] = None
        full_sheet["board_item"] = order.board_item
        full_sheet["material"] = order.board_material or ""
        full_sheet["color"] = order.board_color or ""
        full_sheet["thickness_mm"] = flt(order.board_thickness_mm)
        full_sheet["full_width_cm"] = full_board_w_cm
        full_sheet["full_length_cm"] = full_board_h_cm
        full_sheet["usable_width_cm"] = usable_full_w
        full_sheet["usable_length_cm"] = usable_full_h
        full_sheet["source_area_m2"] = usable_full_w * usable_full_h / 10000
        sheets.append(full_sheet)

    total_source_area = sum(flt(sheet.get("source_area_m2")) for sheet in sheets)
    used_area = sum(flt(piece.get("area_m2")) for sheet in sheets for piece in (sheet.get("pieces") or []))
    waste_area = max(0.0, total_source_area - used_area)
    full_board_count = sum(1 for sheet in sheets if sheet.get("source_type") == "Full Board")
    unplaced = full_plan.get("unplaced") or []

    plan = {
        "engine_version": order.engine_version or "2.0.0-advanced",
        "optimization_mode": full_plan.get("optimization_mode") or order.packing_mode or "Auto Pro",
        "machine_type": machine_type,
        "method_key": full_plan.get("method_key") or order.packing_mode or "Auto Pro",
        "method_label": (("Remnant First + " if used_remnants else "") + (full_plan.get("method_label") or "No full board required")),
        "score": full_plan.get("score") or 0,
        "ordering_strategy": full_plan.get("ordering_strategy") or "",
        "attempts": cint(full_plan.get("attempts")),
        "search_elapsed_sec": flt(full_plan.get("search_elapsed_sec")),
        "search_time_limit_sec": flt(full_plan.get("search_time_limit_sec")),
        "solver_status": full_plan.get("solver_status") or "",
        "solver_wall_time_sec": flt(full_plan.get("solver_wall_time_sec")),
        "full_board_width_cm": full_board_w_cm,
        "full_board_length_cm": full_board_h_cm,
        "usable_board_width_cm": usable_full_w,
        "usable_board_length_cm": usable_full_h,
        "kerf_cm": kerf_cm,
        "trim_cm": trim_cm,
        "used_area_m2": used_area,
        "total_board_area_m2": total_source_area,
        "waste_area_m2": waste_area,
        "required_full_boards": full_board_count,
        "used_remnants": used_remnants,
        "sheets": sheets,
        "unplaced": unplaced,
    }

    metric_method = plan["method_key"] if plan["method_key"] != "Auto Pro" else "MaxRects Best Short Side"
    plan = enrich_plan_metrics(
        plan,
        metric_method,
        machine_type,
        min_remnant_width_cm=flt(settings.min_remnant_width_mm) / 10,
        min_remnant_length_cm=flt(settings.min_remnant_length_mm) / 10,
        min_remnant_area_m2=flt(settings.min_remnant_area_m2),
    )
    validation_errors = _validate_variable_plan(plan, pieces, order)
    plan["validation"] = {"is_valid": not validation_errors, "errors": validation_errors}
    return plan


def reserve_plan_remnants(order_name: str, plan: dict[str, Any]) -> None:
    """Reserve remnants already locked by build_approval_plan within this transaction."""
    for remnant_name in plan.get("used_remnants") or []:
        current = frappe.db.get_value("Board Remnant", remnant_name, ["status", "reserved_for_order"], as_dict=True)
        if not current or current.status != "Available":
            frappe.throw(_("Remnant {0} was taken by another order; recalculate approval.").format(remnant_name))
        frappe.db.set_value(
            "Board Remnant",
            remnant_name,
            {
                "status": "Reserved",
                "reserved_for_order": order_name,
                "reservation_timestamp": now_datetime(),
            },
            update_modified=True,
        )
