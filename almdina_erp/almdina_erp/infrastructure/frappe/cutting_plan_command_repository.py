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
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_context import (
    PLAN_COMMAND_FLAG,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    initial_plan_cost_values,
)


class FrappeCuttingPlanCommandRepository:
    """Persistence adapter for command-owned Cutting Plan mutations.

    The adapter never bypasses Frappe permissions. The related order capability
    is authorized before this repository is used, then carried only in ephemeral
    Document.flags while the native insert/save operation runs.
    """

    def __init__(self, capability: str):
        self.capability = str(capability or "").strip()

    @staticmethod
    def _settings(plan: Any) -> PlanSettings:
        return PlanSettings(
            optimization_mode=str(plan.optimization_mode or "Auto Pro"),
            machine_type=str(plan.machine_type or "Auto"),
            optimization_time_limit_sec=flt(plan.optimization_time_limit_sec),
            kerf_mm=flt(plan.kerf_mm),
            trim_margin_mm=flt(plan.trim_margin_mm),
        )

    @staticmethod
    def _settings_from_order(order: Any) -> PlanSettings:
        return PlanSettings(
            optimization_mode=str(getattr(order, "packing_mode", None) or "Auto Pro"),
            machine_type=str(getattr(order, "cutting_machine_type", None) or "Auto"),
            optimization_time_limit_sec=flt(
                getattr(order, "optimization_time_limit_sec", 0)
            )
            or 10,
            kerf_mm=flt(getattr(order, "kerf_mm", 0)) or 3,
            trim_margin_mm=flt(getattr(order, "trim_margin_mm", 0)) or 5,
        )

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

    def _run_persist(
        self,
        plan: Any,
        operation: str,
        *,
        allow_status_transition: bool = False,
    ) -> Any:
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
        plan.optimization_mode = settings.optimization_mode
        plan.machine_type = settings.machine_type
        plan.optimization_time_limit_sec = settings.optimization_time_limit_sec
        plan.kerf_mm = settings.kerf_mm
        plan.trim_margin_mm = settings.trim_margin_mm
        for fieldname, value in initial_plan_cost_values(
            order_name,
            based_on_plan=based_on_plan,
        ).items():
            setattr(plan, fieldname, value)
        plan.plan_needs_recalculation = 1
        self._run_persist(plan, "insert")
        return self._record(plan)

    def save_settings(self, plan_name: str, settings: PlanSettings) -> PlanRecord:
        plan = self.get_document(plan_name)
        plan.optimization_mode = settings.optimization_mode
        plan.machine_type = settings.machine_type
        plan.optimization_time_limit_sec = settings.optimization_time_limit_sec
        plan.kerf_mm = settings.kerf_mm
        plan.trim_margin_mm = settings.trim_margin_mm
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
            settings=self._settings_from_order(order),
        )
        return self.get_document(created.name)

    def ensure_uploaded_dxf_draft(self, order: Any) -> Any:
        """Return the editable Uploaded DXF revision for the current order.

        Switching plan source never mutates an approved revision. A new Draft is
        based on the latest approved plan for lineage, while its working settings
        come from the current DCO compatibility projection used by the DXF parser.
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
        next_revision = (cint(latest_any.get("revision")) + 1) if latest_any else 1
        based_on = latest_approved["name"] if latest_approved else None
        created = self.create_draft(
            order_name=order.name,
            revision=next_revision,
            status=DRAFT,
            source_type=UPLOADED_DXF,
            based_on_plan=based_on,
            settings=self._settings_from_order(order),
        )
        return self.get_document(created.name)


__all__ = ["FrappeCuttingPlanCommandRepository"]
