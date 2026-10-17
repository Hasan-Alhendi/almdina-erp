from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from almdina_erp.almdina_erp.domain.cutting import round_value
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    MACHINING_ADDONS_BY_KIND,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    available_liner_sides,
    contour_notch_cm,
    liner_activation_error,
    resolved_liner_span_mm,
    validation_code,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    PIECE_TYPES,
    PieceGeometry,
    PiecePolicyError,
    SpecialPrice,
    apply_edge_break_policy,
    apply_special_measurement_edge_policy,
    drawing_token,
    evaluate_special_shape,
    is_corner_cut,
    pending_custom_edge_price_labels,
    reset_price_values,
    resolve_clipped_corner,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
)
from almdina_erp.almdina_erp.services.special_shape_drawing_validation_service import (
    validate_special_shape_drawing,
)
from almdina_erp.almdina_erp.services.special_shape_service import (
    validate_special_shape_geometry,
)

from .document_access import FrappeOrderDocumentAccess


class FrappeOrderPiecePolicyAdapter:
    """Translate Frappe child rows to pure piece-policy decisions."""

    def __init__(
        self,
        document: Any,
        access: FrappeOrderDocumentAccess,
    ) -> None:
        self.document = document
        self.access = access

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
            edge_break=cint(getattr(row, "edge_break", 0)),
            edge_break_only=cint(getattr(row, "edge_break_only", 0)),
            edge_type=str(getattr(row, "edge_type", None) or ""),
        )

    @staticmethod
    def _apply_edge_break(row: Any) -> None:
        try:
            decision = apply_edge_break_policy(
                piece_type=str(getattr(row, "piece_type", None) or "Regular"),
                clipped_corner_position=str(
                    getattr(row, "clipped_corner_position", None) or ""
                ),
                edge_break=cint(getattr(row, "edge_break", 0)),
                edge_break_only=cint(getattr(row, "edge_break_only", 0)),
                edge_long_right=cint(getattr(row, "edge_long_right", 0)),
                edge_long_left=cint(getattr(row, "edge_long_left", 0)),
                edge_width_top=cint(getattr(row, "edge_width_top", 0)),
                edge_width_bottom=cint(getattr(row, "edge_width_bottom", 0)),
            )
        except PiecePolicyError as error:
            if error.code == "mutually_exclusive_corner_edge_options":
                frappe.throw(
                    _(
                        "Full corner-path banding and break-only banding cannot be selected together."
                    )
                )
            raise
        row.edge_break = decision.edge_break
        row.edge_break_only = decision.edge_break_only
        row.edge_long_right = decision.edge_long_right
        row.edge_long_left = decision.edge_long_left
        row.edge_width_top = decision.edge_width_top
        row.edge_width_bottom = decision.edge_width_bottom
        for side in decision.cleared_sides:
            override = f"{side}_type_override"
            if hasattr(row, override):
                setattr(row, override, None)

    @staticmethod
    def _apply_special_measurement_edges(row: Any) -> None:
        decision = apply_special_measurement_edge_policy(
            piece_type=str(getattr(row, "piece_type", None) or "Regular"),
        )
        if not decision.disabled:
            return
        row.edge_long_right = decision.edge_long_right
        row.edge_long_left = decision.edge_long_left
        row.edge_width_top = decision.edge_width_top
        row.edge_width_bottom = decision.edge_width_bottom
        row.edge_break = decision.edge_break
        row.edge_break_only = decision.edge_break_only
        row.edge_type = decision.edge_type or None
        for field, value in (
            ("edge_long_right_type_override", decision.edge_long_right_type_override),
            ("edge_long_left_type_override", decision.edge_long_left_type_override),
            ("edge_width_top_type_override", decision.edge_width_top_type_override),
            ("edge_width_bottom_type_override", decision.edge_width_bottom_type_override),
        ):
            if hasattr(row, field):
                setattr(row, field, value or None)

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

    @staticmethod
    def _required_price_capability(old_row: Any | None) -> str:
        return (
            Capability.EDIT_SPECIAL_PRICE
            if old_row
            and str(old_row.special_shape_price_status or "") == "Approved"
            else Capability.APPROVE_SPECIAL_PRICE
        )

    def _validate_clipped_corner(self, row: Any, index: int) -> None:
        try:
            result = resolve_clipped_corner(
                position=row.clipped_corner_position,
                piece_width_cm=flt(row.width_cm),
                piece_length_cm=flt(row.length_cm),
                cut_width_cm=self.access.finite(
                    row.clipped_corner_width_cm,
                    _("Row {0} Clipped Corner Width CM").format(index),
                ),
                cut_length_cm=self.access.finite(
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
                    "Row {0}: Clipped Corner Width must be smaller than the piece "
                    "width."
                ).format(index),
                "clipped_corner_length_too_large": _(
                    "Row {0}: Clipped Corner Length must be smaller than the piece "
                    "length."
                ).format(index),
            }
            frappe.throw(messages[error.code])

        row.clipped_corner_position = result.position
        row.clipped_corner_width_cm = round_value(result.width_cm, 3)
        row.clipped_corner_length_cm = round_value(result.length_cm, 3)

    @staticmethod
    def _validated_special_geometry(row: Any | None) -> dict[str, Any] | None:
        if not row or str(getattr(row, "piece_type", None) or "Regular") != "Special":
            return None
        raw_geometry = getattr(row, "special_shape_geometry_json", "") or ""
        if not raw_geometry:
            return None
        return validate_special_shape_geometry(
            raw_geometry,
            getattr(row, "width_cm", 0),
            getattr(row, "length_cm", 0),
        )

    def _legacy_liner_checkbox(self, old_row: Any) -> bool:
        return self._legacy_machining_checkbox(old_row, MACHINING_ADDONS_BY_KIND["liner"])

    def _legacy_machining_checkbox(self, old_row: Any, addon: Any) -> bool:
        if old_row is None or not cint(getattr(old_row, addon.enabled_field, 0)):
            return False
        return (
            not str(getattr(old_row, addon.side_field, "") or "").strip()
            and flt(getattr(old_row, addon.offset_field, 0)) <= 0
            and flt(getattr(old_row, addon.width_field, 0)) <= 0
        )

    def _clear_machining(self, row: Any, addon: Any) -> None:
        setattr(row, addon.side_field, "")
        setattr(row, addon.offset_field, 0)
        setattr(row, addon.width_field, 0)
        setattr(row, addon.start_field, 0)
        setattr(row, addon.length_field, 0)

    def _liner_notch_cm(self, row: Any) -> tuple[float, float]:
        return contour_notch_cm(
            piece_type=row.piece_type or "Regular",
            finished_width_cm=flt(row.width_cm),
            finished_length_cm=flt(row.length_cm),
            notch_width_cm=flt(getattr(row, "clipped_corner_width_cm", 0)),
            notch_length_cm=flt(getattr(row, "clipped_corner_length_cm", 0)),
            position=str(getattr(row, "clipped_corner_position", "") or ""),
            side_thickness_mm=self._liner_side_thickness_mm(row),
            edge_break=bool(cint(getattr(row, "edge_break", 0))),
            edge_break_thickness_mm=getattr(row, "edge_break_thickness_mm", None),
        )

    def _liner_side_thickness_mm(self, row: Any) -> dict[str, float]:
        long_thickness = flt(getattr(row, "edge_long_thickness_mm", 0))
        width_thickness = flt(getattr(row, "edge_width_thickness_mm", 0))
        return {
            "long_right": long_thickness if cint(getattr(row, "edge_long_right", 0)) else 0,
            "long_left": long_thickness if cint(getattr(row, "edge_long_left", 0)) else 0,
            "width_top": width_thickness if cint(getattr(row, "edge_width_top", 0)) else 0,
            "width_bottom": width_thickness if cint(getattr(row, "edge_width_bottom", 0)) else 0,
        }

    def _apply_liner_parameters(self, row: Any, index: int, old_row: Any) -> None:
        for addon in MACHINING_ADDONS:
            self._apply_machining_addon(row, index, old_row, addon)

    def _apply_machining_addon(self, row: Any, index: int, old_row: Any, addon: Any) -> None:
        if not cint(getattr(row, addon.enabled_field, 0)):
            self._clear_machining(row, addon)
            return
        if not available_liner_sides(row.piece_type or "Regular"):
            self._clear_machining(row, addon)
            return
        side = str(getattr(row, addon.side_field, "") or "").strip()
        offset = flt(getattr(row, addon.offset_field, 0))
        width = flt(getattr(row, addon.width_field, 0))
        activation = liner_activation_error(
            enabled=True,
            piece_type=row.piece_type or "Regular",
            side=side,
            offset_cm=offset,
            width_cm=width,
            legacy_checkbox_only=self._legacy_machining_checkbox(old_row, addon),
        )
        if activation:
            if addon.kind == "liner":
                frappe.throw(
                    _("Row {0}: Liner needs a reference side and a width greater than zero.").format(index)
                )
            frappe.throw(
                _("Row {0}: Machining add-on needs a reference side and a width greater than zero.").format(index)
            )
        if not side and offset <= 0 and width <= 0:
            return
        width_cm = flt(getattr(row, "cut_width_cm", 0)) or flt(row.width_cm)
        length_cm = flt(getattr(row, "cut_length_cm", 0)) or flt(row.length_cm)
        notch_width_cm, notch_length_cm = self._liner_notch_cm(row)
        piece = LinerPiece(
            piece_type=row.piece_type or "Regular",
            width_cm=width_cm,
            length_cm=length_cm,
            clipped_corner_position=str(getattr(row, "clipped_corner_position", "") or ""),
            clipped_corner_width_cm=notch_width_cm,
            clipped_corner_length_cm=notch_length_cm,
        )
        code = validation_code(piece, side, offset, width)
        if code:
            if addon.kind == "liner":
                frappe.throw(
                    _("Row {0}: Liner settings are invalid ({1}).").format(index, code)
                )
            frappe.throw(
                _("Row {0}: Machining add-on settings are invalid ({1}).").format(index, code)
            )
        _start_mm, _length_mm, span_error = resolved_liner_span_mm(
            piece,
            side,
            flt(getattr(row, addon.start_field, 0)),
            flt(getattr(row, addon.length_field, 0)),
        )
        if span_error:
            if addon.kind == "liner":
                frappe.throw(
                    _("Row {0}: Liner settings are invalid ({1}).").format(index, span_error)
                )
            frappe.throw(
                _("Row {0}: Machining add-on settings are invalid ({1}).").format(index, span_error)
            )

    def validate_rows(self) -> None:
        old_rows = self.access.old_piece_map()
        old_header = self.access.old_header()
        default_edge_changed = bool(
            old_header
            and str(old_header.default_edge_type or "")
            != str(self.document.default_edge_type or "")
        )
        approval_action = bool(
            self.document.flags.get("special_price_approval_action")
        )
        permission_cache: dict[str, bool] = {}

        for index, row in enumerate(self.document.pieces or [], start=1):
            row.piece_type = row.piece_type or "Regular"
            if row.piece_type not in PIECE_TYPES:
                frappe.throw(_("Row {0}: Piece Type is invalid.").format(index))
            self._apply_liner_parameters(row, index, old_rows.get(row.name))
            if is_corner_cut(row.piece_type):
                self._validate_clipped_corner(row, index)
            self._apply_edge_break(row)
            self._apply_special_measurement_edges(row)

            old_row = old_rows.get(row.name)
            current_raw = drawing_token(row.special_shape_drawing_json)
            old_raw = (
                drawing_token(old_row.special_shape_drawing_json)
                if old_row
                else ""
            )
            drawing_changed = current_raw != old_raw

            if current_raw and drawing_changed:
                drawing = validate_special_shape_drawing(current_raw)
                drawing_has_elements = bool(
                    drawing
                    and (drawing.get("reference") or drawing.get("elements"))
                )
            elif current_raw:
                drawing_has_elements = bool(
                    (old_row and old_row.special_shape_status == "Documented")
                    or row.special_shape_status == "Documented"
                )
            else:
                drawing_has_elements = False

            special_geometry = self._validated_special_geometry(row)
            old_special_geometry = self._validated_special_geometry(old_row)
            geometry_payload_changed = bool(
                old_row and old_special_geometry != special_geometry
            )
            documentation_changed = bool(drawing_changed)

            decision = evaluate_special_shape(
                old_geometry=self._geometry_snapshot(old_row),
                current_geometry=(
                    self._geometry_snapshot(row) or PieceGeometry()
                ),
                old_price=self._price_snapshot(old_row),
                current_price=self._price_snapshot(row) or SpecialPrice(),
                drawing_changed=bool(drawing_changed or geometry_payload_changed),
                drawing_has_elements=bool(drawing_has_elements),
                default_edge_changed=default_edge_changed,
                approval_action=approval_action,
            )

            if decision.requires_price_permission:
                capability = self._required_price_capability(old_row)
                if capability not in permission_cache:
                    permission_cache[capability] = document_has_capability(
                        self.document,
                        capability,
                    )
                if not permission_cache[capability]:
                    frappe.throw(
                        _(
                            "Row {0}: you do not have permission to approve or edit "
                            "the special door price."
                        ).format(index),
                        frappe.PermissionError,
                    )

            if documentation_changed:
                row.special_shape_drawing_updated_by = frappe.session.user
                row.special_shape_drawing_updated_on = now_datetime()

            row.special_shape_status = decision.documentation_status
            if decision.reset_price:
                for fieldname, value in reset_price_values(
                    row.piece_type
                ).items():
                    setattr(row, fieldname, value)

    def ensure_documented(self) -> None:
        missing = [
            str(row.piece_no or row.idx)
            for row in (self.document.pieces or [])
            if (row.piece_type or "Regular") == "Special"
            and row.special_shape_status != "Documented"
        ]
        if missing:
            frappe.throw(
                _(
                    "Document the special door shape before review. Missing rows: "
                    "{0}."
                ).format(", ".join(missing))
            )

    def ensure_custom_edge_prices(self) -> None:
        pending = pending_custom_edge_price_labels(self.document.pieces or [])
        if pending:
            frappe.throw(
                _(
                    "أدخل السعر الخاص الشامل للدرف الخاصة وسعر قشاط درف "
                    "الزاوية الكسر وزاوية L قبل الحفظ أو طباعة الفاتورة. "
                    "المتبقي: {0}."
                ).format("، ".join(pending))
            )

    def ensure_prices_approved(self) -> None:
        self.ensure_custom_edge_prices()


__all__ = ["FrappeOrderPiecePolicyAdapter"]
