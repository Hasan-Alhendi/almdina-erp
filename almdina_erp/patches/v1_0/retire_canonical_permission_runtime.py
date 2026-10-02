from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import CAPABILITY_CATALOG
from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    STATE_DOCTYPE,
    CanonicalPermissionStateRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


_MANAGED_DOCTYPES = tuple(
    sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()})
)


def _has_live_docperm_matrix(role: str) -> bool:
    """Return whether current Frappe data already represents this role.

    A role-specific Custom DocPerm row is authoritative even when every business
    capability column is false. That state is an explicit/fail-closed deny-all,
    not an absent matrix that may be bootstrapped from historical canonical data.
    """

    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return False
    return bool(
        frappe.db.exists(
            "Custom DocPerm",
            {
                "role": role,
                "parent": ["in", list(_MANAGED_DOCTYPES)],
                "if_owner": 0,
            },
        )
    )


def execute() -> None:
    """One-time bridge: project any remaining canonical mirror into DocPerm.

    Idempotent: roles whose live Custom DocPerm matrix already exists are left
    unchanged, including an explicit deny-all matrix. Historical canonical data
    may bridge only when the role has no live matrix at all. Never imports audit
    history as grants and never grants access when both sources are empty.

    Recurring ``sync_permission_types()`` / ``after_migrate`` never perform this
    bridge. After cutover, live Custom DocPerm (including explicit deny-all)
    remains authoritative forever.
    """

    # Schema + DocPerm-only reconcile first; this call must not re-import the
    # retired mirror. The empty-DocPerm bridge below is the sole migration path.
    sync_permission_types()
    if not frappe.db.exists("DocType", STATE_DOCTYPE):
        return

    canonical = CanonicalPermissionStateRepository()
    if not canonical.available():
        return

    reader = CustomDocPermCapabilityReader()
    repository = ProjectedPermissionMatrixRepository()
    prepared: dict[str, dict[str, bool]] = {}
    for role in frappe.get_all(STATE_DOCTYPE, pluck="role", order_by="role asc"):
        resolved = str(role or "").strip()
        if (
            not resolved
            or resolved in PROTECTED_SYSTEM_ROLES
            or not frappe.db.exists("Role", resolved)
        ):
            continue
        mirror = canonical.read(resolved)
        try:
            current = reader.role_capabilities(resolved)
        except ValueError:
            continue
        if current == mirror:
            continue
        # Prefer non-empty DocPerm authority. Only bridge when DocPerm is empty
        # and the retired mirror still carries grants.
        if any(current.values()):
            continue
        if not any(mirror.values()):
            continue
        if _has_live_docperm_matrix(resolved):
            continue
        prepared[resolved] = mirror

    if prepared:
        repository.save_role_states(prepared)
