from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.install import (
    after_install as run_existing_after_install,
    after_migrate as run_existing_after_migrate,
)


def _sync_security_foundation() -> None:
    """Keep permission-type metadata in sync without assigning role grants.

    Historical role grants belong to one-time migration patches. Re-running that
    bootstrap after every install/migrate would make role names implicit policy
    and could repopulate an intentionally empty role.
    """

    sync_permission_types()


def after_install() -> None:
    run_existing_after_install()
    _sync_security_foundation()


def after_migrate() -> None:
    run_existing_after_migrate()
    _sync_security_foundation()


__all__ = ["after_install", "after_migrate"]
