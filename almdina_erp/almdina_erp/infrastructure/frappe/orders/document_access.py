from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.orders.numeric_input import (
    default_if_missing,
)


_OLD_PIECE_FIELDS = [
    "name",
    "piece_type",
    "width_cm",
    "length_cm",
    "qty",
    "allow_rotation",
    "clipped_corner_position",
    "clipped_corner_width_cm",
    "clipped_corner_length_cm",
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
    "edge_type",
    "special_shape_drawing_json",
    "special_shape_geometry_json",
    "special_shape_status",
    "special_shape_drawing_updated_by",
    "special_shape_drawing_updated_on",
    "special_shape_custom_unit_price_usd",
    "special_shape_price_status",
    "special_shape_price_note",
    "special_shape_price_approved_by",
    "special_shape_price_approved_on",
    "extra_double",
    "extra_double_unit_price_usd",
    "extra_liner",
    "extra_liner_unit_price_usd",
    "extra_recessed_handle_cutout",
    "extra_recessed_handle_cutout_unit_price_usd",
]


class FrappeOrderDocumentAccess:
    """Own framework reads, writes, caches, and basic input validation."""

    def __init__(self, document: Any) -> None:
        self.document = document

    @property
    def settings(self) -> Any:
        flags = self.document.flags
        if not flags.get("_order_settings_loaded"):
            flags._order_settings = frappe.get_cached_doc("Almdina ERP Settings")
            flags._order_settings_loaded = True
        return flags.get("_order_settings")

    def old_header(self) -> Any | None:
        if self.document.is_new():
            return None
        flags = self.document.flags
        if not flags.get("_order_old_header_loaded"):
            flags._order_old_header = frappe.db.get_value(
                "Door Cutting Order",
                self.document.name,
                ["status", "default_edge_type"],
                as_dict=True,
            )
            flags._order_old_header_loaded = True
        return flags.get("_order_old_header")

    def old_piece_map(self) -> dict[str, Any]:
        if self.document.is_new():
            return {}
        flags = self.document.flags
        if not flags.get("_order_old_piece_rows_loaded"):
            rows = frappe.get_all(
                "Door Cutting Order Detail",
                filters={
                    "parent": self.document.name,
                    "parenttype": "Door Cutting Order",
                },
                fields=_OLD_PIECE_FIELDS,
                order_by="idx asc",
            )
            flags._order_old_piece_rows = {row.name: row for row in rows}
            flags._order_old_piece_rows_loaded = True
        return flags.get("_order_old_piece_rows") or {}

    def old_document(self) -> Any | None:
        """Load the complete previous document only for the legacy plan path."""

        if self.document.is_new():
            return None
        flags = self.document.flags
        if not flags.get("_order_old_doc_loaded"):
            flags._order_old_doc = self.document.get_doc_before_save()
            flags._order_old_doc_loaded = True
        return flags.get("_order_old_doc")

    @staticmethod
    def finite(value: Any, label: str) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            frappe.throw(_("{0} must be a valid numeric value.").format(label))
        if not math.isfinite(number):
            frappe.throw(
                _("{0} must be finite; NaN/Infinity are not allowed.").format(label)
            )
        return number

    @staticmethod
    def normalized_number(value: Any) -> float:
        return round(flt(value), 6)

    def enforce_immutability(self) -> None:
        if self.document.is_new() or self.document.flags.get("allow_approved_edit"):
            return
        old = self.old_header()
        if not old:
            return
        from almdina_erp.almdina_erp.services.order_edit_policy import (
            enforce_order_immutability_on_save,
        )

        enforce_order_immutability_on_save(self.document, old)

    def set_piece_numbers(self) -> None:
        for index, row in enumerate(self.document.pieces or [], start=1):
            row.piece_no = index

    def validate_numeric_inputs(self) -> None:
        kerf = self.finite(self.document.kerf_mm, _("Kerf (MM)"))
        trim = self.finite(self.document.trim_margin_mm, _("Trim Margin (MM)"))
        board_rate = self.finite(self.document.board_rate_usd, _("Board Rate USD"))
        cutting_cost = self.finite(
            self.document.cutting_cost_per_board_usd,
            _("Cutting Cost / Board USD"),
        )
        time_limit = self.finite(
            default_if_missing(
                self.document.optimization_time_limit_sec,
                10,
            ),
            _("Optimization Time Limit (Sec)"),
        )

        if kerf < 0:
            frappe.throw(_("Kerf (MM) cannot be negative."))
        if trim < 0:
            frappe.throw(_("Trim Margin (MM) cannot be negative."))
        if board_rate < 0:
            frappe.throw(_("Board Rate USD cannot be negative."))
        if cutting_cost < 0:
            frappe.throw(_("Cutting Cost / Board USD cannot be negative."))
        if time_limit <= 0 or time_limit > 120:
            frappe.throw(
                _(
                    "Optimization Time Limit must be greater than 0 and no more than "
                    "120 seconds."
                )
            )

    def validate_piece_inputs(self) -> None:
        if not self.document.pieces:
            frappe.throw(_("At least one piece row is required."))

        for index, row in enumerate(self.document.pieces or [], start=1):
            width = self.finite(
                row.width_cm,
                _("Row {0} Width CM").format(index),
            )
            length = self.finite(
                row.length_cm,
                _("Row {0} Length CM").format(index),
            )
            qty = self.finite(
                row.qty,
                _("Row {0} Quantity").format(index),
            )
            if width <= 0:
                frappe.throw(
                    _("Row {0}: Width must be greater than zero.").format(index)
                )
            if length <= 0:
                frappe.throw(
                    _("Row {0}: Length must be greater than zero.").format(index)
                )
            if qty <= 0 or qty != int(qty):
                frappe.throw(
                    _("Row {0}: Quantity must be a positive integer.").format(index)
                )

    def load_board_snapshot(self) -> None:
        description = str(
            getattr(self.document, "board_description", "") or ""
        ).strip()
        if not description:
            frappe.throw(_("Board description is required."))

        length_cm = self.finite(
            default_if_missing(
                getattr(self.document, "board_length_cm", None),
                244,
            ),
            _("Board Length (CM)"),
        )
        width_cm = self.finite(
            default_if_missing(
                getattr(self.document, "board_width_cm", None),
                122,
            ),
            _("Board Width (CM)"),
        )
        if length_cm <= 0:
            frappe.throw(_("Board Length (CM) must be greater than zero."))
        if width_cm <= 0:
            frappe.throw(_("Board Width (CM) must be greater than zero."))

        self.document.board_description = description
        self.document.board_length_cm = length_cm
        self.document.board_width_cm = width_cm
        self.document.full_board_length_mm = length_cm * 10
        self.document.full_board_width_mm = width_cm * 10

        trim_mm = flt(self.document.trim_margin_mm)
        usable_length_mm = self.document.full_board_length_mm - (trim_mm * 2)
        usable_width_mm = self.document.full_board_width_mm - (trim_mm * 2)
        if usable_length_mm <= 0 or usable_width_mm <= 0:
            frappe.throw(_("Trim Margin leaves no usable board area."))

    def edge_rate_map(self) -> dict[str, float]:
        names = {
            str(edge_type)
            for edge_type in [
                self.document.default_edge_type,
                *(row.edge_type for row in (self.document.pieces or [])),
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
            frappe.throw(
                _("Edge Banding Type {0} does not exist.").format(
                    ", ".join(missing)
                )
            )

        rates: dict[str, float] = {}
        for name, row in found.items():
            if cint(row.disabled):
                frappe.throw(_("Edge Banding Type {0} is disabled.").format(name))
            rate = flt(row.rate_usd_per_meter)
            if not math.isfinite(rate) or rate < 0:
                frappe.throw(
                    _("Edge Banding Type {0} has an invalid rate.").format(name)
                )
            rates[name] = rate
        return rates

    def parse_plan_snapshot(self) -> dict[str, Any]:
        raw = self.document.cutting_plan_json or ""
        flags = self.document.flags
        if flags.get("_order_plan_snapshot_raw") == raw:
            return flags.get("_order_plan_snapshot") or {}
        try:
            snapshot = frappe.parse_json(raw or "{}") or {}
        except Exception:
            snapshot = {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        flags._order_plan_snapshot_raw = raw
        flags._order_plan_snapshot = snapshot
        return snapshot

    def set_plan_snapshot(self, snapshot: dict[str, Any] | str) -> None:
        payload = snapshot if isinstance(snapshot, str) else frappe.as_json(snapshot)
        self.document.cutting_plan_json = payload
        if self.document.meta.has_field("system_plan_json"):
            self.document.system_plan_json = payload
        self.document.flags._order_plan_snapshot_raw = payload
        self.document.flags._order_plan_snapshot = (
            snapshot if isinstance(snapshot, dict) else None
        )

    def clear_system_plan_if_available(self) -> None:
        if self.document.meta.has_field("system_plan_json"):
            self.document.system_plan_json = ""


__all__ = ["FrappeOrderDocumentAccess"]
