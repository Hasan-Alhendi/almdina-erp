from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_surface_metadata import (
    sync_cutting_plan_surface_metadata,
)
from almdina_erp.almdina_erp.infrastructure.frappe.native_app_navigation import (
    sync_native_app_navigation,
)
from almdina_erp.almdina_erp.infrastructure.frappe.order_cost_surface_metadata import (
    sync_order_cost_surface_metadata,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.supporting_permission_reconciliation import (
    reconcile_supporting_permission_projections,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import (
    sync_workforce_membership_metadata,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_security_cleanup import (
    revoke_hidden_system_manager_from_almdina_workforce,
)
from almdina_erp.install import (
    after_install as run_existing_after_install,
    after_migrate as run_existing_after_migrate,
)


def _sync_security_foundation() -> None:
    """Repair security metadata and native projections without seeding policy.

    Role names never seed business policy here. Canonical Almdina role state is
    the sole authority; migrations only remove hidden platform authority and
    refresh the technical Frappe grants required for its permission hooks.
    """

    sync_permission_types()
    sync_workforce_membership_metadata()
    revoke_hidden_system_manager_from_almdina_workforce()
    reconcile_supporting_permission_projections()


def _sync_form_metadata_invariants() -> None:
    """Keep Order, Plan, and Cost workspace metadata boundaries explicit."""

    sync_cutting_plan_surface_metadata()
    sync_order_cost_surface_metadata()


def _sync_native_navigation_metadata() -> None:
    """Keep only app-owned native Frappe navigation metadata current."""

    sync_native_app_navigation()


def after_install() -> None:
    run_existing_after_install()
    _sync_form_metadata_invariants()
    _sync_security_foundation()
    _sync_native_navigation_metadata()


def after_migrate() -> None:
    run_existing_after_migrate()
    _sync_form_metadata_invariants()
    _sync_security_foundation()
    _sync_native_navigation_metadata()


__all__ = ["after_install", "after_migrate"]
