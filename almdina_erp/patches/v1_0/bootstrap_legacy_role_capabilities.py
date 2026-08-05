from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.legacy_permission_bootstrap import (
    bootstrap_legacy_role_permissions,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


def execute() -> None:
    """Restore operational access after introducing configurable capabilities."""

    sync_permission_types()
    bootstrap_legacy_role_permissions()
