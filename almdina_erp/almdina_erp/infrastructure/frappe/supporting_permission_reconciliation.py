from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.supporting_doctype_permission_repository import (
    SupportingDoctypePermissionRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


def reconcile_supporting_permission_projections() -> int:
    """Refresh native technical grants from live Custom DocPerm capability grants.

    Business authority remains in Custom DocPerm columns for editable factory
    roles. This migration only repairs the native Frappe Role Permission layer
    that must be present before controller-level ``has_permission`` hooks can
    authorize a command. Missing/deleted/protected roles are ignored fail-closed.
    """

    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return 0

    roles = {
        str(role or "").strip()
        for role in frappe.get_all(
            "Custom DocPerm",
            filters={"permlevel": 0},
            pluck="role",
            order_by="role asc",
        )
        if role
    }
    reader = CustomDocPermCapabilityReader()
    supporting = SupportingDoctypePermissionRepository()
    reconciled = 0
    for role in sorted(roles):
        if role in PROTECTED_SYSTEM_ROLES or not frappe.db.exists("Role", role):
            continue
        try:
            state = reader.role_capabilities(role)
        except ValueError:
            continue
        supporting.save_role_state(role, state)
        reconciled += 1
    return reconciled


__all__ = ["reconcile_supporting_permission_projections"]
