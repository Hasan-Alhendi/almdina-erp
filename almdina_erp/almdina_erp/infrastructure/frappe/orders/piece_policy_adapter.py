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
    LinerGeometryError,
    LinerPiece,
    available_liner_sides,
    contour_notch_cm,
    liner_activation_error,
    liner_centerline_mm,
    resolved_liner_span_mm,
    validation_code,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    GLASS_TYPE,
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
    validate_glass_opening,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_DOUBLE_SIDES_FIELD,
    ExtraAddonError,
    normalize_extra_double_sides,
    serialize_extra_double_sides,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.edge_profile_repository import (
    FrappeEdgeProfileRepository,
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

    MACHINING_ERROR_LABELS = {
        "missing_dimensions": "Current cutting dimensions are not valid.",
        "missing_corner": "Corner dimensions must be set before machining.",
        "invalid_corner": "Corner position is invalid.",
        "side_unavailable": "The reference side is unavailable for this piece type.",
        "offset_invalid": "Offset must be finite and zero or greater.",
        "width_invalid": "Width must be finite and greater than zero.",
        "liner_start_invalid": "Start position must be finite and zero or greater.",
        "liner_length_invalid": "Length must be finite and greater than zero.",
        "strip_outside": "Machining geometry does not fit inside the piece.",
        "liner_span_on_corner": "The machining limit falls on a corner bend.",
        "liner_flat_end_unmachinable": "A flat end cannot be machined with this bit and length.",
    }

    def __init__(
        self,
        document: Any,
        access: FrappeOrderDocumentAccess,
        edge_profiles: FrappeEdgeProfileRepository,
    ) -> None:
        self.document = document
        self.access = access
        self.edge_profiles = edge_profiles

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
            glass_margin_mm=flt(getattr(row, "glass_margin_mm", 0)),
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
        edge_break = bool(cint(getattr(row, "edge_break", 0)))
        edge_break_thickness_mm = None
        if edge_break:
            edge_type = str(
                getattr(row, "edge_type", None)
                or getattr(self.document, "default_edge_type", None)
                or ""
            ).strip()
            profile = self.edge_profiles.profiles().get(edge_type) if edge_type else None
            edge_break_thickness_mm = profile.thickness_mm if profile else None
        return contour_notch_cm(
            piece_type=row.piece_type or "Regular",
            finished_width_cm=flt(row.width_cm),
            finished_length_cm=flt(row.length_cm),
            notch_width_cm=flt(getattr(row, "clipped_corner_width_cm", 0)),
            notch_length_cm=flt(getattr(row, "clipped_corner_length_cm", 0)),
            position=str(getattr(row, "clipped_corner_position", "") or ""),
            side_thickness_mm=self._liner_side_thickness_mm(row),
            edge_break=edge_break,
            edge_break_thickness_mm=edge_break_thickness_mm,
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

    def _normalize_machining_fields(self, row: Any) -> None:
        for addon in MACHINING_ADDONS:
            if (
                not cint(getattr(row, addon.enabled_field, 0))
                or not available_liner_sides(row.piece_type or "Regular")
            ):
                self._clear_machining(row, addon)

    @staticmethod
    def _validate_double_edge_sides(row: Any, index: int) -> None:
        enabled = bool(cint(getattr(row, "extra_double", 0)))
        raw = getattr(row, EXTRA_DOUBLE_SIDES_FIELD, "")
        try:
            sides = normalize_extra_double_sides(
                raw,
                piece_type=getattr(row, "piece_type", "Regular"),
                enabled=enabled,
            )
        except ExtraAddonError as error:
            messages = {
                "double_edge_sides_invalid": _(
                    "Row {0}: Double Edge sides are invalid."
                ),
                "double_edge_sides_required": _(
                    "Row {0}: Select at least one side for Double Edge."
                ),
                "double_edge_side_unavailable": _(
                    "Row {0}: A selected Double Edge side is unavailable for this piece type."
                ),
            }
            message = messages.get(
                error.code,
                _("Row {0}: Double Edge sides are invalid."),
            )
            frappe.throw(message.format(index))
            return
        if not enabled:
            setattr(row, EXTRA_DOUBLE_SIDES_FIELD, "")
        elif str(raw or "").strip():
            setattr(row, EXTRA_DOUBLE_SIDES_FIELD, serialize_extra_double_sides(sides))

    @staticmethod
    def _addon_title(addon: Any) -> str:
        titles = {
            "liner": _("Liner"),
            "back_groove": _("Back Groove"),
            "recessed_handle_cutout": _("Recessed Handle Cutout"),
        }
        return titles.get(addon.kind, _(addon.layer))

    @staticmethod
    def _format_cm(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".") or "0"

    @staticmethod
    def _machining_number(value: Any) -> float:
        if value is None or (isinstance(value, str) and not value.strip()):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    def _throw_machining_error(
        self,
        index: int,
        addon: Any,
        code: str,
    ) -> None:
        reason = _(self.MACHINING_ERROR_LABELS.get(code, code))
        frappe.throw(
            _("Row {0}: {1} settings are invalid ({2}).").format(
                index,
                self._addon_title(addon),
                reason,
            )
        )

    def _apply_machining_addon(self, row: Any, index: int, old_row: Any, addon: Any) -> None:
        if not cint(getattr(row, addon.enabled_field, 0)):
            self._clear_machining(row, addon)
            return
        if not available_liner_sides(row.piece_type or "Regular"):
            self._clear_machining(row, addon)
            return
        side = str(getattr(row, addon.side_field, "") or "").strip()
        offset = self._machining_number(getattr(row, addon.offset_field, 0))
        width = self._machining_number(getattr(row, addon.width_field, 0))
        activation = liner_activation_error(
            enabled=True,
            piece_type=row.piece_type or "Regular",
            side=side,
            offset_cm=offset,
            width_cm=width,
            legacy_checkbox_only=self._legacy_machining_checkbox(old_row, addon),
        )
        if activation:
            frappe.throw(
                _("Row {0}: {1} needs a reference side and a width greater than zero.").format(
                    index,
                    self._addon_title(addon),
                )
            )
        if not side and offset <= 0 and width <= 0:
            return
        cut_width = getattr(row, "cut_width_cm", None)
        cut_length = getattr(row, "cut_length_cm", None)
        width_cm = flt(row.width_cm) if cut_width is None else flt(cut_width)
        length_cm = flt(row.length_cm) if cut_length is None else flt(cut_length)
        notch_width_cm, notch_length_cm = self._liner_notch_cm(row)
        piece = LinerPiece(
            piece_type=row.piece_type or "Regular",
            width_cm=width_cm,
            length_cm=length_cm,
            clipped_corner_position=str(getattr(row, "clipped_corner_position", "") or ""),
            clipped_corner_width_cm=notch_width_cm,
            clipped_corner_length_cm=notch_length_cm,
        )
        start_raw = getattr(row, addon.start_field, 0)
        length_raw = getattr(row, addon.length_field, 0)
        start_cm = self._machining_number(start_raw)
        length_cm_input = self._machining_number(length_raw)
        if not start_cm >= 0:
            self._throw_machining_error(index, addon, "liner_start_invalid")
        if length_cm_input < 0:
            self._throw_machining_error(index, addon, "liner_length_invalid")
        code = validation_code(piece, side, offset, width)
        if code:
            self._throw_machining_error(index, addon, code)
        start_mm, _length_mm, span_error = resolved_liner_span_mm(
            piece,
            side,
            start_cm,
            length_cm_input,
        )
        if span_error == "liner_span_exceeds_edge":
            _edge_start_mm, edge_mm, _edge_error = resolved_liner_span_mm(
                piece,
                side,
                0,
                None,
            )
            available_cm = edge_mm / 10
            maximum_cm = max(0.0, available_cm - start_mm / 10)
            frappe.throw(
                _(
                    "Row {0}: {1} length exceeds the reference side "
                    "(available {2} cm, start {3} cm, entered {4} cm, maximum {5} cm)."
                ).format(
                    index,
                    self._addon_title(addon),
                    self._format_cm(available_cm),
                    self._format_cm(start_cm),
                    self._format_cm(length_cm_input),
                    self._format_cm(maximum_cm),
                )
            )
        if span_error:
            self._throw_machining_error(index, addon, span_error)
        try:
            liner_centerline_mm(
                piece,
                side,
                offset,
                width,
                start_cm,
                length_cm_input,
            )
        except LinerGeometryError as error:
            self._throw_machining_error(index, addon, error.code)

    def validate_machining_rows(self) -> None:
        old_rows = self.access.old_piece_map()
        for index, row in enumerate(self.document.pieces or [], start=1):
            self._apply_liner_parameters(row, index, old_rows.get(row.name))

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

        for index, row in enumerate(self.document.pieces or [], start=1):
            row.piece_type = row.piece_type or "Regular"
            if row.piece_type not in PIECE_TYPES:
                frappe.throw(_("Row {0}: Piece Type is invalid.").format(index))
            if row.piece_type == GLASS_TYPE:
                self._validate_glass_opening(row, index)
            if is_corner_cut(row.piece_type):
                self._validate_clipped_corner(row, index)
            self._validate_double_edge_sides(row, index)
            self._apply_edge_break(row)
            self._apply_special_measurement_edges(row)
            self._normalize_machining_fields(row)

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
                frappe.throw(
                    _(
                        "Row {0}: Special prices must be saved from the Cost edit session."
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

    @staticmethod
    def _validate_glass_opening(row: Any, index: int) -> None:
        try:
            validate_glass_opening(
                outer_width_cm=getattr(row, "width_cm", 0),
                outer_length_cm=getattr(row, "length_cm", 0),
                glass_margin_mm=getattr(row, "glass_margin_mm", None),
            )
        except PiecePolicyError as error:
            if error.code == "glass_margin_must_be_positive":
                frappe.throw(
                    _(
                        "Row {0}: Glass margin must be greater than zero."
                    ).format(index)
                )
            if error.code == "glass_opening_must_be_positive":
                frappe.throw(
                    _(
                        "Row {0}: The inner glass opening must have a positive width and length."
                    ).format(index)
                )
            raise

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
