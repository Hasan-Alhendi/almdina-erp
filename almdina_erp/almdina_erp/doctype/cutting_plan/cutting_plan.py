from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime


class CuttingPlan(Document):
    def validate(self) -> None:
        if self.revision and self.revision < 1:
            frappe.throw(_("Cutting Plan revision must be at least 1."))
        if self.plan_kind == "Replacement" and not self.replacement_piece:
            frappe.throw(_("A Replacement cutting plan must reference its Replacement Piece."))
        self._populate_source_identity_snapshots()
        if self.plan_kind == "Replacement":
            self._validate_replacement_plan()
        if self.validation_status in {"Valid", "Invalid"} and not self.validated_on:
            self.validated_on = now_datetime()
        self._enforce_approved_immutability()

    def _populate_source_identity_snapshots(self) -> None:
        order = frappe.get_doc("Door Cutting Order", self.door_cutting_order)
        for source in self.sources or []:
            if source.source_type == "Remnant" and source.remnant:
                remnant = frappe.db.get_value(
                    "Board Remnant",
                    source.remnant,
                    ["board_item", "material", "color", "thickness_mm"],
                    as_dict=True,
                )
                if remnant:
                    source.board_item = source.board_item or remnant.board_item
                    source.material = remnant.material or ""
                    source.color = remnant.color or ""
                    source.thickness_mm = flt(remnant.thickness_mm)
                    continue

            source.board_item = source.board_item or order.board_item
            source.material = order.board_material or ""
            source.color = order.board_color or ""
            source.thickness_mm = flt(order.board_thickness_mm)

    def _validate_replacement_plan(self) -> None:
        errors: list[str] = []
        if len(self.sources or []) != 1:
            errors.append(_("Replacement Mini Cutting Plan must contain exactly one physical source."))
        if len(self.placed_pieces or []) != 1:
            errors.append(_("Replacement Mini Cutting Plan must contain exactly one placed replacement piece."))

        replacement = frappe.get_doc("Replacement Piece", self.replacement_piece)
        order = frappe.get_doc("Door Cutting Order", self.door_cutting_order)
        if replacement.door_cutting_order != self.door_cutting_order:
            errors.append(_("Replacement Piece belongs to a different Door Cutting Order."))
        if replacement.board_item != self.board_item:
            errors.append(_("Replacement Piece board item does not match the Cutting Plan board item."))

        if self.sources and self.placed_pieces:
            source = self.sources[0]
            piece = self.placed_pieces[0]
            tolerance = 0.001

            if source.board_item and source.board_item != replacement.board_item:
                errors.append(_("Replacement source board item does not match the required board item."))
            if (source.material or "") != (order.board_material or ""):
                errors.append(_("Replacement source material does not match the order material snapshot."))
            if (source.color or "") != (order.board_color or ""):
                errors.append(_("Replacement source color does not match the order color snapshot."))
            if abs(flt(source.thickness_mm) - flt(order.board_thickness_mm)) > tolerance:
                errors.append(_("Replacement source thickness does not match the order thickness snapshot."))

            usable_w = flt(source.usable_width_mm)
            usable_h = flt(source.usable_length_mm)
            x = flt(piece.x_mm)
            y = flt(piece.y_mm)
            width = flt(piece.width_mm)
            height = flt(piece.height_mm)
            if x < -tolerance or y < -tolerance or x + width > usable_w + tolerance or y + height > usable_h + tolerance:
                errors.append(_("Replacement piece exceeds the usable source bounds."))

            original_w = flt(replacement.width_cm) * 10
            original_h = flt(replacement.length_cm) * 10
            normal = abs(width - original_w) <= tolerance and abs(height - original_h) <= tolerance
            rotated = (
                cint(replacement.allow_rotation)
                and abs(width - original_h) <= tolerance
                and abs(height - original_w) <= tolerance
            )
            if not (normal or rotated):
                errors.append(_("Replacement piece dimensions/orientation do not match the approved request."))
            if cint(piece.rotated) and not cint(replacement.allow_rotation):
                errors.append(_("Replacement piece is rotated although rotation is not allowed."))

            if source.source_type == "Remnant":
                if not source.remnant:
                    errors.append(_("A Remnant source must reference a Board Remnant."))
                else:
                    remnant = frappe.db.get_value(
                        "Board Remnant",
                        source.remnant,
                        ["board_item", "width_mm", "length_mm", "status", "reserved_for_order", "material", "color", "thickness_mm"],
                        as_dict=True,
                    )
                    if not remnant:
                        errors.append(_("Referenced Board Remnant does not exist."))
                    else:
                        if remnant.board_item != replacement.board_item:
                            errors.append(_("Referenced Board Remnant does not match the replacement board item."))
                        if (remnant.material or "") != (order.board_material or ""):
                            errors.append(_("Referenced Board Remnant material does not match the order snapshot."))
                        if (remnant.color or "") != (order.board_color or ""):
                            errors.append(_("Referenced Board Remnant color does not match the order snapshot."))
                        if abs(flt(remnant.thickness_mm) - flt(order.board_thickness_mm)) > tolerance:
                            errors.append(_("Referenced Board Remnant thickness does not match the order snapshot."))
                        if abs(flt(remnant.width_mm) - flt(source.full_width_mm)) > tolerance or abs(flt(remnant.length_mm) - flt(source.full_length_mm)) > tolerance:
                            errors.append(_("Replacement plan source dimensions do not match the referenced Board Remnant."))
                        if remnant.status not in {"Available", "Reserved"}:
                            errors.append(_("Referenced Board Remnant is not available/reserved for use."))

        snapshot = frappe.parse_json(self.snapshot_json or "{}") or {}
        if snapshot.get("unplaced"):
            errors.append(_("Replacement plan contains unplaced pieces."))

        self.validation_status = "Invalid" if errors else "Valid"
        self.validation_errors = "\n".join(errors)
        if errors:
            frappe.throw(_("Invalid Replacement Mini Cutting Plan:\n{0}").format("\n".join(errors)))

    def on_update(self) -> None:
        if self.status != "Approved" or (self.plan_kind or "Order") != "Order":
            return

        old = self.get_doc_before_save()
        became_approved = self.is_new() or not old or old.status != "Approved"
        if not became_approved:
            return

        settings = frappe.get_single("Almdina ERP Settings")
        if cint(settings.reserve_stock_on_approval):
            from almdina_erp.almdina_erp.services.stock_service import create_order_reservation

            create_order_reservation(self.door_cutting_order)

    def _enforce_approved_immutability(self) -> None:
        if self.is_new() or self.flags.get("allow_status_transition"):
            return

        old = self.get_doc_before_save()
        if not old:
            return

        if old.status == "Approved":
            frappe.throw(
                _(
                    "Approved Cutting Plan {0} is immutable. Create a new revision instead of editing it."
                ).format(self.name)
            )
