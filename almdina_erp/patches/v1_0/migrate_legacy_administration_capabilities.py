from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability


_SETTINGS_DOCTYPE = "Almdina ERP Settings"
_LEGACY_GRANTS: dict[str, frozenset[str]] = {
    "manage_users": frozenset(
        {
            Capability.VIEW_USERS,
            Capability.CREATE_USERS,
            Capability.EDIT_USERS,
            Capability.ASSIGN_USER_ROLES,
            Capability.ENABLE_USERS,
            Capability.DISABLE_USERS,
            Capability.RESET_USER_PASSWORD,
        }
    ),
    "assign_workforce_profile": frozenset({Capability.ASSIGN_USER_ROLES}),
    "manage_factory_settings": frozenset(
        {
            Capability.VIEW_FACTORY_SETTINGS,
            Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
            Capability.EDIT_FACTORY_COST_DEFAULTS,
            Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
        }
    ),
}
_WORKFORCE_LEGACY_FIELDS = frozenset(
    {"manage_users", "assign_workforce_profile"}
)


def _legacy_role_fields(permission_doctype: str) -> dict[str, set[str]]:
    """Capture exactly which legacy grants each role owned before reconciliation."""

    if not frappe.db.exists("DocType", permission_doctype):
        return {}
    meta = frappe.get_meta(permission_doctype)
    available = [field for field in _LEGACY_GRANTS if meta.has_field(field)]
    if not available:
        return {}

    rows = frappe.get_all(
        permission_doctype,
        filters={"parent": _SETTINGS_DOCTYPE, "permlevel": 0},
        fields=["role", *available],
    )
    grants: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        role = str(row.get("role") or "").strip()
        if not role:
            continue
        for legacy_field in available:
            if bool(row.get(legacy_field)):
                grants[role].add(legacy_field)
    return dict(grants)


def _collect_legacy_fields() -> dict[str, set[str]]:
    collected: dict[str, set[str]] = defaultdict(set)
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        for role, fields in _legacy_role_fields(permission_doctype).items():
            collected[role].update(fields)
    return dict(collected)


def _migrated_capabilities(legacy_fields: set[str]) -> set[str]:
    capabilities: set[str] = set()
    for legacy_field in legacy_fields:
        capabilities.update(_LEGACY_GRANTS[legacy_field])
    return capabilities


def execute() -> None:
    """Migrate broad/profile-era grants to the granular capability model.

    Legacy Permission Type columns are read before synchronization. Runtime code
    never references those old keys. A historical workforce grant also used to
    project ``read`` onto the Settings singleton; fail closed by removing that
    stale read unless the same role explicitly owned the old factory-settings
    grant. Granular settings edit grants, when already present, still restore the
    required view dependency through the canonical matrix normalizer.
    """

    legacy_fields_by_role = _collect_legacy_fields()

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
        sync_permission_types,
    )

    sync_permission_types()
    if not legacy_fields_by_role:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
        PROTECTED_ROLES,
    )

    repository = FrappePermissionMatrixRepository()
    for role in sorted(legacy_fields_by_role):
        if role in PROTECTED_ROLES or not frappe.db.exists("Role", role):
            continue
        try:
            current = repository.role_state(role)["capabilities"]
        except ValueError:
            continue

        legacy_fields = legacy_fields_by_role[role]
        migrated: dict[str, Any] = dict(current)
        if (
            legacy_fields.intersection(_WORKFORCE_LEGACY_FIELDS)
            and "manage_factory_settings" not in legacy_fields
        ):
            migrated[Capability.VIEW_FACTORY_SETTINGS] = False
        for capability in _migrated_capabilities(legacy_fields):
            migrated[capability] = True
        repository.save_role_state(role, migrated)


__all__ = ["execute"]
