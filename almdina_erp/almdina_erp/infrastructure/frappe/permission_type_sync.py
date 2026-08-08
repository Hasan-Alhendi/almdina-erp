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
from almdina_erp.almdina_erp.infrastructure.frappe.automatic_role_permission_cleanup import (
    revoke_automatic_role_business_grants,
)
from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    AUDIT_DOCTYPE,
    STATE_DOCTYPE,
    CanonicalPermissionStateRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


def _managed_doctypes() -> tuple[str, ...]:
    return tuple(
        sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()})
    )


def _remove_legacy_settings_read(capabilities: dict[str, bool]) -> dict[str, bool]:
    """Remove the old administration-derived Settings read projection."""

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


def _roles_requiring_reconciliation(doctypes: list[str]) -> list[str]:
    """Collect roles with legacy projections, canonical state, or explicit audit."""

    roles: set[str] = set()
    if frappe.db.exists("DocType", "Custom DocPerm"):
        roles.update(
            str(role)
            for role in frappe.get_all(
                "Custom DocPerm",
                filters={"parent": ["in", doctypes], "permlevel": 0},
                pluck="role",
                order_by="role asc",
            )
            if role
        )
    if frappe.db.exists("DocType", STATE_DOCTYPE):
        roles.update(
            str(role)
            for role in frappe.get_all(
                STATE_DOCTYPE,
                pluck="role",
                order_by="role asc",
            )
            if role
        )
    if frappe.db.exists("DocType", AUDIT_DOCTYPE):
        roles.update(
            str(role)
            for role in frappe.get_all(
                AUDIT_DOCTYPE,
                pluck="role",
                order_by="role asc",
            )
            if role
        )
    return sorted(roles)


def reconcile_custom_permission_projections() -> None:
    """Rebuild Frappe projections exclusively from canonical Almdina state.

    Legacy DocPerm/Custom DocPerm rows are never imported as business authority.
    On the first migration to canonical state, the latest explicit Almdina audit
    is trusted as provenance. Roles without an audit fail closed to no business
    capabilities. The resulting canonical state is then projected back to Frappe,
    removing stale permissions that old baselines may have resurrected.
    """

    doctypes = [
        doctype
        for doctype in _managed_doctypes()
        if frappe.db.exists("DocType", doctype)
    ]
    if not doctypes or not frappe.db.exists("DocType", STATE_DOCTYPE):
        return

    roles = _roles_requiring_reconciliation(doctypes)
    if not roles:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
        ProjectedPermissionMatrixRepository,
    )

    canonical = CanonicalPermissionStateRepository()
    prepared: dict[str, dict[str, bool]] = {}
    for resolved in roles:
        if resolved in PROTECTED_SYSTEM_ROLES or not frappe.db.exists("Role", resolved):
            continue
        state = canonical.bootstrap_fail_closed(resolved)
        prepared[resolved] = _remove_legacy_settings_read(state)

    if prepared:
        ProjectedPermissionMatrixRepository().save_role_states(prepared)


def _ensure_permission_type_schema(permission_type_name: str) -> None:
    """Repair generated permission fields for a pre-existing Permission Type."""

    document = frappe.get_doc("Permission Type", permission_type_name)
    for target in CUSTOM_FIELD_TARGET:
        document.create_custom_field(target)


def sync_permission_types() -> None:
    """Install capability columns and rebuild projections from canonical state."""

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

    # Platform roles are never Almdina business authority.
    revoke_automatic_role_business_grants()

    get_doctype_ptype_map.clear_cache()
    for permission_doctype in ("DocPerm", "Custom DocPerm", "DocShare"):
        frappe.clear_cache(doctype=permission_doctype)

    from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
        ProjectedPermissionMatrixRepository,
    )

    # Canonical bootstrap happens before any baseline can be trusted. Existing
    # business grants are restored only from explicit audit provenance; otherwise
    # they fail closed. Then the canonical state overwrites all legacy projections.
    reconcile_custom_permission_projections()
    ProjectedPermissionMatrixRepository().ensure_custom_permission_baseline(
        _managed_doctypes()
    )

    # A baseline may preserve native Frappe rows for compatibility, but it must
    # never become business authority because the gateway reads canonical state.
    revoke_automatic_role_business_grants()


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
