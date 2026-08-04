from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, now_datetime

from almdina_erp.almdina_erp.services.advanced_cutting_optimizer import optimize_plan
from almdina_erp.almdina_erp.services.cutting_engine import (
    expand_piece_groups,
    round_value,
    validate_plan,
)
from almdina_erp.almdina_erp.services.special_shape_service import (
    has_special_price_approval_permission,
    validate_special_shape_drawing,
    validate_special_shape_geometry,
)

ENGINE_VERSION = "2.1.0-fast-save"
PLAN_INPUT_VERSION = 1
PIECE_TYPES = {"Regular", "Clipped Corner", "Special"}
CLIPPED_CORNER_POSITIONS = {"Top Right", "Top Left", "Bottom Right", "Bottom Left"}


class DoorCuttingOrder(Document):
    def validate(self) -> None:
        """Keep ordinary saves lightweight; run the optimizer only on explicit request.

        Geometry optimization is the most expensive part of a Door Cutting Order.
        It is now separated from the ordinary Save action. Save still validates the
        document, refreshes row totals/prices and persists all edits immediately.
        The plan is recalculated only from the dedicated plan action or when the
        review workflow requires a current plan.
        """

        self._enforce_approved_immutability()
        self._set_piece_numbers()
        self._validate_numeric_inputs()
        self._validate_piece_inputs()
        self._validate_special_shape_rows()
        self._load_board_snapshot()

        settings = self._get_settings()
        self._calculate_piece_rows()
        input_fingerprint = self._plan_input_fingerprint(settings)

        if self.flags.get("force_cutting_plan_recalculation"):
            self._calculate_cutting_plan(settings, input_fingerprint)
        elif self._can_reuse_current_plan(input_fingerprint, settings):
            self._refresh_current_plan_without_optimization(settings, input_fingerprint)
        else:
            self._mark_plan_for_recalculation(settings)

    def _get_old_doc(self) -> Any | None:
        """Read the previous document at most once during one save request."""
        if self.is_new():
            return None
        if not self.flags.get("_old_doc_cache_loaded"):
            self.flags._old_doc_cache = self.get_doc_before_save()
            self.flags._old_doc_cache_loaded = True
        return self.flags.get("_old_doc_cache")

    @staticmethod
    def _get_settings() -> Any:
        return frappe.get_cached_doc("Almdina ERP Settings")

    def _enforce_approved_immutability(self) -> None:
        """Shop-floor workers keep historical records frozen; Order Entry may still edit."""
        if self.is_new() or self.flags.get("allow_approved_edit"):
            return

        old = self._get_old_doc()
        if not old:
            return

        from almdina_erp.almdina_erp.services.order_edit_policy import enforce_order_immutability_on_save

        old = self._get_old_doc()
        enforce_order_immutability_on_save(self, old)

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
        old_doc = self._get_old_doc()
        old_rows = {row.name: row for row in (old_doc.pieces or [])} if old_doc else {}
        default_edge_changed = bool(
            old_doc
            and str(old_doc.default_edge_type or "") != str(self.default_edge_type or "")
        )
        can_approve_price = has_special_price_approval_permission()
        approval_action = bool(self.flags.get("special_price_approval_action"))

        for index, row in enumerate(self.pieces or [], start=1):
            row.piece_type = row.piece_type or "Regular"
            if row.piece_type not in PIECE_TYPES:
                frappe.throw(_("Row {0}: Piece Type is invalid.").format(index))

            if row.piece_type == "Clipped Corner":
                position = row.clipped_corner_position or "Top Right"
                if position not in CLIPPED_CORNER_POSITIONS:
                    frappe.throw(
                        _("Row {0}: Clipped Corner Position is invalid.").format(index)
                    )

                piece_width = flt(row.width_cm)
                piece_length = flt(row.length_cm)
                cut_width = self._finite(
                    row.clipped_corner_width_cm,
                    _("Row {0} Clipped Corner Width CM").format(index),
                )
                cut_length = self._finite(
                    row.clipped_corner_length_cm,
                    _("Row {0} Clipped Corner Length CM").format(index),
                )

                # Live preview validates partially entered rows before the strict
                # save-time piece validator. Defer size defaults until both outer
                # dimensions exist so selecting the shape never interrupts entry.
                if piece_width > 0 and piece_length > 0:
                    if cut_width <= 0:
                        cut_width = min(max(piece_width * 0.2, 1), piece_width * 0.45)
                    if cut_length <= 0:
                        cut_length = min(max(piece_length * 0.2, 1), piece_length * 0.45)
                    if cut_width >= piece_width:
                        frappe.throw(
                            _("Row {0}: Clipped Corner Width must be smaller than the piece width.").format(
                                index
                            )
                        )
                    if cut_length >= piece_length:
                        frappe.throw(
                            _("Row {0}: Clipped Corner Length must be smaller than the piece length.").format(
                                index
                            )
                        )

                row.clipped_corner_position = position
                row.clipped_corner_width_cm = round_value(cut_width, 3)
                row.clipped_corner_length_cm = round_value(cut_length, 3)

            old_row = old_rows.get(row.name)
            drawing = validate_special_shape_drawing(row.special_shape_drawing_json)
            old_drawing = (
                validate_special_shape_drawing(old_row.special_shape_drawing_json)
                if old_row
                else None
            )
            special_geometry = (
                validate_special_shape_geometry(
                    getattr(row, "special_shape_geometry_json", ""),
                    row.width_cm,
                    row.length_cm,
                )
                if row.piece_type == "Special"
                and getattr(row, "special_shape_geometry_json", "")
                else None
            )
            old_special_geometry = (
                validate_special_shape_geometry(
                    getattr(old_row, "special_shape_geometry_json", ""),
                    old_row.width_cm,
                    old_row.length_cm,
                )
                if old_row
                and (old_row.piece_type or "Regular") == "Special"
                and getattr(old_row, "special_shape_geometry_json", "")
                else None
            )
            documentation_changed = bool(
                (old_row and old_drawing != drawing)
                or (not old_row and drawing)
                or (old_row and old_special_geometry != special_geometry)
                or (not old_row and special_geometry)
            )
            geometry_changed = bool(
                old_row
                and (
                    str(old_row.piece_type or "Regular")
                    != str(row.piece_type or "Regular")
                    or not math.isclose(
                        flt(old_row.width_cm),
                        flt(row.width_cm),
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                    or not math.isclose(
                        flt(old_row.length_cm),
                        flt(row.length_cm),
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                    or cint(old_row.qty) != cint(row.qty)
                    or str(getattr(old_row, "clipped_corner_position", "") or "")
                    != str(row.clipped_corner_position or "")
                    or not math.isclose(
                        flt(getattr(old_row, "clipped_corner_width_cm", 0)),
                        flt(row.clipped_corner_width_cm),
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                    or not math.isclose(
                        flt(getattr(old_row, "clipped_corner_length_cm", 0)),
                        flt(row.clipped_corner_length_cm),
                        rel_tol=0,
                        abs_tol=1e-9,
                    )
                    or any(
                        cint(getattr(old_row, fieldname, 0))
                        != cint(getattr(row, fieldname, 0))
                        for fieldname in (
                            "allow_rotation",
                            "edge_long_right",
                            "edge_long_left",
                            "edge_width_top",
                            "edge_width_bottom",
                        )
                    )
                    or str(old_row.edge_type or "") != str(row.edge_type or "")
                    or old_drawing != drawing
                    or old_special_geometry != special_geometry
                )
            )
            pricing_basis_changed = bool(
                geometry_changed
                or (
                    default_edge_changed
                    and row.piece_type == "Special"
                    and not row.edge_type
                )
            )

            if not can_approve_price and not approval_action:
                protected_price_changed = False
                if old_row:
                    old_approved_on = (
                        get_datetime(old_row.special_shape_price_approved_on)
                        if old_row.special_shape_price_approved_on
                        else None
                    )
                    approved_on = (
                        get_datetime(row.special_shape_price_approved_on)
                        if row.special_shape_price_approved_on
                        else None
                    )
                    protected_price_changed = bool(
                        not math.isclose(
                            flt(old_row.special_shape_custom_unit_price_usd),
                            flt(row.special_shape_custom_unit_price_usd),
                            rel_tol=0,
                            abs_tol=1e-9,
                        )
                        or any(
                            str(getattr(old_row, fieldname, "") or "")
                            != str(getattr(row, fieldname, "") or "")
                            for fieldname in (
                                "special_shape_price_status",
                                "special_shape_price_note",
                                "special_shape_price_approved_by",
                            )
                        )
                        or old_approved_on != approved_on
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
                    pricing_basis_changed
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
                            "Row {0}: you do not have permission to change or approve "
                            "the special door price."
                        ).format(index),
                        frappe.PermissionError,
                    )

            if documentation_changed:
                row.special_shape_drawing_updated_by = frappe.session.user
                row.special_shape_drawing_updated_on = now_datetime()

            if row.piece_type == "Special":
                row.special_shape_status = (
                    "Documented"
                    if special_geometry or (drawing and drawing.get("elements"))
                    else "Needs Documentation"
                )
            else:
                row.special_shape_status = "Not Required"

            if pricing_basis_changed and not approval_action:
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

    def _get_edge_rate_map(self) -> dict[str, float]:
        """Load all used edge types in one query instead of one query per row."""
        names = {
            str(edge_type)
            for edge_type in [
                self.default_edge_type,
                *(row.edge_type for row in (self.pieces or [])),
            ]
            if edge_type
        }
        if not names:
            return {}

        rows = frappe.get_all(
            "Edge Banding Type",
            filters={"name": ["in", sorted(names)]},
            fields=["name", "rate_usd_per_meter", "disabled"],
        )
        found = {row.name: row for row in rows}
        missing = sorted(names.difference(found))
        if missing:
            frappe.throw(_("Edge Banding Type {0} does not exist.").format(", ".join(missing)))

        rates: dict[str, float] = {}
        for name, row in found.items():
            if cint(row.disabled):
                frappe.throw(_("Edge Banding Type {0} is disabled.").format(name))
            rate = flt(row.rate_usd_per_meter)
            if not math.isfinite(rate) or rate < 0:
                frappe.throw(_("Edge Banding Type {0} has an invalid rate.").format(name))
            rates[name] = rate
        return rates

    def _calculate_piece_rows(self) -> None:
        total_area = 0.0
        total_edge_meters = 0.0
        total_edge_cost = 0.0
        rates = self._get_edge_rate_map()

        for row in self.pieces:
            width_cm = flt(row.width_cm)
            length_cm = flt(row.length_cm)
            qty = cint(row.qty)

            # A special door is planned as its rectangular CNC raw piece. The
            # operator's selected sides are an initial edge-banding estimate.
            long_edges = cint(row.edge_long_right) + cint(row.edge_long_left)
            width_edges = cint(row.edge_width_top) + cint(row.edge_width_bottom)

            area_m2 = (width_cm * length_cm * qty) / 10000
            edge_meters = (((length_cm * long_edges) + (width_cm * width_edges)) * qty) / 100

            effective_edge_type = row.edge_type or self.default_edge_type
            edge_rate = rates.get(effective_edge_type, 0.0) if effective_edge_type else 0.0
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

    @staticmethod
    def _normalized_number(value: Any) -> float:
        return round(flt(value), 6)

    def _plan_input_payload(self, settings: Any, source: Any | None = None) -> dict[str, Any]:
        source = source or self
        return {
            "version": PLAN_INPUT_VERSION,
            "board": {
                "item": source.board_item or "",
                "width_mm": self._normalized_number(source.full_board_width_mm),
                "length_mm": self._normalized_number(source.full_board_length_mm),
            },
            "cut": {
                "kerf_mm": self._normalized_number(source.kerf_mm),
                "trim_margin_mm": self._normalized_number(source.trim_margin_mm),
                "packing_mode": source.packing_mode or "Auto Pro",
                "machine_type": source.cutting_machine_type or "Auto",
                "time_limit_sec": self._normalized_number(source.optimization_time_limit_sec or 10),
            },
            "optimizer_settings": {
                "exact_piece_limit": cint(settings.optimal_search_piece_limit) or 40,
                "min_remnant_width_mm": self._normalized_number(settings.min_remnant_width_mm),
                "min_remnant_length_mm": self._normalized_number(settings.min_remnant_length_mm),
                "min_remnant_area_m2": self._normalized_number(settings.min_remnant_area_m2),
            },
            "pieces": [
                {
                    "index": index,
                    "width_cm": self._normalized_number(row.width_cm),
                    "length_cm": self._normalized_number(row.length_cm),
                    "qty": cint(row.qty),
                    "allow_rotation": cint(row.allow_rotation),
                }
                for index, row in enumerate(source.pieces or [], start=1)
            ],
        }

    def _plan_input_fingerprint(self, settings: Any, source: Any | None = None) -> str:
        payload = self._plan_input_payload(settings, source)
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _parse_plan_snapshot(self) -> dict[str, Any]:
        try:
            snapshot = frappe.parse_json(self.cutting_plan_json or "{}") or {}
        except Exception:
            return {}
        return snapshot if isinstance(snapshot, dict) else {}

    def _can_reuse_current_plan(self, input_fingerprint: str, settings: Any) -> bool:
        snapshot = self._parse_plan_snapshot()
        if not snapshot.get("sheets"):
            return False

        stored_fingerprint = self.calculated_plan_input_hash or snapshot.get("input_fingerprint")
        if stored_fingerprint:
            return str(stored_fingerprint) == input_fingerprint

        # One-time migration path for plans created before fingerprints existed:
        # preserve the plan when the current save did not change packing inputs.
        old_doc = self._get_old_doc()
        if not old_doc or not old_doc.cutting_plan_json:
            return False
        return self._plan_input_fingerprint(settings, old_doc) == input_fingerprint

    def _sync_snapshot_piece_metadata(
        self,
        snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Update edge/notes/special metadata without running placement again."""
        expanded = expand_piece_groups([self._piece_row_as_dict(row) for row in self.pieces])
        current_by_id = {cint(piece.get("id")): piece for piece in expanded}
        metadata_fields = (
            "label",
            "source_piece_no",
            "copy_no",
            "group_qty",
            "original_w",
            "original_h",
            "area_m2",
            "notes",
            "piece_type",
            "clipped_corner_position",
            "clipped_corner_width_cm",
            "clipped_corner_length_cm",
            "special_shape_geometry_json",
            "edge_long_right",
            "edge_long_left",
            "edge_width_top",
            "edge_width_bottom",
            "edge_type",
            "edge_rate_usd",
            "edge_cost_usd",
        )
        for sheet in snapshot.get("sheets") or []:
            for placed in sheet.get("pieces") or []:
                current = current_by_id.get(cint(placed.get("id")))
                if not current:
                    continue
                for fieldname in metadata_fields:
                    if fieldname in current:
                        placed[fieldname] = current[fieldname]

    def _set_cutting_plan_json(self, snapshot: dict[str, Any] | str) -> None:
        payload = snapshot if isinstance(snapshot, str) else frappe.as_json(snapshot)
        self.cutting_plan_json = payload
        from almdina_erp.almdina_erp.services.dual_plan_fields import set_system_plan_json_if_available

        set_system_plan_json_if_available(self, payload)

    def _refresh_costs_from_plan(self, settings: Any, snapshot: dict[str, Any]) -> None:
        required_boards = len(snapshot.get("sheets") or [])
        mdf_cost = required_boards * flt(self.board_rate_usd)
        cutting_cost = required_boards * flt(self.cutting_cost_per_board_usd)

        self.required_boards = required_boards
        self.mdf_cost_usd = round_value(mdf_cost, 3)
        self.cutting_cost_usd = round_value(cutting_cost, 3)
        self.total_cost_usd = round_value(mdf_cost + cutting_cost + flt(self.edge_cost_usd), 3)
        self.waste_area_m2 = round_value(max(0.0, flt(snapshot.get("waste_area_m2"))), 3)
        total_board_area = flt(snapshot.get("total_board_area_m2"))
        self.waste_percent = round_value(
            (flt(self.waste_area_m2) / total_board_area * 100) if total_board_area else 0,
            2,
        )
        self.packing_method = snapshot.get("method_label") or self.packing_method or ""
        self.engine_version = snapshot.get("engine_version") or ENGINE_VERSION
        self._calculate_special_shape_pricing(settings)

    def _refresh_current_plan_without_optimization(
        self,
        settings: Any,
        input_fingerprint: str,
    ) -> None:
        snapshot = self._parse_plan_snapshot()
        self._sync_snapshot_piece_metadata(snapshot)
        snapshot["input_fingerprint"] = input_fingerprint
        self.calculated_plan_input_hash = input_fingerprint
        self.plan_needs_recalculation = 0
        self._set_cutting_plan_json(snapshot)
        self._refresh_costs_from_plan(settings, snapshot)

    def _mark_plan_for_recalculation(self, settings: Any) -> None:
        """Invalidate stale layout output while keeping the ordinary save fast."""
        self.plan_needs_recalculation = 1
        self.calculated_plan_input_hash = ""
        self.cutting_plan_json = ""
        from almdina_erp.almdina_erp.services.dual_plan_fields import has_dual_plan_field

        if has_dual_plan_field("system_plan_json"):
            self.system_plan_json = ""
        self.required_boards = 0
        self.waste_area_m2 = 0
        self.waste_percent = 0
        self.mdf_cost_usd = 0
        self.cutting_cost_usd = 0
        self.total_cost_usd = 0
        self.packing_method = ""
        self.packing_score = "خطة القص تحتاج إعادة حساب"
        self.engine_version = ENGINE_VERSION
        self._calculate_special_shape_pricing(settings)

    def _calculate_cutting_plan(
        self,
        settings: Any,
        input_fingerprint: str,
    ) -> None:
        full_board_length_cm = flt(self.full_board_length_mm) / 10
        full_board_width_cm = flt(self.full_board_width_mm) / 10
        trim_cm = flt(self.trim_margin_mm) / 10
        kerf_cm = flt(self.kerf_mm) / 10

        usable_board_length_cm = full_board_length_cm - (trim_cm * 2)
        usable_board_width_cm = full_board_width_cm - (trim_cm * 2)

        piece_rows = [self._piece_row_as_dict(row) for row in self.pieces]
        expanded = expand_piece_groups(piece_rows)
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
            "input_fingerprint": input_fingerprint,
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
            "special_shape_raw_summary": self._special_shape_raw_summary(expanded, plan),
            "sheets": plan["sheets"],
            "unplaced": plan["unplaced"],
            "validation": {
                "is_valid": not validation_errors,
                "errors": validation_errors,
            },
        }
        self._set_cutting_plan_json(snapshot)
        self.calculated_plan_input_hash = input_fingerprint
        self.plan_needs_recalculation = 0

    def _calculate_special_shape_pricing(self, settings: Any) -> None:
        """Add each special row's inclusive price to the full board and cutting charges."""
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

        regular_edge_total = sum(
            flt(row.edge_cost_usd)
            for row in (self.pieces or [])
            if (row.piece_type or "Regular") != "Special"
        )
        invoice_base_total = board_and_cutting_cost + regular_edge_total
        self.special_shapes_baseline_cost_usd = round_value(baseline_total, 3)
        self.special_shapes_estimated_total_usd = round_value(estimated_total, 3)
        self.special_shapes_final_total_usd = round_value(final_total, 3)
        self.customer_quote_total_usd = round_value(invoice_base_total + final_total, 3)

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
                _("Document the special door shape before review. Missing rows: {0}.").format(
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
                    "Every special door price must be approved before "
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
            "edge_long_right": cint(row.edge_long_right),
            "edge_long_left": cint(row.edge_long_left),
            "edge_width_top": cint(row.edge_width_top),
            "edge_width_bottom": cint(row.edge_width_bottom),
            "edge_type": row.edge_type or "",
            "edge_rate_usd": flt(row.edge_rate_usd),
            "edge_cost_usd": flt(row.edge_cost_usd),
            "piece_type": row.piece_type or "Regular",
            "clipped_corner_position": row.clipped_corner_position or "",
            "clipped_corner_width_cm": flt(row.clipped_corner_width_cm),
            "clipped_corner_length_cm": flt(row.clipped_corner_length_cm),
            "special_shape_geometry_json": (
                getattr(row, "special_shape_geometry_json", "") or ""
            ),
            "notes": row.notes or "",
        }

    @staticmethod
    def _special_shape_raw_summary(
        expanded: list[dict[str, Any]],
        plan: dict[str, Any],
    ) -> dict[str, int | bool]:
        requested_ids = {
            cint(piece.get("id"))
            for piece in (expanded or [])
            if (piece.get("piece_type") or "Regular") == "Special"
        }
        placed_ids = {
            cint(piece.get("id"))
            for sheet in (plan.get("sheets") or [])
            for piece in (sheet.get("pieces") or [])
            if (piece.get("piece_type") or "Regular") == "Special"
        }
        unplaced_ids = {
            cint(piece.get("id"))
            for piece in (plan.get("unplaced") or [])
            if (piece.get("piece_type") or "Regular") == "Special"
        }
        return {
            "requested": len(requested_ids),
            "placed": len(requested_ids.intersection(placed_ids)),
            "unplaced": len(requested_ids.intersection(unplaced_ids)),
            "complete": requested_ids.issubset(placed_ids) and not unplaced_ids,
        }


@frappe.whitelist()
def recalculate_order(order_name: str) -> dict[str, Any]:
    """Run the expensive optimizer only from the explicit plan action.

    Recalculation refreshes live plan JSON and costs only. It must never approve
    the order or freeze a production Cutting Plan snapshot.
    """
    from almdina_erp.almdina_erp.services.order_edit_policy import assert_order_editable

    doc = frappe.get_doc("Door Cutting Order", order_name)
    doc.check_permission("write")
    assert_order_editable(doc)
    # Editing + recalculating invalidates any previously frozen production plan.
    if doc.approved_plan:
        doc.approved_plan = None
        doc.approved_plan_source = "System"
    doc.flags.force_cutting_plan_recalculation = True
    doc.flags.allow_approved_edit = True
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
        "plan_needs_recalculation": doc.plan_needs_recalculation,
        "approved_plan": doc.approved_plan,
        "cutting_plan_json": doc.cutting_plan_json,
    }
