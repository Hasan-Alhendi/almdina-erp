from __future__ import annotations

from almdina_erp.almdina_erp.application.security.shop_floor_history_migration import (
    legacy_history_state_updates,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)


def execute() -> None:
    """Preserve the history visibility that existing Shop Floor roles had.

    Before ``VIEW_SHOP_FLOOR_HISTORY`` existed, every role that could enter Shop
    Floor could also read its completed-stage archive. The pure application
    policy derives the minimal compatibility updates from canonical role state;
    no role names or DocPerm projections are treated as authority.
    """

    repository = ProjectedPermissionMatrixRepository()
    updates = legacy_history_state_updates(repository.role_states())
    if updates:
        repository.save_role_states(updates)


__all__ = ["execute"]
