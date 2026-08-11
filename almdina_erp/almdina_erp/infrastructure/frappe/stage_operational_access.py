"""Application/Frappe adapter for stage operational-role mutation gates."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.orders.stage_operational_access import (
    decide_stage_scoped_mutation,
)


def _is_admin(user: str | None = None) -> bool:
    return str(user or frappe.session.user or "") == "Administrator"


def current_stage_operational_access(order: Any, *, user: str | None = None) -> dict[str, Any]:
    """Describe whether ``user`` may perform stage-scoped mutations on ``order``."""

    actor = str(user or frappe.session.user or "").strip()
    stage_name = str(getattr(order, "current_production_stage", None) or "").strip()
    production_path = str(getattr(order, "production_path", None) or "").strip()
    operational_role = ""
    if stage_name and frappe.db.exists("Production Stage", stage_name):
        operational_role = str(
            frappe.db.get_value("Production Stage", stage_name, "operational_role") or ""
        ).strip()

    allowed, code, reason = decide_stage_scoped_mutation(
        actor_roles=frappe.get_roles(actor) if actor else (),
        operational_role=operational_role or None,
        has_current_stage=bool(stage_name),
        has_production_path=bool(production_path),
        is_admin=_is_admin(actor),
    )
    return {
        "has_current_stage": bool(stage_name),
        "has_production_path": bool(production_path),
        "active_stage_name": stage_name or None,
        "operational_role": operational_role or None,
        "actor_holds_operational_role": allowed,
        "code": code,
        "reason": reason,
    }


def require_stage_operational_access(order: Any, *, user: str | None = None) -> dict[str, Any]:
    """Fail closed unless the actor holds the current stage operational role."""

    access = current_stage_operational_access(order, user=user)
    if access["actor_holds_operational_role"]:
        return access
    frappe.throw(
        _(access["reason"] or "لا تملك الدور التشغيلي المطلوب للمرحلة الحالية."),
        frappe.PermissionError,
    )
    return access


__all__ = [
    "current_stage_operational_access",
    "require_stage_operational_access",
]
