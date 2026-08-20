from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import APPROVED, DRAFT
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    plan_input_fingerprint,
)


@dataclass(frozen=True, slots=True)
class ProductionPlanFacts:
    plan_name: str | None
    approved_plan_name: str | None
    has_cutting_plan: bool
    plan_needs_recalculation: bool
    has_approved_plan: bool


def _plan_rows(order_name: str, **filters: Any) -> list[Any]:
    return frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order_name,
            "plan_kind": "Order",
            **filters,
        },
        fields=["name", "revision", "status", "source_type", "modified"],
        order_by="revision desc, modified desc, creation desc",
    )


def latest_plan(order_name: str, **filters: Any) -> Any | None:
    rows = _plan_rows(order_name, **filters)
    return frappe.get_doc("Cutting Plan", rows[0].name) if rows else None


def current_working_plan(order_name: str) -> Any | None:
    """Resolve the current editable plan without consulting DCO source projections."""

    draft = latest_plan(order_name, status=DRAFT)
    if draft:
        return draft
    return latest_plan(order_name, status=APPROVED) or latest_plan(order_name)


def factory_default_plan_settings() -> PlanSettings:
    """Return the canonical defaults for a plan that has no revision lineage yet."""

    settings = frappe.get_cached_doc("Almdina ERP Settings")
    return PlanSettings(
        optimization_mode=str(settings.default_packing_mode or "Auto Pro"),
        machine_type=str(settings.default_cutting_machine_type or "Auto"),
        optimization_time_limit_sec=flt(settings.default_optimization_time_limit_sec) or 10,
        kerf_mm=flt(settings.default_kerf_mm) or 3,
        trim_margin_mm=flt(settings.default_trim_margin_mm) or 5,
    )


def plan_settings(plan: Any) -> PlanSettings:
    return PlanSettings(
        optimization_mode=str(plan.optimization_mode or "Auto Pro"),
        machine_type=str(plan.machine_type or "Auto"),
        optimization_time_limit_sec=flt(plan.optimization_time_limit_sec) or 10,
        kerf_mm=flt(plan.kerf_mm),
        trim_margin_mm=flt(plan.trim_margin_mm),
    )


def seed_plan_settings(order_name: str) -> PlanSettings:
    """Seed a new revision from canonical plan lineage, then factory defaults."""

    existing = latest_plan(order_name)
    return plan_settings(existing) if existing else factory_default_plan_settings()


def _plan_is_stale(order: Any, plan: Any) -> bool:
    if cint(getattr(plan, "plan_needs_recalculation", 0)):
        return True
    stored = str(getattr(plan, "input_fingerprint", None) or "").strip()
    if not stored:
        return True
    return stored != plan_input_fingerprint(order, plan)


def approved_plan_for_order(order: Any) -> Any | None:
    """Resolve the real DCO→Cutting Plan approval relation fail-closed.

    Replacement and production flows must inherit plan-owned settings/costs from
    this exact approved revision, never from compatibility projections on DCO or
    from an unrelated newer draft.
    """

    name = str(getattr(order, "approved_plan", None) or "").strip()
    if not name or not frappe.db.exists("Cutting Plan", name):
        return None
    plan = frappe.get_doc("Cutting Plan", name)
    if str(getattr(plan, "door_cutting_order", None) or "") != str(order.name):
        return None
    if str(getattr(plan, "plan_kind", None) or "Order") != "Order":
        return None
    if str(getattr(plan, "status", None) or "") != APPROVED:
        return None
    return plan


def production_plan_facts(order: Any) -> ProductionPlanFacts:
    """Build shop-floor plan facts exclusively from canonical Cutting Plan state.

    ``approved_plan_name`` preserves whether the order has an explicit approval
    relation, while ``has_approved_plan`` means that exact relation is still a
    current, non-stale production approval. Keeping those facts separate lets the
    workflow explain stale approvals accurately instead of asking for approval a
    second time with a misleading message.
    """

    approved_plan_name = str(getattr(order, "approved_plan", None) or "").strip() or None
    approved = approved_plan_for_order(order)
    candidate = approved or current_working_plan(str(order.name))
    if not candidate:
        return ProductionPlanFacts(
            plan_name=None,
            approved_plan_name=approved_plan_name,
            has_cutting_plan=False,
            plan_needs_recalculation=True,
            has_approved_plan=False,
        )

    has_snapshot = bool(str(getattr(candidate, "snapshot_json", None) or "").strip())
    stale = _plan_is_stale(order, candidate) if has_snapshot else True
    return ProductionPlanFacts(
        plan_name=str(candidate.name),
        approved_plan_name=approved_plan_name,
        has_cutting_plan=has_snapshot,
        plan_needs_recalculation=stale,
        has_approved_plan=bool(approved and has_snapshot and not stale),
    )


__all__ = [
    "ProductionPlanFacts",
    "approved_plan_for_order",
    "current_working_plan",
    "factory_default_plan_settings",
    "latest_plan",
    "plan_settings",
    "production_plan_facts",
    "seed_plan_settings",
]
