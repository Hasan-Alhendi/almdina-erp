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


def invalidate_stale_draft_plans(order: Any) -> tuple[str, ...]:
    """Mark calculated Draft plans stale after customer requirements change.

    The order has already been persisted when this service runs. No optimizer is
    invoked, no plan snapshot is cleared, and immutable plan revisions are never
    touched. The legacy DCO stale flag is maintained only as a one-way UI
    compatibility projection until the aggregate workspace replaces it.
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
    for plan_name in plan_names:
        plan = frappe.get_doc("Cutting Plan", plan_name)
        decision = decide_draft_plan_freshness(
            status=str(plan.status or ""),
            stored_fingerprint=str(plan.input_fingerprint or ""),
            expected_fingerprint=plan_input_fingerprint(order, plan),
            already_needs_recalculation=bool(cint(plan.plan_needs_recalculation)),
        )
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

    if invalidated:
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
