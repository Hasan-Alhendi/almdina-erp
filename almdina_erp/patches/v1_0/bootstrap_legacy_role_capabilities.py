from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    legacy_role_state,
    legacy_roles,
)
from almdina_erp.almdina_erp.domain.security.authorization import CAPABILITY_CATALOG
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


BOOTSTRAP_SOURCE = "Almdina legacy permission upgrade bootstrap"


def _managed_doctypes() -> list[str]:
    return sorted(
        {
            definition.applies_to
            for definition in CAPABILITY_CATALOG.values()
            if frappe.db.exists("DocType", definition.applies_to)
        }
    )


def _has_explicit_override(role: str, doctypes: list[str]) -> bool:
    """Protect any matrix previously saved through Frappe or Almdina."""

    if not doctypes or not frappe.db.exists("DocType", "Custom DocPerm"):
        return False
    return bool(
        frappe.get_all(
            "Custom DocPerm",
            filters={
                "parent": ["in", doctypes],
                "role": role,
                "permlevel": 0,
            },
            pluck="name",
            limit=1,
        )
    )


def execute() -> None:
    """Restore operational access when upgrading to configurable capabilities.

    The capability foundation intentionally did not auto-grant templates. That is
    safe for new installations, but it makes existing operational users lose the
    custom plan, costing, production and administration permissions immediately
    after migration. This one-time patch maps only the historical Almdina roles,
    skips roles with an explicit Custom DocPerm matrix, and records every applied
    upgrade in the append-only permission audit.
    """

    sync_permission_types()
    doctypes = _managed_doctypes()
    repository = FrappePermissionMatrixRepository()

    for role in legacy_roles():
        if not frappe.db.exists("Role", role):
            continue
        if _has_explicit_override(role, doctypes):
            continue

        before = repository.role_state(role)["capabilities"]
        saved = repository.save_role_state(role, legacy_role_state(role))
        after = saved["capabilities"]
        repository.record_audit(
            role=role,
            before=before,
            after=after,
            changed_by="Administrator",
            source=BOOTSTRAP_SOURCE,
        )
