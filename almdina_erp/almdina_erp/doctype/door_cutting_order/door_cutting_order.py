from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.services.advanced_cutting_optimizer import optimize_plan
from almdina_erp.almdina_erp.services.cutting_engine import (
    expand_piece_groups,
    round_value,
    validate_plan,
)
from almdina_erp.almdina_erp.services.special_shape_service import (
    has_special_price_approval_role,
    validate_special_shape_drawing,
)

ENGINE_VERSION = "2.0.0-advanced"


class DoorCuttingOrder(Document):
    def validate(self) -> None:
        self._enforce_approved_immutability()
        self._set_piece_numbers()
        self._validate_numeric_inputs()
        self._validate_piece_inputs()
        self._validate_special_shape_rows()
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

    def _validate_special_shape_rows(self) -> None:
        old_doc = None if self.is_new() else self.get_doc_before_save()
        old_rows = {row.name: row for row in (old_doc.pieces or [])} if old_doc else {}
        can_approve_price = has_special_price_approval_role()
        approval_action = bool(self.flags.get("special_price_approval_action"))
        protected_fields = (
            "special_shape_custom_unit_price_usd",
            "special_shape_price_status",
            "special_shape_price_note",
            "special_shape_price_approved_by",
            "special_shape_price_approved_on",
        )
        geometry_fields = (
            "piece_type",
            "width_cm",
            "length_cm",
            "qty",
            "special_shape_drawing_json",
        )

        for index, row in enumerate(self.pieces or [], start=1):
            row.piece_type = row.piece_type or "Regular"
            if row.piece_type not in {"Regular", "Special"}:
                frappe.throw(_("Row {0}: Piece Type is invalid.").format(index))

            old_row = old_rows.get(row.name)
            drawing = validate_special_shape_drawing(row.special_shape_drawing_json)
            drawing_changed = bool(
                (
                    old_row
                    and str(old_row.special_shape_drawing_json or "")
                    != str(row.special_shape_drawing_json or "")
                )
                or (not old_row and drawing)
            )
            geometry_changed = bool(
                old_row
                and any(
                    str(getattr(old_row, fieldname, "") or "")
                    != str(getattr(row, fieldname, "") or "")
                    for fieldname in geometry_fields
                )
            )

            if not can_approve_price and not approval_action:
                protected_price_changed = False
                if old_row:
                    protected_price_changed = any(
                        str(getattr(old_row, fieldname, "") or "")
                        != str(getattr(row, fieldname, "") or "")
                        for fieldname in protected_fields
                    )
                else:
                    protected_price_changed = bool(
                        flt(row.special_shape_custom_unit_price_usd)
                        or row.special_shape_price_status == "Approved"
                        or row.special_shape_price_note
                        or row.special_shape_price_approved_by
                        or row.special_shape_price_approved_on
                    )
                safe_geometry_invalidation = bool(
                    geometry_changed
                    and row.special_shape_price_status in {
                        None,
                        "",
                        "Estimated",
                        "Not Applicable",
                    }
                    and not flt(row.special_shape_custom_unit_price_usd)
                    and not row.special_shape_price_note
                    and not row.special_shape_price_approved_by
                    and not row.special_shape_price_approved_on
                )
                if protected_price_changed and not safe_geometry_invalidation:
                    frappe.throw(
                        _(
                            "Row {0}: only Accounts Management can change or approve "
                            "the special door price."
                        ).format(index),
                        frappe.PermissionError,
                    )

            if drawing_changed:
                row.special_shape_drawing_updated_by = frappe.session.user
                row.special_shape_drawing_updated_on = now_datetime()

            if row.piece_type == "Special":
                row.special_shape_status = "Documented" if drawing and drawing.get("elements") else "Needs Documentation"
            else:
                row.special_shape_status = "Not Required"

            if geometry_changed and not approval_action:
                row.special_shape_custom_unit_price_usd = 0
                row.special_shape_price_status = (
                    "Estimated" if row.piece_type == "Special" else "Not Applicable"
                )
                row.special_shape_price_note = ""
                row.special_shape_price_approved_by = ""
                row.special_shape_price_approved_on = None

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

            is_special = (row.piece_type or "Regular") == "Special"
            long_edges = 0 if is_special else cint(row.edge_long_right) + cint(row.edge_long_left)
            width_edges = 0 if is_special else cint(row.edge_width_top) + cint(row.edge_width_bottom)

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
        self._calculate_special_shape_pricing(settings)

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

    def _calculate_special_shape_pricing(self, settings: Any) -> None:
        """Replace each special row's automatic cost allocation with an inclusive quote price."""

        special_rows = [
            row for row in (self.pieces or []) if (row.piece_type or "Regular") == "Special"
        ]
        if not special_rows:
            self.special_shapes_baseline_cost_usd = 0
            self.special_shapes_estimated_total_usd = 0
            self.special_shapes_final_total_usd = 0
            self.customer_quote_total_usd = round_value(self.total_cost_usd, 3)
            self.customer_quote_status = "Automatic"
            for row in self.pieces or []:
                row.special_shape_estimated_unit_price_usd = 0
                row.special_shape_custom_unit_price_usd = 0
                row.special_shape_final_unit_price_usd = 0
                row.special_shape_price_status = "Not Applicable"
            return

        design_fee = self._finite(
            settings.default_special_design_fee_usd or 0,
            _("Default Special Design Fee USD / Piece"),
        )
        cnc_fee = self._finite(
            settings.default_special_cnc_fee_usd or 0,
            _("Default Special CNC Fee USD / Piece"),
        )
        manual_edge_fee = self._finite(
            settings.default_special_manual_edge_fee_usd or 0,
            _("Default Manual Edge Fee USD / Piece"),
        )
        margin_percent = self._finite(
            settings.default_special_margin_percent or 0,
            _("Default Special Shape Margin Percent"),
        )
        if min(design_fee, cnc_fee, manual_edge_fee, margin_percent) < 0:
            frappe.throw(_("Special shape estimate defaults cannot be negative."))

        total_area = flt(self.total_area_m2)
        board_and_cutting_cost = flt(self.mdf_cost_usd) + flt(self.cutting_cost_usd)
        baseline_total = 0.0
        estimated_total = 0.0
        final_total = 0.0
        approved_count = 0

        for row in special_rows:
            qty = max(1, cint(row.qty))
            area_share = (flt(row.area_m2) / total_area) if total_area else 0
            allocated_total = (board_and_cutting_cost * area_share) + flt(row.edge_cost_usd)
            baseline_unit = allocated_total / qty
            estimated_unit = (
                baseline_unit + design_fee + cnc_fee + manual_edge_fee
            ) * (1 + (margin_percent / 100))
            estimated_unit = round_value(estimated_unit, 3)

            is_approved = bool(
                row.special_shape_price_status == "Approved"
                and row.special_shape_price_approved_by
            )
            final_unit = (
                flt(row.special_shape_custom_unit_price_usd)
                if is_approved
                else estimated_unit
            )

            row.special_shape_estimated_unit_price_usd = estimated_unit
            row.special_shape_final_unit_price_usd = round_value(final_unit, 3)
            if is_approved:
                approved_count += 1
            else:
                row.special_shape_price_status = "Estimated"
                row.special_shape_custom_unit_price_usd = 0
                row.special_shape_price_note = ""
                row.special_shape_price_approved_by = ""
                row.special_shape_price_approved_on = None

            baseline_total += allocated_total
            estimated_total += estimated_unit * qty
            final_total += final_unit * qty

        regular_automatic_total = max(0.0, flt(self.total_cost_usd) - baseline_total)
        self.special_shapes_baseline_cost_usd = round_value(baseline_total, 3)
        self.special_shapes_estimated_total_usd = round_value(estimated_total, 3)
        self.special_shapes_final_total_usd = round_value(final_total, 3)
        self.customer_quote_total_usd = round_value(regular_automatic_total + final_total, 3)

        if approved_count == len(special_rows):
            self.customer_quote_status = "Approved"
        elif approved_count:
            self.customer_quote_status = "Partially Approved"
        else:
            self.customer_quote_status = "Estimated"

    def ensure_special_shapes_documented(self) -> None:
        missing = [
            str(row.piece_no or row.idx)
            for row in (self.pieces or [])
            if (row.piece_type or "Regular") == "Special"
            and row.special_shape_status != "Documented"
        ]
        if missing:
            frappe.throw(
                _("Document the special door drawing before review. Missing rows: {0}.").format(
                    ", ".join(missing)
                )
            )

    def ensure_special_prices_approved(self) -> None:
        pending = [
            str(row.piece_no or row.idx)
            for row in (self.pieces or [])
            if (row.piece_type or "Regular") == "Special"
            and row.special_shape_price_status != "Approved"
        ]
        if pending:
            frappe.throw(
                _(
                    "Accounts Management must approve every special door price before "
                    "production approval. Pending rows: {0}."
                ).format(", ".join(pending))
            )

    @staticmethod
    def _piece_row_as_dict(row: Any) -> dict[str, Any]:
        return {
            "width_cm": flt(row.width_cm),
            "length_cm": flt(row.length_cm),
            "qty": cint(row.qty),
            "allow_rotation": cint(row.allow_rotation),
            "edge_long_right": 0 if row.piece_type == "Special" else cint(row.edge_long_right),
            "edge_long_left": 0 if row.piece_type == "Special" else cint(row.edge_long_left),
            "edge_width_top": 0 if row.piece_type == "Special" else cint(row.edge_width_top),
            "edge_width_bottom": 0 if row.piece_type == "Special" else cint(row.edge_width_bottom),
            "edge_type": row.edge_type or "",
            "edge_rate_usd": flt(row.edge_rate_usd),
            "edge_cost_usd": flt(row.edge_cost_usd),
            "piece_type": row.piece_type or "Regular",
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
        "special_shapes_baseline_cost_usd": doc.special_shapes_baseline_cost_usd,
        "special_shapes_estimated_total_usd": doc.special_shapes_estimated_total_usd,
        "special_shapes_final_total_usd": doc.special_shapes_final_total_usd,
        "customer_quote_total_usd": doc.customer_quote_total_usd,
        "customer_quote_status": doc.customer_quote_status,
        "cutting_plan_json": doc.cutting_plan_json,
    }
