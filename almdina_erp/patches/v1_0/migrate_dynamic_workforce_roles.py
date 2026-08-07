from __future__ import annotations

import uuid

import frappe

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    LEGACY_ROLE_CAPABILITIES,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.role_management import PROTECTED_ROLE_NAMES
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


_METADATA_DOCTYPE = "Almdina Role Metadata"
_SETTINGS_DOCTYPE = "Almdina ERP Settings"
_LEGACY_ASSIGNMENT_PERMISSION = "assign_workforce_profile"


def _doctype_exists(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype))


def _adopt_existing_workforce_roles() -> None:
    """Mark historical Almdina business roles as dynamically managed roles."""

    if not _doctype_exists(_METADATA_DOCTYPE):
        return
    for role in sorted(LEGACY_ROLE_CAPABILITIES):
        if role in PROTECTED_ROLE_NAMES or not frappe.db.exists("Role", role):
            continue
        existing = frappe.db.get_value(
            _METADATA_DOCTYPE,
            {"role": role},
            "name",
        )
        if existing:
            frappe.db.set_value(
                _METADATA_DOCTYPE,
                existing,
                "managed_by_almdina",
                1,
                update_modified=False,
            )
            continue
        frappe.get_doc(
            {
                "doctype": _METADATA_DOCTYPE,
                "role": role,
                "role_uid": str(uuid.uuid4()),
                "description": "Migrated historical Almdina role.",
                "managed_by_almdina": 1,
            }
        ).insert(ignore_permissions=True)


def _copy_role_assignment_grants() -> None:
    """Copy the retired assignment grant to the direct role-assignment grant.

    The old Permission Type may remain in the schema as historical metadata, but
    active authorization no longer reads it after this patch.
    """

    sync_permission_types()
    new_permission = Capability.ASSIGN_USER_ROLES
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        if not _doctype_exists(permission_doctype):
            continue
        meta = frappe.get_meta(permission_doctype)
        if not meta.has_field(_LEGACY_ASSIGNMENT_PERMISSION) or not meta.has_field(
            new_permission
        ):
            continue
        rows = frappe.get_all(
            permission_doctype,
            filters={
                "parent": _SETTINGS_DOCTYPE,
                _LEGACY_ASSIGNMENT_PERMISSION: 1,
            },
            pluck="name",
            limit_page_length=0,
        )
        for name in rows:
            frappe.db.set_value(
                permission_doctype,
                name,
                new_permission,
                1,
                update_modified=False,
            )


def execute() -> None:
    _adopt_existing_workforce_roles()
    _copy_role_assignment_grants()
    frappe.clear_cache()
