from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    required_capabilities,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
    PROTECTED_ROLES,
)
from almdina_erp.patches.v1_0.permission_migration_helpers import ensure_permission_types


_METADATA_DOCTYPE = "Almdina Role Metadata"


def _managed_doctypes() -> tuple[str, ...]:
    return tuple(sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()}))


def _candidate_roles() -> tuple[str, ...]:
    roles: set[str] = set()
    doctypes = [doctype for doctype in _managed_doctypes() if frappe.db.exists("DocType", doctype)]
    if doctypes and frappe.db.exists("DocType", "Custom DocPerm"):
        roles.update(
            str(role)
            for role in frappe.get_all(
                "Custom DocPerm",
                filters={"parent": ["in", doctypes], "permlevel": 0},
                pluck="role",
                limit_page_length=0,
            )
            if role
        )
    if frappe.db.exists("DocType", _METADATA_DOCTYPE):
        roles.update(
            str(role)
            for role in frappe.get_all(
                _METADATA_DOCTYPE,
                filters={"managed_by_almdina": 1},
                pluck="role",
                limit_page_length=0,
            )
            if role
        )
    return tuple(
        sorted(
            role
            for role in roles
            if role not in PROTECTED_ROLES and frappe.db.exists("Role", role)
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
