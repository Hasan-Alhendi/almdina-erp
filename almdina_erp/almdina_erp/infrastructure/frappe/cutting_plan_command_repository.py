from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.cutting.plan_revisions import (
    CreatePlanRevisionCommand,
    PlanRecord,
    PlanSettings,
    create_revision,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import settings_for_system_search
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    BOARD_EDITOR,
    CANCELLED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
    next_revision,
    revision_from_lineage_source,
    select_newer_draft_of_source,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_context import (
    PLAN_COMMAND_FLAG,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    COST_SNAPSHOT_VERSION,
    PLAN_COST_FIELDS,
    initial_plan_cost_values,
    persist_plan_cost_snapshot,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    plan_settings as read_plan_settings,
    seed_plan_settings,
    manufacturing_plan_settings,
)


class FrappeCuttingPlanCommandRepository:
    """Persistence adapter for command-owned Cutting Plan mutations.

    The adapter never bypasses Frappe document permissions. The related order
    capability is authorized before this repository is used, then carried only
    in ephemeral ``Document.flags`` while the native insert/save operation runs.

    Plan financial fields intentionally live at permission level 1. After a
    trusted command saves one Draft whose server-calculated cost snapshot is
    current, the repository persists that protected snapshot through the narrow
    costing infrastructure boundary. This keeps plan editors unable to edit cost
    inputs while ensuring geometry changes immediately refresh derived totals.
    """

    def __init__(self, capability: str):
        self.capability = str(capability or "").strip()

    @staticmethod
    def _settings(plan: Any) -> PlanSettings:
        return read_plan_settings(plan)

    @classmethod
    def _record(cls, plan: Any) -> PlanRecord:
        return PlanRecord(
            name=plan.name,
            order_name=plan.door_cutting_order,
            revision=cint(plan.revision),
            status=str(plan.status or ""),
            source_type=str(plan.source_type or SYSTEM),
            based_on_plan=str(plan.based_on_plan or "") or None,
            settings=cls._settings(plan),
        )

    @staticmethod
    def _current_cost_snapshot(plan: Any) -> dict[str, float | int] | None:
        if (
            str(getattr(plan, "status", None) or "") != DRAFT
            or cint(getattr(plan, "cost_snapshot_version", 0)) < COST_SNAPSHOT_VERSION
        ):
            return None
        return {
            "cost_snapshot_version": COST_SNAPSHOT_VERSION,
            **{
                fieldname: flt(getattr(plan, fieldname, 0))
                for fieldname in PLAN_COST_FIELDS
            },
        }

    def _run_persist(
        self,
        plan: Any,
        operation: str,
        *,
        allow_status_transition: bool = False,
    ) -> Any:
        protected_cost_snapshot = self._current_cost_snapshot(plan)
        plan.flags[PLAN_COMMAND_FLAG] = self.capability
        if allow_status_transition:
            plan.flags.allow_status_transition = True
        try:
            if operation == "insert":
                plan.insert()
            else:
                plan.save()
        finally:
            plan.flags.pop(PLAN_COMMAND_FLAG, None)
            if allow_status_transition:
                plan.flags.pop("allow_status_transition", None)

        if protected_cost_snapshot is not None:
            # Frappe field-level permission sanitization may restore permlevel-1
            # values on the in-memory document. Reapply only the snapshot that
            # the already-authorized server command calculated before save.
            for fieldname, value in protected_cost_snapshot.items():
                setattr(plan, fieldname, value)
            persist_plan_cost_snapshot(plan)
        return plan

    def get_document(self, plan_name: str) -> Any:
        return frappe.get_doc("Cutting Plan", plan_name)

    def get(self, plan_name: str) -> PlanRecord:
        return self._record(self.get_document(plan_name))

    def create_draft(
        self,
        *,
        order_name: str,
        revision: int,
        status: str,
        source_type: str,
        based_on_plan: str | None,
        settings: PlanSettings,
    ) -> PlanRecord:
        plan = frappe.new_doc("Cutting Plan")
        plan.plan_kind = "Order"
        plan.source_type = source_type or SYSTEM
        plan.door_cutting_order = order_name
        plan.revision = max(1, cint(revision))
        plan.based_on_plan = based_on_plan
        plan.status = status or DRAFT
        if plan.source_type == SYSTEM:
            settings = settings_for_system_search(settings)
        plan.optimization_mode = settings.optimization_mode
        plan.machine_type = settings.machine_type
        plan.optimization_time_limit_sec = settings.optimization_time_limit_sec
        plan.kerf_mm = settings.kerf_mm
        plan.trim_margin_mm = settings.preferred_trim_mm
        plan.deduct_edge_thickness = 1 if settings.deduct_edge_thickness else 0
        self._assign_tool_diameters(
            plan,
            kerf_mm=settings.kerf_mm,
            based_on_plan=based_on_plan,
        )
        for fieldname, value in initial_plan_cost_values(
            order_name,
            based_on_plan=based_on_plan,
        ).items():
            setattr(plan, fieldname, value)
        plan.plan_needs_recalculation = 1
        self._run_persist(plan, "insert")
        return self._record(plan)

    def _assign_tool_diameters(self, plan: Any, *, kerf_mm: float, based_on_plan: str | None) -> None:
        from almdina_erp.almdina_erp.domain.cutting.tool_diameters import initial_diameters

        lineage = None
        if based_on_plan and frappe.db.exists("Cutting Plan", based_on_plan):
            lineage = frappe.get_doc("Cutting Plan", based_on_plan)
        factory = None if lineage is not None else frappe.get_cached_doc("Almdina ERP Settings")
        for fieldname, value in initial_diameters(
            kerf_mm=kerf_mm,
            lineage=lineage,
            factory=factory,
        ).items():
            if value is not None:
                setattr(plan, fieldname, value)

    def save_settings(self, plan_name: str, settings: PlanSettings) -> PlanRecord:
        plan = self.get_document(plan_name)
        plan.optimization_mode = settings.optimization_mode
        plan.machine_type = settings.machine_type
        plan.optimization_time_limit_sec = settings.optimization_time_limit_sec
        plan.kerf_mm = settings.kerf_mm
        plan.trim_margin_mm = settings.preferred_trim_mm
        plan.deduct_edge_thickness = 1 if settings.deduct_edge_thickness else 0
        plan.plan_needs_recalculation = 1
        self._run_persist(plan, "save")
        return self._record(plan)

    def save_document(
        self,
        plan: Any,
        *,
        allow_status_transition: bool = False,
    ) -> Any:
        return self._run_persist(
            plan,
            "save",
            allow_status_transition=allow_status_transition,
        )

    @staticmethod
    def _latest_plan_row(order_name: str, **filters: Any) -> dict[str, Any] | None:
        resolved_filters = {"door_cutting_order": order_name, **filters}
        rows = frappe.get_all(
            "Cutting Plan",
            filters=resolved_filters,
            fields=["name", "revision", "status", "source_type"],
            order_by="revision desc, creation desc",
            limit_page_length=1,
        )
        return rows[0] if rows else None

    def latest_document(
        self,
        order_name: str,
        *,
        source_type: str | None = None,
        status: str | None = None,
    ) -> Any | None:
        filters: dict[str, Any] = {"plan_kind": "Order"}
        if source_type:
            filters["source_type"] = source_type
        if status:
            filters["status"] = status
        row = self._latest_plan_row(order_name, **filters)
        return self.get_document(row["name"]) if row else None

    def approved_documents(self, order_name: str, *, exclude: str | None = None) -> list[Any]:
        filters: dict[str, Any] = {
            "door_cutting_order": order_name,
            "plan_kind": "Order",
            "status": APPROVED,
        }
        if exclude:
            filters["name"] = ["!=", exclude]
        names = frappe.get_all(
            "Cutting Plan",
            filters=filters,
            pluck="name",
            order_by="revision asc, creation asc",
        )
        return [self.get_document(name) for name in names]

    def ensure_system_draft(self, order: Any) -> Any:
        current = self._latest_plan_row(
            order.name,
            plan_kind="Order",
            source_type=SYSTEM,
            status=DRAFT,
        )
        if current:
            return self.get_document(current["name"])

        latest_any = self._latest_plan_row(order.name, plan_kind="Order")
        latest_approved = self._latest_plan_row(
            order.name,
            plan_kind="Order",
            status=APPROVED,
        )
        next_revision = (cint(latest_any.get("revision")) + 1) if latest_any else 1

        if latest_approved:
            approved = self.get_document(latest_approved["name"])
            created = create_revision(
                CreatePlanRevisionCommand(
                    approved_plan_name=approved.name,
                    source_type=SYSTEM,
                ),
                self,
            )
            return self.get_document(created.name)

        created = self.create_draft(
            order_name=order.name,
            revision=next_revision,
            status=DRAFT,
            source_type=SYSTEM,
            based_on_plan=None,
            settings=seed_plan_settings(order.name),
        )
        return self.get_document(created.name)

    def ensure_uploaded_dxf_draft(self, order: Any) -> Any:
        """Return the editable Uploaded DXF revision for the current order.

        Switching plan source never mutates an approved revision. A new Draft is
        based on the latest approved plan for lineage, while working optimizer
        settings come from canonical Cutting Plan lineage or factory defaults.
        """

        current = self._latest_plan_row(
            order.name,
            plan_kind="Order",
            source_type=UPLOADED_DXF,
            status=DRAFT,
        )
        if current:
            return self.get_document(current["name"])

        latest_any = self._latest_plan_row(order.name, plan_kind="Order")
        latest_approved = self._latest_plan_row(
            order.name,
            plan_kind="Order",
            status=APPROVED,
        )
        next_revision_number = (cint(latest_any.get("revision")) + 1) if latest_any else 1
        based_on = latest_approved["name"] if latest_approved else None
        created = self.create_draft(
            order_name=order.name,
            revision=next_revision_number,
            status=DRAFT,
            source_type=UPLOADED_DXF,
            based_on_plan=based_on,
            # The imported geometry is validated against the current manufacturing
            # settings, not a cancelled Uploaded DXF revision's old trim.
            settings=manufacturing_plan_settings(order.name),
        )
        return self.get_document(created.name)

    def _order_plan_rows(self, order_name: str) -> list[dict[str, Any]]:
        return frappe.get_all(
            "Cutting Plan",
            filters={"door_cutting_order": order_name, "plan_kind": "Order"},
            fields=["name", "revision", "status", "source_type", "modified"],
            order_by="revision desc, modified desc",
        )

    def find_newer_draft(
        self,
        order_name: str,
        *,
        source_type: str,
        min_revision: int,
    ) -> Any | None:
        newer = select_newer_draft_of_source(
            self._order_plan_rows(order_name),
            source_type=source_type,
            min_revision=min_revision,
        )
        if not newer:
            return None
        name = str(newer.get("name") if isinstance(newer, dict) else getattr(newer, "name", "") or "")
        return self.get_document(name) if name else None

    def latest_cancelled_document(
        self,
        order_name: str,
        *,
        source_type: str,
    ) -> Any | None:
        row = self._latest_plan_row(
            order_name,
            plan_kind="Order",
            source_type=source_type,
            status=CANCELLED,
        )
        return self.get_document(row["name"]) if row else None

    def create_geometry_preserving_draft(
        self,
        source_plan: Any,
        *,
        order: Any | None = None,
    ) -> Any:
        """Copy one immutable tip into a new Draft without rerunning the engine.

        The source revision stays untouched. Geometry, fingerprints, DXF metadata,
        child tables, and the trusted cost snapshot are preserved. Freshness is
        re-checked against the current order so a drifted tip is marked stale and
        cannot be re-approved until the operator recalculates or re-uploads.
        """

        source_name = str(getattr(source_plan, "name", None) or "").strip()
        order_name = str(getattr(source_plan, "door_cutting_order", None) or "").strip()
        source_type = str(getattr(source_plan, "source_type", None) or SYSTEM).strip() or SYSTEM
        source_status = str(getattr(source_plan, "status", None) or "").strip()
        source_revision = cint(getattr(source_plan, "revision", 0))
        if not source_name or not order_name:
            raise ValueError("geometry_copy_requires_named_plan")

        existing = self.find_newer_draft(
            order_name,
            source_type=source_type,
            min_revision=source_revision,
        )
        if existing:
            return existing

        rows = self._order_plan_rows(order_name)
        tip_revision = next_revision(
            [cint(row.get("revision")) for row in rows if cint(row.get("revision"))]
        )
        lineage = revision_from_lineage_source(
            current_name=source_name,
            current_revision=source_revision,
            current_status=source_status,
            source_type=source_type,
            next_revision_number=tip_revision,
        )

        draft = frappe.copy_doc(source_plan)
        draft.status = DRAFT
        draft.revision = lineage.revision
        draft.based_on_plan = lineage.based_on_plan
        draft.source_type = lineage.source_type
        draft.approved_by = None
        draft.approved_on = None
        # Keep stored fingerprints/geometry. Freshness below may mark stale.
        draft.plan_needs_recalculation = cint(
            getattr(source_plan, "plan_needs_recalculation", 0)
        )
        self._run_persist(draft, "insert")

        if lineage.source_type == BOARD_EDITOR:
            self._copy_board_editor_drawings(
                order_name=order_name,
                source_plan_name=source_name,
                target_plan_name=draft.name,
                source_input_fingerprint=str(
                    getattr(source_plan, "input_fingerprint", None) or ""
                ),
                source_content_revision=str(getattr(source_plan, "revision", "") or ""),
            )

        # Re-apply the copied cost snapshot through the costing boundary so
        # permlevel-1 fields survive insert for operators without financial edit.
        if cint(getattr(draft, "cost_snapshot_version", 0)) >= COST_SNAPSHOT_VERSION:
            persist_plan_cost_snapshot(draft)

        self._apply_post_copy_freshness(order or order_name, draft)
        return self.get_document(draft.name)

    def ensure_geometry_draft_from_cancelled(
        self,
        order: Any,
        *,
        source_type: str,
    ) -> Any | None:
        """Recover one working Draft from the latest Cancelled tip of ``source_type``."""

        current = self.latest_document(
            order.name,
            source_type=source_type,
            status=DRAFT,
        )
        if current:
            return current
        cancelled = self.latest_cancelled_document(order.name, source_type=source_type)
        if not cancelled:
            return None
        return self.create_geometry_preserving_draft(cancelled, order=order)

    def _apply_post_copy_freshness(self, order: Any | str, plan: Any) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
            plan_fingerprint_compatibility,
        )

        order_doc = (
            order
            if not isinstance(order, str)
            else frappe.get_doc("Door Cutting Order", order)
        )
        stored = str(getattr(plan, "input_fingerprint", None) or "")
        decision = plan_fingerprint_compatibility(order_doc, plan, stored)
        needs_recalculation = bool(
            cint(getattr(plan, "plan_needs_recalculation", 0)) or not decision.compatible
        )
        if bool(cint(getattr(plan, "plan_needs_recalculation", 0))) == needs_recalculation:
            return
        plan.plan_needs_recalculation = 1 if needs_recalculation else 0
        frappe.db.set_value(
            "Cutting Plan",
            plan.name,
            "plan_needs_recalculation",
            plan.plan_needs_recalculation,
            update_modified=False,
        )

    @staticmethod
    def _copy_board_editor_drawings(
        *,
        order_name: str,
        source_plan_name: str,
        target_plan_name: str,
        source_input_fingerprint: str,
        source_content_revision: str,
    ) -> None:
        from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
            DrawingDocumentError,
            document_fingerprint,
        )
        from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_copy import (
            clone_drawing_document,
        )
        from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import (
            drawing_key,
        )
        from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_drawing_store import (
            FrappeBoardEditorDrawingStore,
            drawing_storage_ready,
        )

        if not drawing_storage_ready():
            return
        store = FrappeBoardEditorDrawingStore()
        records = store.read_for_plan(order_name, source_plan_name)
        if not records:
            return
        for record in records:
            piece_id = str(record.get("piece_instance_id") or "").strip()
            document = record.get("drawing_json")
            if not piece_id or not isinstance(document, dict):
                continue
            try:
                cloned = clone_drawing_document(document, piece_id)
            except DrawingDocumentError:
                continue
            store.insert(
                {
                    "drawing_key": drawing_key(order_name, target_plan_name, piece_id),
                    "door_cutting_order": order_name,
                    "source_plan": target_plan_name,
                    "piece_instance_id": piece_id,
                    "source_input_fingerprint": source_input_fingerprint
                    or str(record.get("source_input_fingerprint") or ""),
                    "source_content_revision": source_content_revision
                    or str(record.get("source_content_revision") or ""),
                    "drawing_version": 1,
                    "document_fingerprint": document_fingerprint(cloned),
                    "drawing_json": cloned,
                    "prior_drawing_archive_json": [],
                }
            )


__all__ = ["FrappeCuttingPlanCommandRepository"]
