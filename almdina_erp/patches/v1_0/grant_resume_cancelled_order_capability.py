from __future__ import annotations

from almdina_erp.almdina_erp.application.security.cancellation_resume_migration import (
    resume_cancelled_state_updates,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)


def execute() -> None:
    """Install the resume capability and grant it to existing supervisor roles."""

    sync_permission_types()
    repository = ProjectedPermissionMatrixRepository()
    updates = resume_cancelled_state_updates(repository.role_states())
    if updates:
        repository.save_role_states(updates)


__all__ = ["execute"]
