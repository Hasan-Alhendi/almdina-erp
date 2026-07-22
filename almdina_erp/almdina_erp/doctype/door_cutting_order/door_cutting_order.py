from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.services.advanced_cutting_optimizer import optimize_plan
from almdina_erp.almdina_erp.services.cutting_engine import (
    expand_piece_groups,
    round_value,
    validate_plan,
)

ENGINE_VERSION = "2.0.0-advanced"


class DoorCuttingOrder(Document):
    def validate(self) -> None:
        self._enforce_approved_immutability()
        self._set_piece_numbers()
        self._validate_numeric_inputs()
        self._validate_piece_inputs()
        self._load_board_snapshot()
        self._calculate_piece_rows()
        self._calculate_cutting_plan()

    def _enforce_approved_immutability(self) -> None:
        """Approved/production orders are historical records, not live calculators."""
        if self.is_new() or self.flags.get("allow_approved_edit"):
            return

        old = self.get_doc_before_save()
        if not old:
            return

        editable_states = {"Draft", "Pending Review", "Rejected"}
        if old.status not in editable_states:
            frappe.throw(
                _(
                    "Order {0} is already approved or in production and cannot be edited/recalculated in place. "
                    "Create a controlled revision instead."
                ).format(self.name)
            )

    @staticmethod
    def _finite(value: Any, label: str) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            frappe.throw(_("{0} must be a valid numeric value.").format(label))
        if not math.isfinite(number):
            frappe.throw(_("{0} must be finite; NaN/Infinity are not allowed.").format(label))
        return number

    def _validate_numeric_inputs(self) -> None:
        kerf = self._finite(self.kerf_mm, _("Kerf (MM)"))
        trim = self._finite(self.trim_margin_mm, _("Trim Margin (MM)"))
        board_rate = self._finite(self.board_rate_usd, _("Board Rate USD"))
        cutting_cost = self._finite(self.cutting_cost_per_board_usd, _("Cutting Cost / Board USD"))
        time_limit = self._finite(self.optimization_time_limit_sec or 10, _("Optimization Time Limit (Sec)"))

        if kerf < 0:
            frappe.throw(_("Kerf (MM) cannot be negative."))
        if trim < 0:
            frappe.throw(_("Trim Margin (MM) cannot be negative."))
        if board_rate < 0:
            frappe.throw(_("Board Rate USD cannot be negative."))
        if cutting_cost < 0:
            frappe.throw(_("Cutting Cost / Board USD cannot be negative."))
        if time_limit <= 0 or time_limit > 120:
            frappe.throw(_("Optimization Time Limit must be greater than 0 and no more than 120 seconds."))

    def _set_piece_numbers(self) -> None:
        for index, row in enumerate(self.pieces or [], start=1):
            row.piece_no = index

    def _validate_piece_inputs(self) -> None:
        if not self.pieces:
            frappe.throw(_("At least one piece row is required."))

        for index, row in enumerate(self.pieces, start=1):
            width = self._finite(row.width_cm, _("Row {0} Width CM").format(index))
            length = self._finite(row.length_cm, _("Row {0} Length CM").format(index))
            qty_raw = self._finite(row.qty, _("Row {0} Quantity").format(index))

            if width <= 0:
                frappe.throw(_("Row {0}: Width must be greater than zero.").format(index))
            if length <= 0:
                frappe.throw(_("Row {0}: Length must be greater than zero.").format(index))
            if qty_raw <= 0 or qty_raw != int(qty_raw):
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
                "custom_board_rate_usd",
            ],
            as_dict=True,
        )

        if not board or not cint(board.custom_is_mdf):
            frappe.throw(_("Selected Item is not marked as an MDF/cutting board."))

        self.full_board_length_mm = self._finite(board.custom_board_length_mm, _("Board Length (MM)"))
        self.full_board_width_mm = self._finite(board.custom_board_width_mm, _("Board Width (MM)"))
        self.board_thickness_mm = self._finite(board.custom_board_thickness_mm, _("Board Thickness (MM)"))
        self.board_color = board.custom_board_color or ""
        self.board_material = board.custom_board_material or ""

        # Item master supplies a default only when the field was truly omitted.
        # Explicit zero is a valid manager-approved value and must remain zero.
        if self.board_rate_usd in (None, "") and board.custom_board_rate_usd not in (None, ""):
            self.board_rate_usd = flt(board.custom_board_rate_usd)

        if self.full_board_length_mm <= 0 or self.full_board_width_mm <= 0:
            frappe.throw(_("Board dimensions are missing or invalid on Item {0}.").format(self.board_item))
        if self.board_thickness_mm < 0:
            frappe.throw(_("Board thickness cannot be negative on Item {0}.").format(self.board_item))

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
        settings = frappe.get_single("Almdina ERP Settings")
        plan = optimize_plan(
            expanded,
            usable_board_width_cm,
            usable_board_length_cm,
            kerf_cm,
            selected_mode=self.packing_mode or "Auto Pro",
            machine_type=self.cutting_machine_type or "Auto",
            time_limit_sec=flt(self.optimization_time_limit_sec) or 10,
            exact_piece_limit=cint(settings.optimal_search_piece_limit) or 40,
            min_remnant_width_cm=flt(settings.min_remnant_width_mm) / 10,
            min_remnant_length_cm=flt(settings.min_remnant_length_mm) / 10,
            min_remnant_area_m2=flt(settings.min_remnant_area_m2),
        )

        validation_errors = validate_plan(
            plan,
            expanded,
            usable_board_width_cm,
            usable_board_length_cm,
        )

        required_boards = len(plan["sheets"])
        mdf_cost = required_boards * flt(self.board_rate_usd)
        cutting_cost = required_boards * flt(self.cutting_cost_per_board_usd)
        total_cost = mdf_cost + cutting_cost + flt(self.edge_cost_usd)
        waste_area = max(0.0, flt(plan["waste_area_m2"]))
        total_board_area = flt(plan["total_board_area_m2"])
        waste_percent = (waste_area / total_board_area * 100) if total_board_area else 0.0
        metrics = plan.get("industrial_metrics") or {}

        self.required_boards = required_boards
        self.mdf_cost_usd = round_value(mdf_cost, 3)
        self.cutting_cost_usd = round_value(cutting_cost, 3)
        self.total_cost_usd = round_value(total_cost, 3)
        self.waste_area_m2 = round_value(waste_area, 3)
        self.waste_percent = round_value(waste_percent, 2)
        self.packing_method = plan["method_label"]
        self.packing_score = (
            f"ألواح: {required_boards} | هدر: {self.waste_percent}% | "
            f"قصات تقديرية: {cint(metrics.get('estimated_cut_count'))} | "
            f"أكبر بقايا مفيدة: {round_value(metrics.get('largest_reusable_free_area_m2'), 3)} م² | "
            f"محاولات: {cint(plan.get('attempts'))} | الخوارزمية: {plan['method_label']}"
        )
        self.engine_version = ENGINE_VERSION

        snapshot = {
            "engine_version": ENGINE_VERSION,
            "optimization_mode": plan.get("optimization_mode") or self.packing_mode or "Auto Pro",
            "machine_type": self.cutting_machine_type or "Auto",
            "method_key": plan["method_key"],
            "method_label": plan["method_label"],
            "ordering_strategy": plan.get("ordering_strategy") or "",
            "score": plan["score"],
            "industrial_metrics": metrics,
            "industrial_rank": list(plan.get("industrial_rank") or []),
            "attempts": cint(plan.get("attempts")),
            "search_elapsed_sec": flt(plan.get("search_elapsed_sec")),
            "search_time_limit_sec": flt(plan.get("search_time_limit_sec")),
            "solver_status": plan.get("solver_status") or "",
            "solver_wall_time_sec": flt(plan.get("solver_wall_time_sec")),
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
        row = frappe.db.get_value(
            "Edge Banding Type",
            edge_type,
            ["rate_usd_per_meter", "disabled"],
            as_dict=True,
        )
        if not row:
            frappe.throw(_("Edge Banding Type {0} does not exist.").format(edge_type))
        if cint(row.disabled):
            frappe.throw(_("Edge Banding Type {0} is disabled.").format(edge_type))
        rate = flt(row.rate_usd_per_meter)
        if not math.isfinite(rate) or rate < 0:
            frappe.throw(_("Edge Banding Type {0} has an invalid rate.").format(edge_type))
        return rate


@frappe.whitelist()
def recalculate_order(order_name: str) -> dict[str, Any]:
    """Recalculate an editable saved order server-side without stock movement."""
    doc = frappe.get_doc("Door Cutting Order", order_name)
    doc.check_permission("write")
    if doc.status not in {"Draft", "Pending Review", "Rejected"}:
        frappe.throw(_("Approved/production orders cannot be recalculated in place."))
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
