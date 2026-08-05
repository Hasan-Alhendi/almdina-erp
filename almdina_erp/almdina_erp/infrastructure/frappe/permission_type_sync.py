from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
    FACTORY_SETTINGS_CAPABILITIES,
    WORKFORCE_CAPABILITIES,
    Capability,
)


def _managed_doctypes() -> tuple[str, ...]:
    return tuple(
        sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()})
    )


def _remove_legacy_settings_read(capabilities: dict[str, bool]) -> dict[str, bool]:
    """Remove the old administration-derived Settings read projection.

    Before granular settings capabilities existed, workforce and permission
    administration grants projected ``read=1`` onto the Settings singleton.
    Preserve an explicit read-only Settings role, and preserve roles that own an
    actual Settings edit capability, but fail closed for old unrelated admin
    roles. Administrators can explicitly re-grant view access when it is wanted.
    """

    normalized = dict(capabilities)
    if not normalized.get(Capability.VIEW_FACTORY_SETTINGS):
        return normalized
    actual_settings_grants = FACTORY_SETTINGS_CAPABILITIES.difference(
        {Capability.VIEW_FACTORY_SETTINGS}
    )
    has_settings_grant = any(normalized.get(capability) for capability in actual_settings_grants)
    legacy_admin_grant = normalized.get(Capability.MANAGE_PERMISSIONS) or any(
        normalized.get(capability) for capability in WORKFORCE_CAPABILITIES
    )
    if legacy_admin_grant and not has_settings_grant:
        normalized[Capability.VIEW_FACTORY_SETTINGS] = False
    return normalized


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
        repository.save_role_state(
            resolved,
            _remove_legacy_settings_read(effective),
        )


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

    from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
        FrappePermissionMatrixRepository,
    )

    # Reconcile only roles that already had custom rows. Baseline creation adds
    # the standard roles to Custom DocPerm, so doing it first would make those
    # untouched roles look like permission-console roles and could normalize
    # rights that this app does not own.
    reconcile_custom_permission_projections()
    FrappePermissionMatrixRepository().ensure_custom_permission_baseline(
        _managed_doctypes()
    )


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
