from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    STATE_DOCTYPE,
    CanonicalPermissionStateRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.supporting_doctype_permission_repository import (
    SupportingDoctypePermissionRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


def reconcile_supporting_permission_projections() -> int:
    """Refresh native technical grants from existing canonical role matrices.

    Canonical Almdina capability state remains the sole business authority. This
    migration only repairs the native Frappe Role Permission layer that must be
    present before controller-level ``has_permission`` hooks can authorize a
    command. Missing/deleted/protected roles are ignored fail-closed.
    """

    canonical = CanonicalPermissionStateRepository()
    if not canonical.available():
        return 0

    roles = frappe.get_all(
        STATE_DOCTYPE,
        pluck="role",
        order_by="role asc",
    )
    supporting = SupportingDoctypePermissionRepository()
    reconciled = 0
    for role in sorted({str(value or "").strip() for value in roles if value}):
        if role in PROTECTED_SYSTEM_ROLES or not frappe.db.exists("Role", role):
            continue
        supporting.save_role_state(role, canonical.read(role))
        reconciled += 1
    return reconciled


__all__ = ["reconcile_supporting_permission_projections"]
