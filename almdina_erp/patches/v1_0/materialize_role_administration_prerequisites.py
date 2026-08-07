from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.managed_role_registry import (
    managed_role_names,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.patches.v1_0.permission_migration_helpers import ensure_permission_types


_ROLE_VISIBILITY_DEPENDENTS = (
    Capability.ASSIGN_USER_ROLES,
    Capability.CREATE_ROLES,
    Capability.EDIT_ROLES,
    Capability.DELETE_ROLES,
    Capability.MANAGE_PERMISSIONS,
)


def _candidate_roles() -> tuple[str, ...]:
    return tuple(
        sorted(
            role
            for role in managed_role_names()
            if frappe.db.exists("Role", role)
        )
    )


def execute() -> None:
    """Preserve old RBAC access after introducing explicit role visibility.

    This patch is intentionally separate from the earlier prerequisite
    materialization because development/staging sites may already have executed
    that patch before VIEW_ROLES existed. It grants only the new prerequisite;
    it never invents create/edit/delete authority.
    """

    ensure_permission_types(ALL_CAPABILITIES)
    repository = FrappePermissionMatrixRepository()

    for role in _candidate_roles():
        current = repository.role_state(role)["capabilities"]
        if current.get(Capability.VIEW_ROLES) is True:
            continue
        if not any(current.get(capability) is True for capability in _ROLE_VISIBILITY_DEPENDENTS):
            continue

        explicit = dict(current)
        explicit[Capability.VIEW_ROLES] = True
        repository.save_role_state(role, explicit)

    frappe.clear_cache()
