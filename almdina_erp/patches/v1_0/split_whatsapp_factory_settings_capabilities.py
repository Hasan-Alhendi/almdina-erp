from __future__ import annotations

from almdina_erp.almdina_erp.application.security.whatsapp_settings_capability_migration import (
    whatsapp_settings_capability_updates,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)


def execute() -> None:
    """Install WhatsApp capabilities and copy them from the previous grants."""

    sync_permission_types()
    repository = ProjectedPermissionMatrixRepository()
    updates = whatsapp_settings_capability_updates(repository.role_states())
    if updates:
        repository.save_role_states(updates)


__all__ = ["execute"]
