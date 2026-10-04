from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    STATE_DOCTYPE,
    CanonicalPermissionStateRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


def execute() -> None:
    """Reset legacy-derived permission state to explicit deny-all once.

    This historical patch predates the Custom DocPerm authority cutover. Keep its
    original security meaning stable even though repository ownership changed:
    every editable role represented in the historical canonical store is cleared
    in both the retired mirror and the live Custom DocPerm authority.

    This prevents a later one-time canonical retirement bridge from resurrecting
    grants that this reset intentionally revoked. Administrator and protected
    platform roles remain outside editable Almdina business authority.
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

    canonical = CanonicalPermissionStateRepository()
    for role in sorted(prepared):
        canonical.save(role, {})

    ProjectedPermissionMatrixRepository().save_role_states(prepared)


__all__ = ["execute"]
