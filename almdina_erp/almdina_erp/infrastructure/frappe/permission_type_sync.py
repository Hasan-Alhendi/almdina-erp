from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
)


def _managed_doctypes() -> tuple[str, ...]:
    return tuple(
        sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()})
    )


def reconcile_custom_permission_projections() -> None:
    """Re-save existing Almdina role states through the current granular model."""

    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return
    doctypes = [
        doctype for doctype in _managed_doctypes() if frappe.db.exists("DocType", doctype)
    ]
    if not doctypes:
        return

    roles = sorted(
        {
            str(role)
            for role in frappe.get_all(
                "Custom DocPerm",
                filters={"parent": ["in", doctypes], "permlevel": 0},
                pluck="role",
                order_by="role asc",
            )
            if role
        }
    )
    if not roles:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
        PROTECTED_ROLES,
    )

    repository = FrappePermissionMatrixRepository()
    for resolved in roles:
        if resolved in PROTECTED_ROLES or not frappe.db.exists("Role", resolved):
            continue
        effective = repository.role_state(resolved)["capabilities"]
        repository.save_role_state(resolved, effective)


def sync_permission_types() -> None:
    """Install granular capability columns without creating or assigning roles."""

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

    reconcile_custom_permission_projections()
    FrappePermissionMatrixRepository().ensure_custom_permission_baseline(
        _managed_doctypes()
    )


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
