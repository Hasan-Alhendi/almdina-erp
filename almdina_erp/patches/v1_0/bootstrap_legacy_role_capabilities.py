from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


def execute() -> None:
    """Historical compatibility patch without role-name policy.

    The permission model is fully configurable. No Almadina business role name
    may seed capabilities. Keep this registered patch importable for sites that
    have not executed the historical entry yet, but limit it to installing and
    reconciling permission metadata from existing data.
    """

    sync_permission_types()


__all__ = ["execute"]
