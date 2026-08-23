"""Compatibility facade for assignment-scoped stage mutation access.

Operational roles still describe routing/worker eligibility, but they are not an
authorization source. Existing imports keep their historical names while all
mutation decisions delegate to the canonical current-assignment policy.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.infrastructure.frappe.stage_assignment_access import (
    current_stage_assignment_access,
)


def current_stage_operational_access(
    order: Any,
    *,
    user: str | None = None,
) -> dict[str, Any]:
    """Return assignment ownership using the legacy response shape.

    ``actor_holds_operational_role`` is retained only as a compatibility key for
    old callers. Its value now means "the actor owns the current assignment" and
    never checks role membership.
    """

    assignment = current_stage_assignment_access(order, user=user)
    stage_name = assignment.get("active_stage_name")
    operational_role = None
    if stage_name and frappe.db.exists("Production Stage", stage_name):
        operational_role = frappe.db.get_value(
            "Production Stage",
            stage_name,
            "operational_role",
        ) or None

    return {
        "has_current_stage": bool(stage_name),
        "has_production_path": bool(
            str(getattr(order, "production_path", None) or "").strip()
        ),
        "active_stage_name": stage_name,
        "assigned_to": assignment.get("assigned_to"),
        "actor_is_current_assignee": bool(
            assignment.get("actor_is_current_assignee")
        ),
        "operational_role": operational_role,
        # Compatibility only; no role lookup is performed.
        "actor_holds_operational_role": bool(assignment.get("allowed")),
        "code": assignment.get("code") or "",
        "reason": assignment.get("reason") or "",
    }


def require_stage_operational_access(
    order: Any,
    *,
    user: str | None = None,
) -> dict[str, Any]:
    """Compatibility gate: require ownership of the current assignment."""

    access = current_stage_operational_access(order, user=user)
    if access["actor_holds_operational_role"]:
        return access
    frappe.throw(
        _(access["reason"] or "لا يمكنك تعديل المرحلة الحالية لهذا الطلب."),
        frappe.PermissionError,
    )
    return access


__all__ = [
    "current_stage_operational_access",
    "require_stage_operational_access",
]
