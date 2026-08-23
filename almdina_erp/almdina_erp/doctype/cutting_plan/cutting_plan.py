from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    CANCELLED,
    DRAFT,
    SUPERSEDED,
    UPLOADED_DXF,
    CuttingPlanLifecycleError,
    normalize_source_type,
)


# Float fields are stored as decimal(21,9); engine scores must stay inside it.
MAX_STORED_SCORE = 10**12 - 1
IMMUTABLE_STATUSES = {APPROVED, SUPERSEDED, CANCELLED}


class CuttingPlan(Document):
    """Canonical cutting-plan aggregate.

    Draft plans own editable optimizer settings and working geometry. Approved
    plans are immutable production snapshots. Any later change is represented by
    a new Draft revision linked through ``based_on_plan``.
    """

    def validate(self) -> None:
        if self.revision and self.revision < 1:
            frappe.throw(_("Cutting Plan revision must be at least 1."))
        if self.plan_kind == "Replacement" and not self.replacement_piece:
            frappe.throw(_("A Replacement cutting plan must reference its Replacement Piece."))
        self._validate_source_type()
        self._validate_revision_parent()
        self._validate_working_settings()
        self.score = max(-MAX_STORED_SCORE, min(MAX_STORED_SCORE, flt(self.score)))
        self._populate_source_identity_snapshots()
        if self.plan_kind == "Replacement":
            self._validate_replacement_plan()
        if self.validation_status in {"Valid", "Invalid"} and not self.validated_on:
            self.validated_on = now_datetime()
        self._enforce_snapshot_immutability()

    def _validate_source_type(self) -> None:
        if self.plan_kind == "Replacement":
            return
        # Historical Custom DXF callers set plan_kind but had no first-class
        # source_type field. Normalize that path into the new aggregate contract
        # while A2 migrates those callers to Cutting Plan commands directly.
        if self.plan_kind == "Custom DXF" and str(self.source_type or "") in {"", "System"}:
            self.source_type = UPLOADED_DXF
        try:
            self.source_type = normalize_source_type(self.source_type)
        except CuttingPlanLifecycleError:
            frappe.throw(_("Unsupported Cutting Plan source type."))

    def _validate_revision_parent(self) -> None:
        parent_name = str(getattr(self, "based_on_plan", None) or "").strip()
        if not parent_name:
            return
        parent = frappe.db.get_value(
            "Cutting Plan",
            parent_name,
            ["door_cutting_order", "revision", "status"],
            as_dict=True,
        )
        if not parent:
            frappe.throw(_("The source Cutting Plan revision does not exist."))
        if str(parent.door_cutting_order or "") != str(self.door_cutting_order or ""):
            frappe.throw(_("The source Cutting Plan revision belongs to another order."))

        # Creating a revision is allowed only from the currently Approved plan;
        # that invariant is also enforced by the application create-revision use
        # case. After the child exists, its immutable lineage remains valid when
        # the parent later becomes Superseded or Cancelled as part of normal
        # approval replacement/cancellation. Re-validating an existing child must
        # therefore accept all immutable historical parent states.
        if self.is_new() and parent.status != APPROVED:
            frappe.throw(_("A new Cutting Plan revision must be based on an approved plan."))
        if not self.is_new() and parent.status not in IMMUTABLE_STATUSES:
            frappe.throw(_("A Cutting Plan revision must reference an immutable historical plan."))
        if cint(self.revision) <= cint(parent.revision):
            frappe.throw(_("The new Cutting Plan revision must be newer than its source revision."))

    def _validate_working_settings(self) -> None:
        for fieldname, label in (
            ("kerf_mm", _("Kerf MM")),
            ("trim_margin_mm", _("Trim Margin MM")),
            ("optimization_time_limit_sec", _("Optimization Time Limit Sec")),
        ):
            value = flt(getattr(self, fieldname, 0))
            if value < 0:
                frappe.throw(_("{0} cannot be negative.").format(label))

    def _populate_source_identity_snapshots(self) -> None:
        order = frappe.get_doc("Door Cutting Order", self.door_cutting_order)
        for source in self.sources or []:
            source.board_description = str(
                source.board_description
                or self.board_description
                or order.board_description
                or ""
            ).strip()

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
        expected_board = str(order.board_description or "").strip()
        if str(replacement.board_description or "").strip() != expected_board:
            errors.append(_("Replacement board description does not match the order."))
        if str(self.board_description or "").strip() != expected_board:
            errors.append(_("Replacement Cutting Plan board description does not match the order."))

        if self.sources and self.placed_pieces:
            source = self.sources[0]
            piece = self.placed_pieces[0]
            tolerance = 0.001

            if str(source.board_description or "").strip() != expected_board:
                errors.append(_("Replacement source board description does not match the order."))

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

        snapshot = frappe.parse_json(self.snapshot_json or "{}") or {}
        if snapshot.get("unplaced"):
            errors.append(_("Replacement plan contains unplaced pieces."))

        self.validation_status = "Invalid" if errors else "Valid"
        self.validation_errors = "\n".join(errors)
        if errors:
            frappe.throw(_("Invalid Replacement Mini Cutting Plan:\n{0}").format("\n".join(errors)))

    def _enforce_snapshot_immutability(self) -> None:
        if self.is_new() or self.flags.get("allow_status_transition"):
            return

        old = self.get_doc_before_save()
        if not old:
            return

        if old.status in IMMUTABLE_STATUSES:
            frappe.throw(
                _(
                    "Cutting Plan {0} is immutable. Create a new Draft revision instead of editing it."
                ).format(self.name)
            )

        if old.status != DRAFT:
            frappe.throw(_("Only Draft Cutting Plans can be edited."))
