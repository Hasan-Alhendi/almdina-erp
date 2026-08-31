from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import APPROVED, DRAFT
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_KERF_MM,
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    DEFAULT_PREFERRED_TRIM_MM,
    PlanSettings,
    normalize_plan_settings,
)
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
    approved_plan_source_type: str | None = None


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


def _numeric_or_default(value: Any, default: float) -> Any:
    return default if value is None else value


def factory_default_plan_settings() -> PlanSettings:
    """Return defaults only for a plan that has no revision lineage yet.

    Zero is an explicit valid value for kerf and preferred trim, so defaults are
    applied only when Frappe returns ``None`` for a genuinely missing numeric
    value. Factory settings never rewrite an existing Cutting Plan lineage.
    """

    settings = frappe.get_cached_doc("Almdina ERP Settings")
    return normalize_plan_settings(
        optimization_mode=(
            str(settings.default_packing_mode or "").strip()
            or DEFAULT_OPTIMIZATION_MODE_ID
        ),
        machine_type=(
            str(settings.default_cutting_machine_type or "").strip()
            or DEFAULT_MACHINE_TYPE
        ),
        optimization_time_limit_sec=_numeric_or_default(
            settings.default_optimization_time_limit_sec,
            DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        ),
        kerf_mm=_numeric_or_default(settings.default_kerf_mm, DEFAULT_KERF_MM),
        preferred_trim_mm=_numeric_or_default(
            settings.default_trim_margin_mm,
            DEFAULT_PREFERRED_TRIM_MM,
        ),
    )


def plan_settings(plan: Any) -> PlanSettings:
    """Read one plan's own settings without reapplying current factory defaults."""

    return normalize_plan_settings(
        optimization_mode=(
            str(getattr(plan, "optimization_mode", None) or "").strip()
            or DEFAULT_OPTIMIZATION_MODE_ID
        ),
        machine_type=(
            str(getattr(plan, "machine_type", None) or "").strip()
            or DEFAULT_MACHINE_TYPE
        ),
        optimization_time_limit_sec=_numeric_or_default(
            getattr(plan, "optimization_time_limit_sec", None),
            DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        ),
        kerf_mm=_numeric_or_default(
            getattr(plan, "kerf_mm", None),
            DEFAULT_KERF_MM,
        ),
        preferred_trim_mm=_numeric_or_default(
            getattr(plan, "trim_margin_mm", None),
            DEFAULT_PREFERRED_TRIM_MM,
        ),
    )


def seed_plan_settings(order_name: str) -> PlanSettings:
    """Seed from plan lineage first; use factory defaults only for the first plan."""

    existing = latest_plan(order_name)
    return plan_settings(existing) if existing else factory_default_plan_settings()


def _plan_is_stale(order: Any, plan: Any) -> bool:
    if cint(getattr(plan, "plan_needs_recalculation", 0)):
        return True
    stored = str(getattr(plan, "input_fingerprint", None) or "").strip()
    if not stored:
        return True
    try:
        return stored != plan_input_fingerprint(order, plan)
    except ManufacturingRequirementsError:
        # Incomplete cut dimensions cannot be fingerprinted. Treat the plan as
        # stale so list/shop-floor reads stay available without trusting it.
        return True


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
    current, non-stale production approval. Source type is read from the approved
    Cutting Plan itself and is never mirrored back onto Door Cutting Order.
    """

    approved_plan_name = str(getattr(order, "approved_plan", None) or "").strip() or None
    approved = approved_plan_for_order(order)
    approved_source = (
        str(getattr(approved, "source_type", None) or "").strip() or None
        if approved is not None
        else None
    )
    candidate = approved or current_working_plan(str(order.name))
    if not candidate:
        return ProductionPlanFacts(
            plan_name=None,
            approved_plan_name=approved_plan_name,
            has_cutting_plan=False,
            plan_needs_recalculation=True,
            has_approved_plan=False,
            approved_plan_source_type=approved_source,
        )

    has_snapshot = bool(str(getattr(candidate, "snapshot_json", None) or "").strip())
    stale = _plan_is_stale(order, candidate) if has_snapshot else True
    return ProductionPlanFacts(
        plan_name=str(candidate.name),
        approved_plan_name=approved_plan_name,
        has_cutting_plan=has_snapshot,
        plan_needs_recalculation=stale,
        has_approved_plan=bool(approved and has_snapshot and not stale),
        approved_plan_source_type=approved_source,
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
