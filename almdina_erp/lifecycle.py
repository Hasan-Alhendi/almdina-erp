from __future__ import annotations

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_schema import (
    ensure_customer_bot_operation_defaults,
    ensure_customer_bot_reply_unique_indexes,
    ensure_customer_bot_session_unique_indexes,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_index import (
    sync_customer_normalized_mobile_index,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_surface_metadata import (
    sync_cutting_plan_surface_metadata,
)
from almdina_erp.almdina_erp.infrastructure.frappe.native_app_navigation import (
    sync_native_app_navigation,
)
from almdina_erp.almdina_erp.infrastructure.frappe.order_cost_surface_metadata import (
    sync_order_cost_surface_metadata,
)
from almdina_erp.almdina_erp.infrastructure.frappe.order_status_metadata import (
    sync_order_status_options,
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

    Role names never seed business policy here. Custom DocPerm / Permission Types
    are the business grant authority for editable factory roles; Almdina
    application/domain authorization applies contextual constraints. ``Almdina
    Role Capability State`` is migration/history compatibility only and is never
    re-imported by recurring migrate/sync. Migrations only remove hidden
    platform authority and refresh technical Frappe grant projections.
    """

    sync_permission_types()
    sync_workforce_membership_metadata()
    revoke_hidden_system_manager_from_almdina_workforce()
    reconcile_supporting_permission_projections()


def _sync_form_metadata_invariants() -> None:
    """Keep Order, Plan, Cost, and status projections explicit and current."""

    sync_cutting_plan_surface_metadata()
    sync_order_cost_surface_metadata()
    sync_order_status_options()


def _sync_native_navigation_metadata() -> None:
    """Keep only app-owned native Frappe navigation metadata current."""

    sync_native_app_navigation()


def _sync_customer_bot_schema() -> None:
    """Ensure lookup field, unique keys, and catalog texts from the live schema.

    Install marks patches complete without running them, and a later migrate
    will not repeat a logged patch. Both hooks therefore inspect the database.
    Missing catalog keys are filled from the defaults. A saved customization
    of an existing key is left as stored.
    """

    from almdina_erp.patches.v1_0.install_customer_bot_settings import execute as repair_customer_bot_texts

    sync_customer_normalized_mobile_index()
    ensure_customer_bot_reply_unique_indexes()
    ensure_customer_bot_session_unique_indexes()
    repair_customer_bot_texts()
    ensure_customer_bot_operation_defaults()


def after_install() -> None:
    run_existing_after_install()
    _sync_form_metadata_invariants()
    _sync_security_foundation()
    _sync_native_navigation_metadata()
    _sync_customer_bot_schema()


def after_migrate() -> None:
    run_existing_after_migrate()
    _sync_form_metadata_invariants()
    _sync_security_foundation()
    _sync_native_navigation_metadata()
    _sync_customer_bot_schema()


__all__ = ["after_install", "after_migrate"]
