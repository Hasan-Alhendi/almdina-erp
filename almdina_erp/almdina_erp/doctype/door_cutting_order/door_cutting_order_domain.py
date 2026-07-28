from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    PIECE_TYPES,
    PieceGeometry,
    PiecePolicyError,
    SpecialPrice,
    drawing_token,
    evaluate_special_shape,
    geometry_changed,
    protected_price_changed,
    reset_price_values,
    resolve_clipped_corner,
)
from almdina_erp.almdina_erp.services.cutting_engine import round_value
from almdina_erp.almdina_erp.services.special_shape_service import (
    has_special_price_approval_role,
    validate_special_shape_drawing,
)

from .door_cutting_order_text_board import TextBoardDoorCuttingOrder


class DomainDoorCuttingOrder(TextBoardDoorCuttingOrder):
    """Active controller with door-piece business rules delegated to Domain."""

    @staticmethod
    def _drawing_token(raw: Any) -> str:
        return drawing_token(raw)

    @staticmethod
    def _geometry_snapshot(row: Any | None) -> PieceGeometry | None:
        if not row:
            return None
        return PieceGeometry(
            piece_type=str(getattr(row, "piece_type", None) or "Regular"),
            width_cm=flt(getattr(row, "width_cm", 0)),
            length_cm=flt(getattr(row, "length_cm", 0)),
            qty=cint(getattr(row, "qty", 0)),
            allow_rotation=cint(getattr(row, "allow_rotation", 0)),
            clipped_corner_position=str(
                getattr(row, "clipped_corner_position", None) or ""
            ),
            clipped_corner_width_cm=flt(
                getattr(row, "clipped_corner_width_cm", 0)
            ),
            clipped_corner_length_cm=flt(
                getattr(row, "clipped_corner_length_cm", 0)
            ),
            edge_long_right=cint(getattr(row, "edge_long_right", 0)),
            edge_long_left=cint(getattr(row, "edge_long_left", 0)),
            edge_width_top=cint(getattr(row, "edge_width_top", 0)),
            edge_width_bottom=cint(getattr(row, "edge_width_bottom", 0)),
            edge_type=str(getattr(row, "edge_type", None) or ""),
        )

    @staticmethod
    def _price_snapshot(row: Any | None) -> SpecialPrice | None:
        if not row:
            return None
        approved_on = getattr(row, "special_shape_price_approved_on", None)
        return SpecialPrice(
            unit_price_usd=flt(
                getattr(row, "special_shape_custom_unit_price_usd", 0)
            ),
            status=str(getattr(row, "special_shape_price_status", None) or ""),
            note=str(getattr(row, "special_shape_price_note", None) or ""),
            approved_by=str(
                getattr(row, "special_shape_price_approved_by", None) or ""
            ),
            approved_on=get_datetime(approved_on) if approved_on else None,
        )

    def _validate_clipped_corner(self, row: Any, index: int) -> None:
        try:
            result = resolve_clipped_corner(
                position=row.clipped_corner_position,
                piece_width_cm=flt(row.width_cm),
                piece_length_cm=flt(row.length_cm),
                cut_width_cm=self._finite(
                    row.clipped_corner_width_cm,
                    _("Row {0} Clipped Corner Width CM").format(index),
                ),
                cut_length_cm=self._finite(
                    row.clipped_corner_length_cm,
                    _("Row {0} Clipped Corner Length CM").format(index),
                ),
            )
        except PiecePolicyError as error:
            messages = {
                "invalid_clipped_corner_position": _(
                    "Row {0}: Clipped Corner Position is invalid."
                ).format(index),
                "clipped_corner_width_too_large": _(
                    "Row {0}: Clipped Corner Width must be smaller than the piece width."
                ).format(index),
                "clipped_corner_length_too_large": _(
                    "Row {0}: Clipped Corner Length must be smaller than the piece length."
                ).format(index),
            }
            frappe.throw(messages[error.code])

        row.clipped_corner_position = result.position
        row.clipped_corner_width_cm = round_value(result.width_cm, 3)
        row.clipped_corner_length_cm = round_value(result.length_cm, 3)

    @classmethod
    def _row_geometry_changed(
        cls,
        old_row: Any,
        row: Any,
        drawing_changed: bool,
    ) -> bool:
        return geometry_changed(
            cls._geometry_snapshot(old_row),
            cls._geometry_snapshot(row),
            drawing_changed=drawing_changed,
        )

    @classmethod
    def _protected_price_changed(cls, old_row: Any, row: Any) -> bool:
        return protected_price_changed(
            cls._price_snapshot(old_row),
            cls._price_snapshot(row) or SpecialPrice(),
        )

    def _validate_special_shape_rows(self) -> None:
        """Adapt Frappe rows to pure special-shape and pricing decisions."""

        old_rows = self._old_piece_map()
        old_header = self._old_header()
        default_edge_changed = bool(
            old_header
            and str(old_header.default_edge_type or "")
            != str(self.default_edge_type or "")
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
            old_raw = (
                self._drawing_token(old_row.special_shape_drawing_json)
                if old_row
                else ""
            )
            drawing_changed = current_raw != old_raw

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

            decision = evaluate_special_shape(
                old_geometry=self._geometry_snapshot(old_row),
                current_geometry=self._geometry_snapshot(row) or PieceGeometry(),
                old_price=self._price_snapshot(old_row),
                current_price=self._price_snapshot(row) or SpecialPrice(),
                drawing_changed=drawing_changed,
                drawing_has_elements=drawing_has_elements,
                default_edge_changed=default_edge_changed,
                approval_action=approval_action,
            )

            if decision.requires_price_permission:
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

            row.special_shape_status = decision.documentation_status

            if decision.reset_price:
                for fieldname, value in reset_price_values(row.piece_type).items():
                    setattr(row, fieldname, value)


__all__ = ["DomainDoorCuttingOrder"]
