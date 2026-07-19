from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.services.cutting_engine import (
    choose_best_plan,
    expand_piece_groups,
    round_value,
    validate_plan,
)

ENGINE_VERSION = "1.0.0-baseline"


class DoorCuttingOrder(Document):
    def validate(self) -> None:
        self._set_piece_numbers()
        self._validate_piece_inputs()
        self._load_board_snapshot()
        self._calculate_piece_rows()
        self._calculate_cutting_plan()

    def _set_piece_numbers(self) -> None:
        for index, row in enumerate(self.pieces or [], start=1):
            row.piece_no = index

    def _validate_piece_inputs(self) -> None:
        if not self.pieces:
            frappe.throw(_("At least one piece row is required."))

        for index, row in enumerate(self.pieces, start=1):
            if flt(row.width_cm) <= 0:
                frappe.throw(_("Row {0}: Width must be greater than zero.").format(index))
            if flt(row.length_cm) <= 0:
                frappe.throw(_("Row {0}: Length must be greater than zero.").format(index))
            if cint(row.qty) <= 0 or flt(row.qty) != cint(row.qty):
                frappe.throw(_("Row {0}: Quantity must be a positive integer.").format(index))

    def _load_board_snapshot(self) -> None:
        if not self.board_item:
            frappe.throw(_("Board Item is required."))

        board = frappe.db.get_value(
            "Item",
            self.board_item,
            [
                "custom_is_mdf",
                "custom_board_length_mm",
                "custom_board_width_mm",
                "custom_board_thickness_mm",
                "custom_board_color",
                "custom_board_material",
            ],
            as_dict=True,
        )

        if not board or not cint(board.custom_is_mdf):
            frappe.throw(_("Selected Item is not marked as an MDF/cutting board."))

        self.full_board_length_mm = flt(board.custom_board_length_mm)
        self.full_board_width_mm = flt(board.custom_board_width_mm)
        self.board_thickness_mm = flt(board.custom_board_thickness_mm)
        self.board_color = board.custom_board_color or ""
        self.board_material = board.custom_board_material or ""

        if self.full_board_length_mm <= 0 or self.full_board_width_mm <= 0:
            frappe.throw(_("Board dimensions are missing or invalid on Item {0}.").format(self.board_item))

        trim_mm = flt(self.trim_margin_mm)
        usable_length_mm = self.full_board_length_mm - (trim_mm * 2)
        usable_width_mm = self.full_board_width_mm - (trim_mm * 2)
        if usable_length_mm <= 0 or usable_width_mm <= 0:
            frappe.throw(_("Trim Margin leaves no usable board area."))

    def _calculate_piece_rows(self) -> None:
        total_area = 0.0
        total_edge_meters = 0.0
        total_edge_cost = 0.0

        default_rate = self._get_edge_rate(self.default_edge_type)

        for row in self.pieces:
            width_cm = flt(row.width_cm)
            length_cm = flt(row.length_cm)
            qty = cint(row.qty)

            long_edges = cint(row.edge_long_right) + cint(row.edge_long_left)
            width_edges = cint(row.edge_width_top) + cint(row.edge_width_bottom)

            area_m2 = (width_cm * length_cm * qty) / 10000
            edge_meters = (((length_cm * long_edges) + (width_cm * width_edges)) * qty) / 100

            effective_edge_type = row.edge_type or self.default_edge_type
            edge_rate = self._get_edge_rate(effective_edge_type) if effective_edge_type else default_rate
            edge_cost = edge_meters * edge_rate

            row.area_m2 = round_value(area_m2, 3)
            row.edge_meters = round_value(edge_meters, 3)
            row.edge_rate_usd = edge_rate
            row.edge_cost_usd = round_value(edge_cost, 3)

            total_area += area_m2
            total_edge_meters += edge_meters
            total_edge_cost += edge_cost

        self.total_area_m2 = round_value(total_area, 3)
        self.total_edge_meters = round_value(total_edge_meters, 3)
        self.edge_cost_usd = round_value(total_edge_cost, 3)

    def _calculate_cutting_plan(self) -> None:
        full_board_length_cm = flt(self.full_board_length_mm) / 10
        full_board_width_cm = flt(self.full_board_width_mm) / 10
        trim_cm = flt(self.trim_margin_mm) / 10
        kerf_cm = flt(self.kerf_mm) / 10

        usable_board_length_cm = full_board_length_cm - (trim_cm * 2)
        usable_board_width_cm = full_board_width_cm - (trim_cm * 2)

        piece_rows = [self._piece_row_as_dict(row) for row in self.pieces]
        expanded = expand_piece_groups(piece_rows)
        plan = choose_best_plan(
            expanded,
            usable_board_width_cm,
            usable_board_length_cm,
            kerf_cm,
            self.packing_mode or "Auto",
        )

        validation_errors = validate_plan(
            plan,
            expanded,
            usable_board_width_cm,
            usable_board_length_cm,
        )

        required_boards = len(plan["sheets"])
        mdf_cost = required_boards * flt(self.board_rate_usd)
        cutting_cost = required_boards * flt(self.cutting_cost_per_board_usd or 1)
        total_cost = mdf_cost + cutting_cost + flt(self.edge_cost_usd)
        waste_area = max(0.0, flt(plan["waste_area_m2"]))
        total_board_area = flt(plan["total_board_area_m2"])
        waste_percent = (waste_area / total_board_area * 100) if total_board_area else 0.0

        self.required_boards = required_boards
        self.mdf_cost_usd = round_value(mdf_cost, 3)
        self.cutting_cost_usd = round_value(cutting_cost, 3)
        self.total_cost_usd = round_value(total_cost, 3)
        self.waste_area_m2 = round_value(waste_area, 3)
        self.waste_percent = round_value(waste_percent, 2)
        self.packing_method = plan["method_label"]
        self.packing_score = (
            f"ألواح: {required_boards} | هدر: {self.waste_percent}% | "
            f"غير مدخل: {len(plan['unplaced'])} | الخوارزمية: {plan['method_label']}"
        )
        self.engine_version = ENGINE_VERSION

        snapshot = {
            "engine_version": ENGINE_VERSION,
            "method_key": plan["method_key"],
            "method_label": plan["method_label"],
            "score": plan["score"],
            "full_board_width_cm": full_board_width_cm,
            "full_board_length_cm": full_board_length_cm,
            "usable_board_width_cm": usable_board_width_cm,
            "usable_board_length_cm": usable_board_length_cm,
            "kerf_cm": kerf_cm,
            "trim_cm": trim_cm,
            "used_area_m2": plan["used_area_m2"],
            "total_board_area_m2": plan["total_board_area_m2"],
            "waste_area_m2": plan["waste_area_m2"],
            "sheets": plan["sheets"],
            "unplaced": plan["unplaced"],
            "validation": {
                "is_valid": not validation_errors,
                "errors": validation_errors,
            },
        }
        self.cutting_plan_json = frappe.as_json(snapshot)

    @staticmethod
    def _piece_row_as_dict(row: Any) -> dict[str, Any]:
        return {
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

    @staticmethod
    def _get_edge_rate(edge_type: str | None) -> float:
        if not edge_type:
            return 0.0
        value = frappe.db.get_value(
            "Edge Banding Type",
            edge_type,
            "rate_usd_per_meter",
        )
        return flt(value)


@frappe.whitelist()
def recalculate_order(order_name: str) -> dict[str, Any]:
    """Recalculate a saved order server-side without creating stock movements."""
    doc = frappe.get_doc("Door Cutting Order", order_name)
    doc.check_permission("write")
    doc.validate()
    doc.save()
    return {
        "name": doc.name,
        "required_boards": doc.required_boards,
        "waste_area_m2": doc.waste_area_m2,
        "waste_percent": doc.waste_percent,
        "packing_method": doc.packing_method,
        "packing_score": doc.packing_score,
        "total_area_m2": doc.total_area_m2,
        "total_edge_meters": doc.total_edge_meters,
        "mdf_cost_usd": doc.mdf_cost_usd,
        "cutting_cost_usd": doc.cutting_cost_usd,
        "edge_cost_usd": doc.edge_cost_usd,
        "total_cost_usd": doc.total_cost_usd,
        "cutting_plan_json": doc.cutting_plan_json,
    }
