"""Frappe adapters for board-editor → Cutting Plan materialization."""

from __future__ import annotations

import json
from typing import Any, Mapping

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import draft_key
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import BOARD_EDITOR, DRAFT
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_draft_store import (
    FrappeBoardEditorDraftStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    apply_plan_costs,
    factory_execution_edge_cost,
    initialize_draft_plan_cost_snapshot,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    apply_board_editor_snapshot,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class FrappeBoardEditorPlanCreateStore:
    def __init__(self) -> None:
        self._store = FrappeBoardEditorDraftStore()

    def lock_draft(self, order_name: str, plan_name: str) -> dict[str, Any] | None:
        return self._store.lock(draft_key(order_name, plan_name))

    def record_create(
        self,
        *,
        draft_name: str,
        request_id: str,
        plan_name: str,
        draft_version: int,
    ) -> None:
        self._store.record_create(
            draft_name=draft_name,
            request_id=request_id,
            plan_name=plan_name,
            draft_version=draft_version,
        )


class FrappeBoardEditorCuttingPlanPort:
    def __init__(self) -> None:
        self._repo = FrappeCuttingPlanCommandRepository(Capability.EDIT_OPTIMIZER_SETTINGS)

    def existing_revisions(self, order_name: str) -> list[int]:
        rows = frappe.get_all(
            "Cutting Plan",
            filters={"door_cutting_order": order_name, "plan_kind": "Order"},
            pluck="revision",
        )
        return [cint(value) for value in rows if cint(value) > 0]

    def create_board_editor_draft(
        self,
        *,
        order_name: str,
        revision: int,
        based_on_plan: str,
        settings: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized = normalize_plan_settings(
            optimization_mode=settings.get("optimization_mode"),
            machine_type=settings.get("machine_type"),
            optimization_time_limit_sec=settings.get("optimization_time_limit_sec"),
            kerf_mm=settings.get("kerf_mm"),
            preferred_trim_mm=settings.get("preferred_trim_mm"),
        )
        record = self._repo.create_draft(
            order_name=order_name,
            revision=revision,
            status=DRAFT,
            source_type=BOARD_EDITOR,
            based_on_plan=based_on_plan,
            settings=normalized,
        )
        return {"name": record.name, "revision": record.revision, "status": record.status}

    def apply_snapshot(
        self,
        *,
        order_name: str,
        plan_name: str,
        snapshot: Mapping[str, Any],
        method_key: str,
        method_label: str,
    ) -> dict[str, Any]:
        order = frappe.get_doc("Door Cutting Order", order_name)
        plan = frappe.get_doc("Cutting Plan", plan_name)
        if str(plan.door_cutting_order or "") != str(order.name):
            frappe.throw("Cutting plan does not belong to this order.")
        apply_board_editor_snapshot(
            order,
            plan,
            dict(snapshot),
            method_label=method_label,
        )
        # Reuse the existing plan-cost path so approve freshness does not fail
        # on a missing cost_snapshot_version. No new costing formulas.
        initialize_draft_plan_cost_snapshot(order, plan)
        apply_plan_costs(plan, edge_cost_usd=factory_execution_edge_cost(order, plan))
        plan.method_key = method_key
        plan.method_label = method_label
        plan.source_type = BOARD_EDITOR
        plan.plan_needs_recalculation = 0
        self._repo.save_document(plan)
        return {
            "name": plan.name,
            "revision": cint(plan.revision),
            "status": str(plan.status or DRAFT),
        }

    def discard_incomplete_plan(self, plan_name: str) -> None:
        """Remove a Board Editor Draft that failed mid-create. Never touches source."""

        name = str(plan_name or "").strip()
        if not name or not frappe.db.exists("Cutting Plan", name):
            return
        row = frappe.db.get_value(
            "Cutting Plan",
            name,
            ["status", "source_type", "door_cutting_order"],
            as_dict=True,
        )
        if not row:
            return
        if str(row.status or "") != DRAFT:
            return
        if str(row.source_type or "") != BOARD_EDITOR:
            return
        frappe.delete_doc(
            "Cutting Plan",
            name,
            ignore_permissions=True,
            force=True,
            delete_permanently=True,
        )

    def load_source_plan(self, order_name: str, plan_name: str) -> dict[str, Any]:
        if not frappe.db.exists("Cutting Plan", plan_name):
            return {}
        plan = frappe.get_doc("Cutting Plan", plan_name)
        if str(plan.door_cutting_order or "") != str(order_name):
            return {}
        raw = plan.snapshot_json or "{}"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        snapshot = sanitize_plan_snapshot(parsed)
        return {
            "name": plan.name,
            "order_name": str(plan.door_cutting_order or ""),
            "status": str(plan.status or ""),
            "source_type": str(plan.source_type or ""),
            "revision": cint(plan.revision),
            "optimization_mode": plan.optimization_mode,
            "machine_type": plan.machine_type,
            "optimization_time_limit_sec": plan.optimization_time_limit_sec,
            "kerf_mm": plan.kerf_mm,
            "trim_margin_mm": plan.trim_margin_mm,
            "snapshot": snapshot if isinstance(snapshot, dict) else {},
        }


__all__ = [
    "FrappeBoardEditorCuttingPlanPort",
    "FrappeBoardEditorPlanCreateStore",
]
