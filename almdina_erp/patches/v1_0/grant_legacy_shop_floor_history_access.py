from __future__ import annotations

from almdina_erp.almdina_erp.domain.security.authorization import (
    SHOP_FLOOR_ACCESS_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)


def _needs_legacy_history_grant(state: dict[str, bool]) -> bool:
    if state.get(Capability.VIEW_SHOP_FLOOR_HISTORY) is True:
        return False
    return any(state.get(capability) is True for capability in SHOP_FLOOR_ACCESS_CAPABILITIES)


def execute() -> None:
    """Preserve the history visibility that existing Shop Floor roles had.

    Before ``VIEW_SHOP_FLOOR_HISTORY`` existed, every role that could enter Shop
    Floor could also read its completed-stage archive. Copy that legacy behavior
    once into the new explicit capability without deriving authority from role
    names or from DocPerm projections.
    """

    repository = ProjectedPermissionMatrixRepository()
    current_states = repository.role_states()
    updates: dict[str, dict[str, bool]] = {}

    for role, state in current_states.items():
        if not _needs_legacy_history_grant(state):
            continue
        updated = dict(state)
        updated[Capability.VIEW_SHOP_FLOOR_HISTORY] = True
        updates[role] = updated

    if updates:
        repository.save_role_states(updates)


__all__ = ["execute"]
