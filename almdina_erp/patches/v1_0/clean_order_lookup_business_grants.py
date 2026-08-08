from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)


_ORDER_INPUT_ACTIONS = frozenset(
    {
        Capability.CREATE_ORDER,
        Capability.EDIT_ORDER,
        Capability.CREATE_ORDER_REVISION,
    }
)
_EDGE_ADMIN_ACTIONS = frozenset(
    {
        Capability.CREATE_EDGE_BANDING_TYPES,
        Capability.EDIT_EDGE_BANDING_TYPES,
        Capability.DELETE_EDGE_BANDING_TYPES,
    }
)


def execute() -> None:
    """Remove legacy lookup-derived grants from canonical business authority.

    Older releases normalized order-entry lookup dependencies into the canonical
    capability state itself. That made VIEW_CUSTOMERS / VIEW_EDGE_BANDING_TYPES
    indistinguishable from explicit administration grants and caused incorrect
    menu visibility.

    This one-time migration is deliberately fail-closed: for roles with order
    input actions, Customer view is removed and Edge view is removed unless the
    role also owns an explicit Edge create/edit/delete action. Frappe lookup
    read/select rights are rebuilt by the projection layer, so order entry keeps
    working without exposing master-data surfaces.
    """

    repository = ProjectedPermissionMatrixRepository()
    for row in repository.list_roles():
        role = str(row.get("name") or "").strip()
        if not role:
            continue
        try:
            state = dict(repository.role_state(role)["capabilities"])
        except ValueError:
            continue

        if not any(state.get(capability) is True for capability in _ORDER_INPUT_ACTIONS):
            continue

        changed = False
        if state.get(Capability.VIEW_CUSTOMERS) is True:
            state[Capability.VIEW_CUSTOMERS] = False
            changed = True

        has_edge_admin = any(
            state.get(capability) is True for capability in _EDGE_ADMIN_ACTIONS
        )
        if (
            state.get(Capability.VIEW_EDGE_BANDING_TYPES) is True
            and not has_edge_admin
        ):
            state[Capability.VIEW_EDGE_BANDING_TYPES] = False
            changed = True

        if changed:
            repository.save_role_state(role, state)

    frappe.clear_cache()


__all__ = ["execute"]
