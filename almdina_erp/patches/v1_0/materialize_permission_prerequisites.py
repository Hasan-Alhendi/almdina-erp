from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.application.security.permission_matrix import required_capabilities
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES
from almdina_erp.almdina_erp.infrastructure.frappe.managed_role_registry import managed_role_names
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import FrappePermissionMatrixRepository
from almdina_erp.patches.v1_0.permission_migration_helpers import ensure_permission_types


def _candidate_roles() -> tuple[str, ...]:
    return tuple(
        sorted(
            role
            for role in managed_role_names()
            if frappe.db.exists("Role", role)
        )
    )


def _materialized_state(state: dict[str, bool]) -> dict[str, bool]:
    explicit = dict(state)
    for capability, enabled in tuple(state.items()):
        if not enabled:
            continue
        for requirement in required_capabilities(capability):
            explicit[requirement] = True
    return explicit


def execute() -> None:
    """Preserve historical effective access before strict validation is enabled."""

    ensure_permission_types(ALL_CAPABILITIES)
    repository = FrappePermissionMatrixRepository()
    for role in _candidate_roles():
        current = repository.role_state(role)["capabilities"]
        explicit = _materialized_state(current)
        if explicit != current:
            repository.save_role_state(role, explicit)
    frappe.clear_cache()
