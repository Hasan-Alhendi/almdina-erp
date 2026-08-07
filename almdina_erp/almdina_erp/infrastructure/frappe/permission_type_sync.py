from __future__ import annotations

import frappe
from frappe.core.doctype.permission_type.permission_type import (
    CUSTOM_FIELD_TARGET,
    get_doctype_ptype_map,
)

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
    has_settings_grant = any(
        normalized.get(capability) for capability in actual_settings_grants
    )
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
    the current projected repository removes stale rights and also repairs the
    native permissions of related resources such as Cutting Plan and Production
    Stage. No role is created and no absent business capability is granted.
    """

    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return
    doctypes = [
        doctype
        for doctype in _managed_doctypes()
        if frappe.db.exists("DocType", doctype)
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
        PROTECTED_ROLES,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
        ProjectedPermissionMatrixRepository,
    )

    repository = ProjectedPermissionMatrixRepository()
    for resolved in roles:
        if resolved in PROTECTED_ROLES or not frappe.db.exists("Role", resolved):
            continue
        effective = repository.role_state(resolved)["capabilities"]
        repository.save_role_state(
            resolved,
            _remove_legacy_settings_read(effective),
        )


def _ensure_permission_type_schema(permission_type_name: str) -> None:
    """Repair generated permission fields for a pre-existing Permission Type.

    Long-lived sites can contain the Permission Type record while one of its
    generated Custom Fields is missing or has stale ``depends_on`` metadata.
    Frappe only creates those fields in PermissionType.on_update, so merely
    skipping an existing row leaves the role matrix looking saved while native
    permission checks cannot see the capability.
    """

    document = frappe.get_doc("Permission Type", permission_type_name)
    for target in CUSTOM_FIELD_TARGET:
        document.create_custom_field(target)


def sync_permission_types() -> None:
    """Install and repair capability columns, then normalize role projections.

    Permission Type creates the required DocPerm and Custom DocPerm fields in
    Frappe v16. Existing records are repaired as well as new ones so upgrades are
    self-healing. No role assignment is seeded here: administrators remain the
    sole owners of which roles receive each business capability.
    """

    if not frappe.db.exists("DocType", "Permission Type"):
        return

    for definition in CUSTOM_PERMISSION_DEFINITIONS:
        if not frappe.db.exists("DocType", definition.applies_to):
            continue
        existing = frappe.db.exists(
            "Permission Type",
            {
                "perm_type": definition.permission_type,
                "doc_type": definition.applies_to,
            },
        )
        if existing:
            _ensure_permission_type_schema(str(existing))
            continue
        frappe.get_doc(
            {
                "doctype": "Permission Type",
                "perm_type": definition.permission_type,
                "doc_type": definition.applies_to,
            }
        ).insert(ignore_permissions=True)

    # Frappe v16 caches the permission-type map per worker process with
    # @site_cache. Invalidate it explicitly after schema repair so a long-lived
    # process cannot keep authorizing against the pre-migration map.
    get_doctype_ptype_map.clear_cache()
    for permission_doctype in ("DocPerm", "Custom DocPerm", "DocShare"):
        frappe.clear_cache(doctype=permission_doctype)

    from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
        ProjectedPermissionMatrixRepository,
    )

    # Reconcile only roles that already had custom rows. Baseline creation adds
    # standard roles to Custom DocPerm, so doing it first would make untouched
    # roles look like permission-console roles and could normalize rights this
    # app does not own.
    reconcile_custom_permission_projections()
    ProjectedPermissionMatrixRepository().ensure_custom_permission_baseline(
        _managed_doctypes()
    )


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
