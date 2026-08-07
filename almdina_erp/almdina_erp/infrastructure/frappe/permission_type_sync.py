from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
)
from almdina_erp.almdina_erp.infrastructure.frappe.managed_role_registry import managed_role_names


def _managed_doctypes() -> tuple[str, ...]:
    return tuple(sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()}))


def reconcile_custom_permission_projections() -> None:
    """Explicitly re-save only Almdina-owned role states through the current model.

    This is intentionally separate from ``sync_permission_types`` so schema
    synchronization can safely run before migration patches materialize old
    implicit grants as explicit permissions.
    """

    roles = sorted(role for role in managed_role_names() if frappe.db.exists("Role", role))
    if not roles:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
    )

    repository = FrappePermissionMatrixRepository()
    for role in roles:
        effective = repository.role_state(role)["capabilities"]
        repository.save_role_state(role, effective)


def sync_permission_types() -> None:
    """Install capability fields and native baselines without rewriting roles."""

    if not frappe.db.exists("DocType", "Permission Type"):
        return

    for definition in CUSTOM_PERMISSION_DEFINITIONS:
        if not frappe.db.exists("DocType", definition.applies_to):
            continue
        if frappe.db.exists(
            "Permission Type",
            {
                "perm_type": definition.permission_type,
                "doc_type": definition.applies_to,
            },
        ):
            continue
        frappe.get_doc(
            {
                "doctype": "Permission Type",
                "perm_type": definition.permission_type,
                "doc_type": definition.applies_to,
            }
        ).insert(ignore_permissions=True)

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
    )

    FrappePermissionMatrixRepository().ensure_custom_permission_baseline(
        _managed_doctypes()
    )


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
