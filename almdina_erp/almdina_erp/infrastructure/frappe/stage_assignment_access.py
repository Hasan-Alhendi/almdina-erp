from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.stage_assignment_access import (
    decide_stage_assignment_access,
)


def current_stage_assignment_access(
    order: Any,
    *,
    user: str | None = None,
) -> dict[str, Any]:
    """Describe stage mutation ownership from the current Production Stage."""

    actor = str(user or frappe.session.user or "").strip()
    stage_name = str(getattr(order, "current_production_stage", None) or "").strip()
    production_path = str(getattr(order, "production_path", None) or "").strip()
    assigned_to = ""

    if stage_name:
        row = frappe.db.get_value(
            "Production Stage",
            stage_name,
            ["door_cutting_order", "assigned_to"],
            as_dict=True,
        )
        if row and str(row.door_cutting_order or "") == str(getattr(order, "name", "")):
            assigned_to = str(row.assigned_to or "").strip()

    decision = decide_stage_assignment_access(
        actor=actor,
        assigned_to=assigned_to or None,
        has_current_stage=bool(stage_name),
        has_production_path=bool(production_path),
        is_admin=actor == "Administrator",
    )
    return {
        "allowed": decision.allowed,
        "code": decision.code,
        "reason": decision.reason,
        "active_stage_name": stage_name or None,
        "assigned_to": assigned_to or None,
        "actor_is_current_assignee": bool(
            assigned_to and actor and assigned_to == actor
        ),
    }


def require_stage_assignment_access(
    order: Any,
    *,
    user: str | None = None,
) -> dict[str, Any]:
    access = current_stage_assignment_access(order, user=user)
    if access["allowed"]:
        return access
    frappe.throw(
        _(access["reason"] or "لا يمكنك تعديل المرحلة الحالية لهذا الطلب."),
        frappe.PermissionError,
    )
    return access


__all__ = ["current_stage_assignment_access", "require_stage_assignment_access"]
