from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


def execute() -> None:
    """Repair native and field-level projections on already configured sites."""

    sync_permission_types()


__all__ = ["execute"]
