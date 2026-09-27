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
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    PlanSettingsValidationError,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    decision_from_values,
    validate_source_resource_homogeneity,
)
from almdina_erp.almdina_erp.domain.cutting.physical_execution_contract import (
    is_legacy_physical_execution_snapshot,
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
        self._validate_source_type()
        self._validate_revision_parent()
        self._validate_working_settings()
        self.score = max(-MAX_STORED_SCORE, min(MAX_STORED_SCORE, flt(self.score)))
        self._populate_source_identity_snapshots()
        self._validate_offcut_contract()
        if self.validation_status in {"Valid", "Invalid"} and not self.validated_on:
            self.validated_on = now_datetime()
        self._enforce_snapshot_immutability()

    def _validate_source_type(self) -> None:
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
        """Enforce the same PlanSettings contract for every Frappe save path."""

        try:
            settings = normalize_plan_settings(
                optimization_mode=self.optimization_mode,
                machine_type=self.machine_type,
                optimization_time_limit_sec=self.optimization_time_limit_sec,
                kerf_mm=self.kerf_mm,
                preferred_trim_mm=self.trim_margin_mm,
            )
        except PlanSettingsValidationError:
            frappe.throw(_("Invalid Cutting Plan settings."), frappe.ValidationError)
            raise AssertionError("unreachable")

        self.optimization_mode = settings.optimization_mode
        self.machine_type = settings.machine_type
        self.optimization_time_limit_sec = settings.optimization_time_limit_sec
        self.kerf_mm = settings.kerf_mm
        self.trim_margin_mm = settings.preferred_trim_mm

    def _populate_source_identity_snapshots(self) -> None:
        order = frappe.get_doc("Door Cutting Order", self.door_cutting_order)
        for source in self.sources or []:
            source.board_description = str(
                source.board_description
                or self.board_description
                or order.board_description
                or ""
            ).strip()

    def _validate_offcut_contract(self) -> None:
        """Validate OFFCUT classification server-side for every save path."""
        try:
            snapshot = frappe.parse_json(self.snapshot_json or "{}") or {}
        except Exception:
            snapshot = {}
        # Historical immutable snapshots without any stable physical identities
        # are display/cost compatible only. They never enter the modern OFFCUT
        # contract, and no data is synthesized or persisted on their behalf.
        if is_legacy_physical_execution_snapshot(snapshot):
            return
        identities: set[str] = set()
        full_board_sources = 0
        pieces_by_source: dict[str, list[dict[str, object]]] = {}
        for piece in self.placed_pieces or []:
            pieces_by_source.setdefault(str(piece.sheet_no), []).append(
                {
                    "piece_instance_id": getattr(piece, "piece_instance_id", ""),
                    "resource_kind": getattr(piece, "resource_kind", None),
                    "offcut_source_party": getattr(piece, "offcut_source_party", None),
                    "offcut_execution_party": getattr(piece, "offcut_execution_party", None),
                }
            )
        try:
            validate_source_resource_homogeneity(
                [
                    {"pieces": pieces_by_source.get(str(source.sheet_no), [])}
                    for source in (self.sources or [])
                ]
            )
        except OffcutPolicyError as exc:
            frappe.throw(
                _(
                    "لا يمكن أن يحتوي نفس مصدر القص على قطع نقص وقطع من لوح كامل. "
                    "ضع قطع OFFCUT كمصدر مستقل عن ألواح MDF الكاملة."
                ),
                frappe.ValidationError,
            )
            raise AssertionError("unreachable") from exc

        for source in self.sources or []:
            try:
                decision = decision_from_values(
                    getattr(source, "resource_kind", None),
                    getattr(source, "offcut_source_party", None),
                    getattr(source, "offcut_execution_party", None),
                )
            except OffcutPolicyError as exc:
                frappe.throw(_("تركيبة مصدر وتنفيذ النقص غير صالحة: {0}").format(exc), frappe.ValidationError)
                raise AssertionError("unreachable")
            source.resource_kind = decision.resource_kind.value
            source.offcut_source_party = decision.source_party.value
            source.offcut_execution_party = decision.execution_party.value
            full_board_sources += int(decision.consumes_full_board)

        for piece in self.placed_pieces or []:
            identity = str(getattr(piece, "piece_instance_id", "") or "").strip()
            if not identity:
                frappe.throw(
                    _(
                        "لا يمكن حفظ خطة القص لأن إحدى القطع الفيزيائية بلا هوية ثابتة. "
                        "أعد حساب الخطة أو أعد رفع DXF من الطلب المحفوظ."
                    ),
                    frappe.ValidationError,
                )
            if identity in identities:
                frappe.throw(_("تكررت هوية القطعة الفيزيائية {0}.").format(identity), frappe.ValidationError)
            identities.add(identity)
            try:
                decision = decision_from_values(
                    getattr(piece, "resource_kind", None),
                    getattr(piece, "offcut_source_party", None),
                    getattr(piece, "offcut_execution_party", None),
                )
            except OffcutPolicyError as exc:
                frappe.throw(_("تركيبة مصدر وتنفيذ النقص غير صالحة: {0}").format(exc), frappe.ValidationError)
                raise AssertionError("unreachable")
            piece.resource_kind = decision.resource_kind.value
            piece.offcut_source_party = decision.source_party.value
            piece.offcut_execution_party = decision.execution_party.value
        if self.sources:
            self.required_boards = full_board_sources

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
