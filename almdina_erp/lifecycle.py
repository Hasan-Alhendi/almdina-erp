from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.install import (
    after_install as run_existing_after_install,
    after_migrate as run_existing_after_migrate,
)


def after_install() -> None:
    run_existing_after_install()
    sync_permission_types()


def after_migrate() -> None:
    run_existing_after_migrate()
    sync_permission_types()


__all__ = ["after_install", "after_migrate"]
