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
    """Mark only canonical Draft Cutting Plans stale after order-input changes.

    Approved plans remain immutable. Production/runtime freshness checks compare
    the approved Plan fingerprint with the current order directly, so A6.2 no
    longer mirrors that state into ``Door Cutting Order.plan_needs_recalculation``.
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
        already_stale = bool(cint(plan.plan_needs_recalculation))
        decision = decide_draft_plan_freshness(
            status=str(plan.status or ""),
            stored_fingerprint=str(plan.input_fingerprint or ""),
            expected_fingerprint=plan_input_fingerprint(order, plan),
            already_needs_recalculation=already_stale,
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

    return tuple(invalidated)


__all__ = ["invalidate_stale_draft_plans"]
