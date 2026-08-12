from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    STATE_DOCTYPE,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


def execute() -> None:
    """Reset legacy-derived canonical grants once, then rebuild Frappe projections.

    This patch is the cut-over boundary to the new authorization model. Existing
    canonical rows may have been bootstrapped from historical audit records before
    audit provenance was removed as an authority source. Because Almdina roles and
    permissions are intentionally being rebuilt from scratch, every editable role
    that already has canonical state is reset to deny-all exactly once.

    Administrator and protected platform roles are never written here. Future
    grants must be made explicitly through the Permission Matrix UI/API.
    """

    if not frappe.db.exists("DocType", STATE_DOCTYPE):
        return

    roles = [
        str(role)
        for role in frappe.get_all(
            STATE_DOCTYPE,
            pluck="role",
            order_by="role asc",
        )
        if role
    ]
    prepared = {
        role: {}
        for role in sorted(set(roles))
        if role not in PROTECTED_SYSTEM_ROLES and frappe.db.exists("Role", role)
    }
    if not prepared:
        return

    ProjectedPermissionMatrixRepository().save_role_states(prepared)


__all__ = ["execute"]
