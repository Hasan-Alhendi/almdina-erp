from __future__ import annotations

import frappe
from frappe.core.doctype.permission_type.permission_type import (
    CUSTOM_FIELD_TARGET,
    get_doctype_ptype_map,
)

from almdina_erp.almdina_erp.application.security.business_capability_state import (
    normalize_business_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
    CUTTING_PLAN_DOCTYPE,
)
from almdina_erp.almdina_erp.infrastructure.frappe.automatic_role_permission_cleanup import (
    revoke_automatic_role_business_grants,
)
from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)


_LEGACY_PLAN_PERMISSION_PARENT = "Door Cutting Order"


def _managed_doctypes() -> tuple[str, ...]:
    return tuple(
        sorted({definition.applies_to for definition in CAPABILITY_CATALOG.values()})
    )


def _relocated_plan_permission_types() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                definition.permission_type
                for definition in CUSTOM_PERMISSION_DEFINITIONS
                if definition.applies_to == CUTTING_PLAN_DOCTYPE
            }
        )
    )


def _roles_requiring_reconciliation(doctypes: list[str]) -> list[str]:
    """Collect editable roles that already have Custom DocPerm rows to refresh."""

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
    return sorted(roles)


def _role_state_for_reconciliation(role: str) -> dict[str, bool]:
    """Read live Custom DocPerm grants only.

    Explicit deny-all remains deny-all. The retired ``Almdina Role Capability
    State`` mirror is never consulted here; one-time upgrade bridging belongs
    exclusively in ``retire_canonical_permission_runtime``.
    """

    reader = CustomDocPermCapabilityReader()
    try:
        current = reader.role_capabilities(role)
    except ValueError:
        return normalize_business_capability_state({})
    return current


def reconcile_custom_permission_projections() -> None:
    """Refresh Custom DocPerm grants from live DocPerm authority only.

    Runtime and recurring migrate/sync authority is Custom DocPerm for editable
    factory roles. Historical ``Almdina Role Capability State`` rows are never
    re-imported here. Audit rows never become grants.
    """

    doctypes = [
        doctype
        for doctype in _managed_doctypes()
        if frappe.db.exists("DocType", doctype)
    ]
    if not doctypes:
        return

    roles = _roles_requiring_reconciliation(doctypes)
    if not roles:
        return

    from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
        ProjectedPermissionMatrixRepository,
    )

    prepared: dict[str, dict[str, bool]] = {}
    for resolved in roles:
        if resolved in PROTECTED_SYSTEM_ROLES or not frappe.db.exists("Role", resolved):
            continue
        prepared[resolved] = _role_state_for_reconciliation(resolved)

    if prepared:
        ProjectedPermissionMatrixRepository().save_role_states(prepared)


def _ensure_permission_type_schema(permission_type_name: str) -> None:
    """Repair generated permission fields for a pre-existing Permission Type."""

    document = frappe.get_doc("Permission Type", permission_type_name)
    for target in CUSTOM_FIELD_TARGET:
        document.create_custom_field(target)


def _clear_relocated_cutting_plan_projections() -> None:
    """Remove stale DCO projections after Plan capability ownership moves.

    Business grants live in Custom DocPerm columns. Only generated Frappe
    projections are cleaned so a Plan permission cannot appear active on both
    aggregates after migration.
    """

    permission_types = _relocated_plan_permission_types()
    if not permission_types:
        return

    if frappe.db.exists("DocType", "Custom DocPerm"):
        meta = frappe.get_meta("Custom DocPerm")
        stale_fields = [value for value in permission_types if meta.has_field(value)]
        if stale_fields:
            updates = {fieldname: 0 for fieldname in stale_fields}
            for row_name in frappe.get_all(
                "Custom DocPerm",
                filters={"parent": _LEGACY_PLAN_PERMISSION_PARENT},
                pluck="name",
            ):
                frappe.db.set_value(
                    "Custom DocPerm",
                    row_name,
                    updates,
                    update_modified=False,
                )

    if frappe.db.exists("DocType", "Permission Type"):
        stale_names = frappe.get_all(
            "Permission Type",
            filters={
                "doc_type": _LEGACY_PLAN_PERMISSION_PARENT,
                "perm_type": ["in", list(permission_types)],
            },
            pluck="name",
        )
        if stale_names:
            frappe.db.delete("Permission Type", {"name": ["in", stale_names]})


def sync_permission_types() -> None:
    """Install capability columns and refresh Custom DocPerm factory grants.

    Recurring sync never re-imports ``Almdina Role Capability State``. Legacy
    cutover bridging remains in the one-time retire patch only.
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

    _clear_relocated_cutting_plan_projections()

    # Platform roles are never Almdina business authority.
    revoke_automatic_role_business_grants()

    get_doctype_ptype_map.clear_cache()
    for permission_doctype in ("DocPerm", "Custom DocPerm", "DocShare"):
        frappe.clear_cache(doctype=permission_doctype)

    from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
        ProjectedPermissionMatrixRepository,
    )

    # Refresh grants from live DocPerm authority only, then re-assert
    # protected-role cleanup.
    reconcile_custom_permission_projections()
    ProjectedPermissionMatrixRepository().ensure_custom_permission_baseline(
        _managed_doctypes()
    )

    revoke_automatic_role_business_grants()


__all__ = ["reconcile_custom_permission_projections", "sync_permission_types"]
