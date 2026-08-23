from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.security.authorization import (
    CUTTING_PLAN_DOCTYPE,
    capability_definition,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
)


_DEFAULT_PERMISSION_MESSAGE = "لا تملك الصلاحية المطلوبة على خطة القص لهذا الطلب."


def cutting_plan_capability_allowed(
    order: Any,
    capability: str,
    *,
    user: str | None = None,
    allow_new_order: bool = False,
) -> bool:
    """Authorize one Cutting Plan capability inside its parent-order scope.

    Cutting Plan is an aggregate owned by its own capability catalog, while the
    Door Cutting Order remains the tenant-like scope boundary for one concrete
    business transaction. Capability membership alone is therefore insufficient:
    a non-administrator must also be able to read the related parent order.

    ``allow_new_order`` exists only for pre-save guards that have no persisted
    parent row yet. Runtime commands should keep the default fail-closed value.
    """

    definition = capability_definition(capability)
    if definition.applies_to != CUTTING_PLAN_DOCTYPE:
        raise ValueError(
            f"Capability {capability} does not belong to {CUTTING_PLAN_DOCTYPE}."
        )

    resolved_user = str(user or frappe.session.user or "")
    if resolved_user == "Administrator":
        return True
    if not resolved_user or resolved_user == "Guest":
        return False
    if not doctype_has_capability(capability, user=resolved_user):
        return False

    is_new = bool(getattr(order, "is_new", lambda: False)())
    if is_new:
        return bool(allow_new_order)
    if getattr(order, "doctype", None) != "Door Cutting Order":
        return False
    return bool(frappe.has_permission(order, "read", user=resolved_user))


def require_cutting_plan_capability(
    order: Any,
    capability: str,
    *,
    user: str | None = None,
    allow_new_order: bool = False,
    message: str | None = None,
) -> None:
    if cutting_plan_capability_allowed(
        order,
        capability,
        user=user,
        allow_new_order=allow_new_order,
    ):
        return
    frappe.throw(
        message or _(_DEFAULT_PERMISSION_MESSAGE),
        frappe.PermissionError,
    )


__all__ = [
    "cutting_plan_capability_allowed",
    "require_cutting_plan_capability",
]
