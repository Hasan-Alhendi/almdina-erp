from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


def _intersection(a: dict[str, float], b: dict[str, float]) -> tuple[float, float, float, float] | None:
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _subtract_rect(free: dict[str, float], used: dict[str, float]) -> list[dict[str, float]]:
    """Subtract one used rectangle into non-overlapping rectangular partitions."""
    inter = _intersection(free, used)
    if not inter:
        return [free]

    ix1, iy1, ix2, iy2 = inter
    fx1, fy1 = free["x"], free["y"]
    fx2, fy2 = fx1 + free["w"], fy1 + free["h"]
    result: list[dict[str, float]] = []

    if ix1 > fx1:
        result.append({"x": fx1, "y": fy1, "w": ix1 - fx1, "h": free["h"]})
    if ix2 < fx2:
        result.append({"x": ix2, "y": fy1, "w": fx2 - ix2, "h": free["h"]})

    middle_w = ix2 - ix1
    if middle_w > 0 and iy1 > fy1:
        result.append({"x": ix1, "y": fy1, "w": middle_w, "h": iy1 - fy1})
    if middle_w > 0 and iy2 < fy2:
        result.append({"x": ix1, "y": iy2, "w": middle_w, "h": fy2 - iy2})

    return [r for r in result if r["w"] > 0.01 and r["h"] > 0.01]


def _merge_adjacent(rects: list[dict[str, float]], tolerance: float = 0.01) -> list[dict[str, float]]:
    rects = [dict(r) for r in rects]
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(rects):
            for j in range(i + 1, len(rects)):
                b = rects[j]
                same_y = abs(a["y"] - b["y"]) <= tolerance and abs(a["h"] - b["h"]) <= tolerance
                touching_x = abs((a["x"] + a["w"]) - b["x"]) <= tolerance or abs((b["x"] + b["w"]) - a["x"]) <= tolerance
                if same_y and touching_x:
                    x = min(a["x"], b["x"])
                    rects[i] = {"x": x, "y": a["y"], "w": a["w"] + b["w"], "h": a["h"]}
                    rects.pop(j)
                    changed = True
                    break

                same_x = abs(a["x"] - b["x"]) <= tolerance and abs(a["w"] - b["w"]) <= tolerance
                touching_y = abs((a["y"] + a["h"]) - b["y"]) <= tolerance or abs((b["y"] + b["h"]) - a["y"]) <= tolerance
                if same_x and touching_y:
                    y = min(a["y"], b["y"])
                    rects[i] = {"x": a["x"], "y": y, "w": a["w"], "h": a["h"] + b["h"]}
                    rects.pop(j)
                    changed = True
                    break
            if changed:
                break
    return rects


def derive_free_rectangles(source: Any, pieces: list[Any], kerf_mm: float) -> list[dict[str, float]]:
    free = [{"x": 0.0, "y": 0.0, "w": flt(source.usable_width_mm), "h": flt(source.usable_length_mm)}]
    for piece in sorted(pieces, key=lambda p: (flt(p.y_mm), flt(p.x_mm), p.piece_label or "")):
        used = {
            "x": flt(piece.x_mm),
            "y": flt(piece.y_mm),
            "w": min(flt(piece.width_mm) + flt(kerf_mm), max(0.0, flt(source.usable_width_mm) - flt(piece.x_mm))),
            "h": min(flt(piece.height_mm) + flt(kerf_mm), max(0.0, flt(source.usable_length_mm) - flt(piece.y_mm))),
        }
        next_free: list[dict[str, float]] = []
        for rect in free:
            next_free.extend(_subtract_rect(rect, used))
        free = next_free
    return _merge_adjacent(free)


def register_plan_remnants(order_name: str) -> dict[str, Any]:
    order = frappe.get_doc("Door Cutting Order", order_name)
    plan_name = order.approved_plan
    if not plan_name:
        frappe.throw(_("Order {0} has no approved Cutting Plan.").format(order_name))
    plan = frappe.get_doc("Cutting Plan", plan_name)

    existing = frappe.get_all(
        "Board Remnant",
        filters={"source_order": order.name, "source_plan": plan.name},
        pluck="name",
    )
    if existing:
        return {"created": existing, "already_generated": True}

    settings = frappe.get_single("Almdina ERP Settings")
    min_width = flt(settings.min_remnant_width_mm)
    min_length = flt(settings.min_remnant_length_mm)
    min_area = flt(settings.min_remnant_area_m2)
    created: list[str] = []
    reusable_area = 0.0
    scrap_area = 0.0

    pieces_by_sheet: dict[int, list[Any]] = {}
    for piece in plan.placed_pieces or []:
        pieces_by_sheet.setdefault(int(piece.sheet_no), []).append(piece)

    for source in plan.sources or []:
        free_rects = derive_free_rectangles(source, pieces_by_sheet.get(int(source.sheet_no), []), flt(plan.kerf_mm))
        parent_remnant = source.remnant if source.source_type == "Remnant" else None
        source_warehouse = settings.default_warehouse
        if parent_remnant:
            source_warehouse = frappe.db.get_value("Board Remnant", parent_remnant, "warehouse") or source_warehouse

        for rect in free_rects:
            width_mm = flt(rect["w"])
            length_mm = flt(rect["h"])
            area_m2 = width_mm * length_mm / 1_000_000
            qualifies = width_mm >= min_width and length_mm >= min_length and area_m2 >= min_area
            if not qualifies:
                scrap_area += area_m2
                continue

            remnant = frappe.new_doc("Board Remnant")
            remnant.status = "Available"
            remnant.board_item = order.board_item
            remnant.warehouse = source_warehouse
            remnant.length_mm = length_mm
            remnant.width_mm = width_mm
            remnant.thickness_mm = order.board_thickness_mm
            remnant.source_order = order.name
            remnant.source_plan = plan.name
            remnant.parent_remnant = parent_remnant
            remnant.notes = _("Generated automatically from source sheet {0} after cutting.").format(source.sheet_no)
            remnant.insert(ignore_permissions=True)
            created.append(remnant.name)
            reusable_area += area_m2

    # Store derived operational metrics inside the immutable plan's snapshot is
    # intentionally avoided; actual remnants are separate auditable documents.
    return {
        "created": created,
        "already_generated": False,
        "reusable_area_m2": reusable_area,
        "scrap_area_m2": scrap_area,
    }


@frappe.whitelist()
def generate_order_remnants(order_name: str) -> dict[str, Any]:
    require_any_role("Production Manager", "Stock Manager")
    return register_plan_remnants(order_name)
