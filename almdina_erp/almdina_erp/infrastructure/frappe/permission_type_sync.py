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
    """Normalize existing role overrides after capability model upgrades.

    Earlier releases projected administration capabilities onto broad standard
    ``read``/``write`` rights. Re-saving each existing Almdina role state through
    the current repository removes stale standard rights, applies new safe
    dependencies, and preserves unrelated Frappe permission columns. No role is
    created and no capability absent from its effective state is granted.
    """

    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return
    doctypes = [
        doctype for doctype in _managed_doctypes() if frappe.db.exists("DocType", doctype)
    ]
    if not doctypes:
        return

    roles = frappe.get_all(
        "Custom DocPerm",
        filters={"parent": ["in", doctypes], "permlevel": 0},
        pluck="role",
        distinct=True,
        order_by="role asc",
    )
    if not roles:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
        PROTECTED_ROLES,
    )

    repository = FrappePermissionMatrixRepository()
    for role in roles:
        resolved = str(role or "").strip()
        if not resolved or resolved in PROTECTED_ROLES or not frappe.db.exists("Role", resolved):
            continue
        effective = repository.role_state(resolved)["capabilities"]
        repository.save_role_state(resolved, effective)


def sync_permission_types() -> None:
    """Install capability columns and normalize existing role projections.

    Permission Type creates the required DocPerm and Custom DocPerm fields in
    Frappe v16. No role assignment is seeded here: administrators remain the sole
    owners of which roles receive each business capability.
    """

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

    reconcile_custom_permission_projections()


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
