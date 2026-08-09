from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_surface_metadata import (
    sync_cutting_plan_surface_metadata,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_security_cleanup import (
    revoke_hidden_system_manager_from_almdina_workforce,
)
from almdina_erp.install import (
    after_install as run_existing_after_install,
    after_migrate as run_existing_after_migrate,
)


def _sync_security_foundation() -> None:
    """Repair security metadata and legacy hidden workforce authority.

    Role names never seed business policy here. The migration only removes
    platform roles that must not act as Almdina authority sources.
    """

    sync_permission_types()
    revoke_hidden_system_manager_from_almdina_workforce()


def _sync_form_metadata_invariants() -> None:
    """Keep non-financial order surfaces independent from cost field levels."""

    sync_cutting_plan_surface_metadata()


def after_install() -> None:
    run_existing_after_install()
    _sync_form_metadata_invariants()
    _sync_security_foundation()


def after_migrate() -> None:
    run_existing_after_migrate()
    _sync_form_metadata_invariants()
    _sync_security_foundation()


__all__ = ["after_install", "after_migrate"]
