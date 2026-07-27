from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from almdina_erp.almdina_erp.services.cutting_engine import round_value
from almdina_erp.almdina_erp.services.special_shape_service import (
    has_special_price_approval_role,
    validate_special_shape_drawing,
)

from .door_cutting_order import (
    CLIPPED_CORNER_POSITIONS,
    ENGINE_VERSION,
    PIECE_TYPES,
    DoorCuttingOrder as BaseDoorCuttingOrder,
)


_EDITABLE_STATES = {"Draft", "Pending Review", "Rejected"}
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
    "special_shape_status",
    "special_shape_drawing_updated_by",
    "special_shape_drawing_updated_on",
    "special_shape_custom_unit_price_usd",
    "special_shape_price_status",
    "special_shape_price_note",
    "special_shape_price_approved_by",
    "special_shape_price_approved_on",
]


class FastDoorCuttingOrder(BaseDoorCuttingOrder):
    """Performance-oriented controller for interactive factory orders.

    The base class remains the authoritative business implementation. This class
    removes work that is unnecessary during an ordinary Save: loading the whole
    previous document, repeatedly parsing the full cutting-plan JSON, validating
    unchanged drawing point arrays, and rewriting unchanged plan snapshots.
    """

    def _old_header(self) -> Any | None:
        if self.is_new():
            return None
        if not self.flags.get("_fast_old_header_loaded"):
            self.flags._fast_old_header = frappe.db.get_value(
                "Door Cutting Order",
                self.name,
                ["status", "default_edge_type"],
                as_dict=True,
            )
            self.flags._fast_old_header_loaded = True
        return self.flags.get("_fast_old_header")

    def _old_piece_map(self) -> dict[str, Any]:
        if self.is_new():
            return {}
        if not self.flags.get("_fast_old_piece_rows_loaded"):
            rows = frappe.get_all(
                "Door Cutting Order Detail",
                filters={"parent": self.name, "parenttype": "Door Cutting Order"},
                fields=_OLD_PIECE_FIELDS,
                order_by="idx asc",
            )
            self.flags._fast_old_piece_rows = {row.name: row for row in rows}
            self.flags._fast_old_piece_rows_loaded = True
        return self.flags.get("_fast_old_piece_rows") or {}

    def _enforce_approved_immutability(self) -> None:
        if self.is_new() or self.flags.get("allow_approved_edit"):
            return
        old = self._old_header()
        if not old:
            return
        from almdina_erp.almdina_erp.services.order_edit_policy import enforce_order_immutability_on_save

        enforce_order_immutability_on_save(self, old)

    @staticmethod
    def _drawing_token(raw: Any) -> str:
        if raw in (None, ""):
            return ""
        if isinstance(raw, str):
            return raw
        return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _validate_clipped_corner(self, row: Any, index: int) -> None:
        position = row.clipped_corner_position or "Top Right"
        if position not in CLIPPED_CORNER_POSITIONS:
            frappe.throw(_("Row {0}: Clipped Corner Position is invalid.").format(index))

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
        if piece_width > 0 and piece_length > 0:
            if cut_width <= 0:
                cut_width = min(max(piece_width * 0.2, 1), piece_width * 0.45)
            if cut_length <= 0:
                cut_length = min(max(piece_length * 0.2, 1), piece_length * 0.45)
            if cut_width >= piece_width:
                frappe.throw(
                    _("Row {0}: Clipped Corner Width must be smaller than the piece width.").format(index)
                )
            if cut_length >= piece_length:
                frappe.throw(
                    _("Row {0}: Clipped Corner Length must be smaller than the piece length.").format(index)
                )
        row.clipped_corner_position = position
        row.clipped_corner_width_cm = round_value(cut_width, 3)
        row.clipped_corner_length_cm = round_value(cut_length, 3)

    @staticmethod
    def _row_geometry_changed(old_row: Any, row: Any, drawing_changed: bool) -> bool:
        if not old_row:
            return False
        return bool(
            str(old_row.piece_type or "Regular") != str(row.piece_type or "Regular")
            or not math.isclose(flt(old_row.width_cm), flt(row.width_cm), rel_tol=0, abs_tol=1e-9)
            or not math.isclose(flt(old_row.length_cm), flt(row.length_cm), rel_tol=0, abs_tol=1e-9)
            or cint(old_row.qty) != cint(row.qty)
            or str(old_row.clipped_corner_position or "") != str(row.clipped_corner_position or "")
            or not math.isclose(
                flt(old_row.clipped_corner_width_cm),
                flt(row.clipped_corner_width_cm),
                rel_tol=0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                flt(old_row.clipped_corner_length_cm),
                flt(row.clipped_corner_length_cm),
                rel_tol=0,
                abs_tol=1e-9,
            )
            or any(
                cint(getattr(old_row, fieldname, 0)) != cint(getattr(row, fieldname, 0))
                for fieldname in (
                    "allow_rotation",
                    "edge_long_right",
                    "edge_long_left",
                    "edge_width_top",
                    "edge_width_bottom",
                )
            )
            or str(old_row.edge_type or "") != str(row.edge_type or "")
            or drawing_changed
        )

    @staticmethod
    def _protected_price_changed(old_row: Any, row: Any) -> bool:
        if not old_row:
            return bool(
                flt(row.special_shape_custom_unit_price_usd)
                or row.special_shape_price_status == "Approved"
                or row.special_shape_price_note
                or row.special_shape_price_approved_by
                or row.special_shape_price_approved_on
            )
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
        return bool(
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

    def _validate_special_shape_rows(self) -> None:
        """Validate only changed drawing JSON and load old child fields in one query."""
        old_rows = self._old_piece_map()
        old_header = self._old_header()
        default_edge_changed = bool(
            old_header
            and str(old_header.default_edge_type or "") != str(self.default_edge_type or "")
        )
        approval_action = bool(self.flags.get("special_price_approval_action"))
        can_approve_price: bool | None = None

        for index, row in enumerate(self.pieces or [], start=1):
            row.piece_type = row.piece_type or "Regular"
            if row.piece_type not in PIECE_TYPES:
                frappe.throw(_("Row {0}: Piece Type is invalid.").format(index))
            if row.piece_type == "Clipped Corner":
                self._validate_clipped_corner(row, index)

            old_row = old_rows.get(row.name)
            current_raw = self._drawing_token(row.special_shape_drawing_json)
            old_raw = self._drawing_token(old_row.special_shape_drawing_json) if old_row else ""
            drawing_changed = current_raw != old_raw

            # Previously stored drawings were already validated. Parsing thousands
            # of unchanged pen points on every Save was one of the largest costs.
            if current_raw and drawing_changed:
                drawing = validate_special_shape_drawing(current_raw)
                drawing_has_elements = bool(drawing and drawing.get("elements"))
            elif current_raw:
                drawing_has_elements = bool(
                    (old_row and old_row.special_shape_status == "Documented")
                    or row.special_shape_status == "Documented"
                )
            else:
                drawing_has_elements = False

            geometry_changed = self._row_geometry_changed(old_row, row, drawing_changed)
            pricing_basis_changed = bool(
                geometry_changed
                or (
                    default_edge_changed
                    and row.piece_type == "Special"
                    and not row.edge_type
                )
            )

            protected_price_changed = self._protected_price_changed(old_row, row)
            safe_geometry_invalidation = bool(
                pricing_basis_changed
                and row.special_shape_price_status in {None, "", "Estimated", "Not Applicable"}
                and not flt(row.special_shape_custom_unit_price_usd)
                and not row.special_shape_price_note
                and not row.special_shape_price_approved_by
                and not row.special_shape_price_approved_on
            )
            if protected_price_changed and not approval_action and not safe_geometry_invalidation:
                if can_approve_price is None:
                    can_approve_price = has_special_price_approval_role()
                if not can_approve_price:
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

            row.special_shape_status = (
                "Documented"
                if row.piece_type == "Special" and drawing_has_elements
                else ("Needs Documentation" if row.piece_type == "Special" else "Not Required")
            )

            if pricing_basis_changed and not approval_action:
                row.special_shape_custom_unit_price_usd = 0
                row.special_shape_price_status = (
                    "Estimated" if row.piece_type == "Special" else "Not Applicable"
                )
                row.special_shape_price_note = ""
                row.special_shape_price_approved_by = ""
                row.special_shape_price_approved_on = None

    def _plan_input_payload(self, settings: Any, source: Any | None = None) -> dict[str, Any]:
        payload = super()._plan_input_payload(settings, source)
        source = source or self
        for item, row in zip(payload.get("pieces") or [], source.pieces or []):
            item.update(
                {
                    "piece_type": row.piece_type or "Regular",
                    "clipped_corner_position": row.clipped_corner_position or "",
                    "clipped_corner_width_cm": self._normalized_number(row.clipped_corner_width_cm),
                    "clipped_corner_length_cm": self._normalized_number(row.clipped_corner_length_cm),
                }
            )
        return payload

    def _plan_metadata_payload(self) -> dict[str, Any]:
        return {
            "default_edge_type": self.default_edge_type or "",
            "edge_color": self.edge_color or "",
            "pieces": [
                {
                    "index": index,
                    "piece_type": row.piece_type or "Regular",
                    "edge_long_right": cint(row.edge_long_right),
                    "edge_long_left": cint(row.edge_long_left),
                    "edge_width_top": cint(row.edge_width_top),
                    "edge_width_bottom": cint(row.edge_width_bottom),
                    "edge_type": row.edge_type or "",
                    "edge_rate_usd": self._normalized_number(row.edge_rate_usd),
                    "edge_cost_usd": self._normalized_number(row.edge_cost_usd),
                    "area_m2": self._normalized_number(row.area_m2),
                    "notes": row.notes or "",
                    "drawing_hash": hashlib.sha256(
                        self._drawing_token(row.special_shape_drawing_json).encode("utf-8")
                    ).hexdigest(),
                    "special_shape_status": row.special_shape_status or "",
                }
                for index, row in enumerate(self.pieces or [], start=1)
            ],
        }

    def _plan_metadata_fingerprint(self) -> str:
        serialized = json.dumps(
            self._plan_metadata_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _parse_plan_snapshot(self) -> dict[str, Any]:
        raw = self.cutting_plan_json or ""
        if self.flags.get("_fast_plan_snapshot_raw") == raw:
            return self.flags.get("_fast_plan_snapshot") or {}
        snapshot = super()._parse_plan_snapshot()
        self.flags._fast_plan_snapshot_raw = raw
        self.flags._fast_plan_snapshot = snapshot
        return snapshot

    def _can_reuse_current_plan(self, input_fingerprint: str, settings: Any) -> bool:
        # Modern plans carry their layout hash in a dedicated column. Do not parse
        # a potentially large JSON document just to compare one short string.
        if self.cutting_plan_json and self.calculated_plan_input_hash:
            return str(self.calculated_plan_input_hash) == input_fingerprint
        return super()._can_reuse_current_plan(input_fingerprint, settings)

    def _refresh_costs_from_stored_summary(self, settings: Any) -> None:
        required_boards = cint(self.required_boards)
        mdf_cost = required_boards * flt(self.board_rate_usd)
        cutting_cost = required_boards * flt(self.cutting_cost_per_board_usd)
        self.mdf_cost_usd = round_value(mdf_cost, 3)
        self.cutting_cost_usd = round_value(cutting_cost, 3)
        self.total_cost_usd = round_value(mdf_cost + cutting_cost + flt(self.edge_cost_usd), 3)
        self.engine_version = self.engine_version or ENGINE_VERSION
        self._calculate_special_shape_pricing(settings)

    def _refresh_current_plan_without_optimization(
        self,
        settings: Any,
        input_fingerprint: str,
    ) -> None:
        metadata_fingerprint = self._plan_metadata_fingerprint()
        if (
            self.cutting_plan_json
            and self.calculated_plan_metadata_hash
            and str(self.calculated_plan_metadata_hash) == metadata_fingerprint
        ):
            self.calculated_plan_input_hash = input_fingerprint
            self.plan_needs_recalculation = 0
            self._refresh_costs_from_stored_summary(settings)
            return

        snapshot = self._parse_plan_snapshot()
        self._sync_snapshot_piece_metadata(snapshot)
        snapshot["input_fingerprint"] = input_fingerprint
        snapshot["metadata_fingerprint"] = metadata_fingerprint
        self.calculated_plan_input_hash = input_fingerprint
        self.calculated_plan_metadata_hash = metadata_fingerprint
        self.plan_needs_recalculation = 0
        self._set_cutting_plan_json(snapshot)
        self._refresh_costs_from_plan(settings, snapshot)

    def _calculate_cutting_plan(self, settings: Any, input_fingerprint: str) -> None:
        super()._calculate_cutting_plan(settings, input_fingerprint)
        self.calculated_plan_metadata_hash = self._plan_metadata_fingerprint()

    def _mark_plan_for_recalculation(self, settings: Any) -> None:
        super()._mark_plan_for_recalculation(settings)
        self.calculated_plan_metadata_hash = ""
