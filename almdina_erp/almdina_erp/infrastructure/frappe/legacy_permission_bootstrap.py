from __future__ import annotations

from collections import defaultdict

import frappe

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    legacy_role_state,
    legacy_roles,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUSTOM_PERMISSION_DEFINITIONS,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
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


def _custom_fields_by_doctype() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    meta = frappe.get_meta("Custom DocPerm")
    for definition in CUSTOM_PERMISSION_DEFINITIONS:
        if meta.has_field(definition.permission_type):
            grouped[definition.applies_to].append(definition.permission_type)
    return dict(grouped)


def _has_permission_audit(role: str) -> bool:
    return bool(
        frappe.db.exists("DocType", "Almdina Permission Audit")
        and frappe.db.exists("Almdina Permission Audit", {"role": role})
    )


def _has_assigned_legacy_user(role: str) -> bool:
    """Return whether a real user still depends on one historical role.

    Fresh installations create the historical Role records for compatibility,
    but an unassigned role must remain empty.  The bootstrap is an upgrade aid
    for existing users, not a hidden permission template for future users.
    """

    if not frappe.db.exists("DocType", "Has Role"):
        return False
    return bool(
        frappe.db.exists(
            "Has Role",
            {
                "parenttype": "User",
                "role": role,
                "parent": ["not in", ["Administrator", "Guest"]],
            },
        )
    )


def _has_explicit_capability_grant(
    role: str,
    doctypes: list[str],
) -> bool:
    """Detect a matrix that was already configured with the capability model."""

    if not doctypes or not frappe.db.exists("DocType", "Custom DocPerm"):
        return False
    fields_by_doctype = _custom_fields_by_doctype()
    for doctype in doctypes:
        fields = fields_by_doctype.get(doctype) or []
        if not fields:
            continue
        rows = frappe.get_all(
            "Custom DocPerm",
            filters={
                "parent": doctype,
                "role": role,
                "permlevel": 0,
            },
            fields=fields,
        )
        if any(
            bool(row.get(fieldname))
            for row in rows
            for fieldname in fields
        ):
            return True
    return False


def _has_explicit_matrix(role: str, doctypes: list[str]) -> bool:
    # Console saves are append-only audited, including an intentionally empty
    # matrix. Direct Role Permission Manager configurations are recognized when
    # at least one of the new custom capability columns is enabled.
    return _has_permission_audit(role) or _has_explicit_capability_grant(
        role,
        doctypes,
    )


def bootstrap_legacy_role_permissions() -> list[str]:
    """Upgrade assigned historical roles without seeding fresh role records."""

    if not frappe.db.exists("DocType", "Custom DocPerm"):
        return []

    doctypes = _managed_doctypes()
    repository = FrappePermissionMatrixRepository()
    applied: list[str] = []

    for role in legacy_roles():
        if not frappe.db.exists("Role", role):
            continue
        if not _has_assigned_legacy_user(role):
            continue
        if _has_explicit_matrix(role, doctypes):
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
        applied.append(role)

    return applied


__all__ = ["BOOTSTRAP_SOURCE", "bootstrap_legacy_role_permissions"]
