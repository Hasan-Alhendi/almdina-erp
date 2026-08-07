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


def _legacy_role_grants(permission_doctype: str) -> dict[str, set[str]]:
    """Capture legacy grants before the current permission catalog is reconciled."""

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
                grants[role].update(_LEGACY_GRANTS[legacy_field])
    return dict(grants)


def _collect_legacy_grants() -> dict[str, set[str]]:
    collected: dict[str, set[str]] = defaultdict(set)
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        for role, capabilities in _legacy_role_grants(permission_doctype).items():
            collected[role].update(capabilities)
    return dict(collected)


def execute() -> None:
    """Migrate broad/profile-era grants to the granular capability model.

    The old Permission Type columns are intentionally read before synchronization.
    They can remain as inert historical metadata; current runtime authorization no
    longer references them. The patch is idempotent because target grants are only
    switched on and the canonical matrix normalizer preserves all existing grants.
    """

    legacy_grants = _collect_legacy_grants()

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
        sync_permission_types,
    )

    # Ensure the new assign_user_roles Permission Type exists before persisting it.
    sync_permission_types()
    if not legacy_grants:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
        PROTECTED_ROLES,
    )

    repository = FrappePermissionMatrixRepository()
    for role in sorted(legacy_grants):
        if role in PROTECTED_ROLES or not frappe.db.exists("Role", role):
            continue
        try:
            current = repository.role_state(role)["capabilities"]
        except ValueError:
            continue
        migrated: dict[str, Any] = dict(current)
        for capability in legacy_grants[role]:
            migrated[capability] = True
        repository.save_role_state(role, migrated)


__all__ = ["execute"]
