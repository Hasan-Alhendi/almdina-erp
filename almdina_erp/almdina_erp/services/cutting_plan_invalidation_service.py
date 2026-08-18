from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.cutting.plan_freshness import (
    decide_draft_plan_freshness,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    plan_input_fingerprint,
)


def _plan_matches_order(order: Any, plan: Any) -> bool:
    stored = str(getattr(plan, "input_fingerprint", None) or "").strip()
    expected = plan_input_fingerprint(order, plan)
    return bool(stored) and stored == expected


def invalidate_stale_draft_plans(order: Any) -> tuple[str, ...]:
    """Project order changes into Cutting Plan freshness without plan mutation.

    Draft revisions may be marked stale. Approved history is never modified; if
    the currently approved plan no longer matches the order, only the legacy DCO
    stale flag is raised so production stays fail-closed until an explicit Draft
    replacement is calculated and approved.
    """

    if not getattr(order, "name", None) or getattr(order, "is_new", lambda: False)():
        return ()

    plan_names = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
            "status": DRAFT,
        },
        pluck="name",
        order_by="revision desc, creation desc",
    )

    invalidated: list[str] = []
    requires_recalculation = False
    for plan_name in plan_names:
        plan = frappe.get_doc("Cutting Plan", plan_name)
        already_stale = bool(cint(plan.plan_needs_recalculation))
        decision = decide_draft_plan_freshness(
            status=str(plan.status or ""),
            stored_fingerprint=str(plan.input_fingerprint or ""),
            expected_fingerprint=plan_input_fingerprint(order, plan),
            already_needs_recalculation=already_stale,
        )
        if already_stale:
            requires_recalculation = True
        if not decision.should_invalidate:
            continue

        frappe.db.set_value(
            "Cutting Plan",
            plan.name,
            "plan_needs_recalculation",
            1,
            update_modified=False,
        )
        invalidated.append(plan.name)
        requires_recalculation = True

    approved_name = str(getattr(order, "approved_plan", None) or "").strip()
    if approved_name and frappe.db.exists("Cutting Plan", approved_name):
        approved_plan = frappe.get_doc("Cutting Plan", approved_name)
        if (
            str(approved_plan.door_cutting_order or "") == str(order.name)
            and not _plan_matches_order(order, approved_plan)
        ):
            # Approved plan remains immutable. Only the order-level compatibility
            # projection becomes stale until an explicit replacement is approved.
            requires_recalculation = True

    if requires_recalculation:
        meta = frappe.get_meta("Door Cutting Order")
        if meta.has_field("plan_needs_recalculation"):
            frappe.db.set_value(
                "Door Cutting Order",
                order.name,
                "plan_needs_recalculation",
                1,
                update_modified=False,
            )
            order.plan_needs_recalculation = 1

    return tuple(invalidated)


__all__ = ["invalidate_stale_draft_plans"]
