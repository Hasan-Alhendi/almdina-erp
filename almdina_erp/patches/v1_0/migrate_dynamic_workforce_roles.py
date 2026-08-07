from __future__ import annotations

import uuid
from collections import defaultdict

import frappe

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    LEGACY_ROLE_CAPABILITIES,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CUSTOM_PERMISSION_DEFINITIONS,
    Capability,
)
from almdina_erp.almdina_erp.domain.security.role_management import PROTECTED_ROLE_NAMES
from almdina_erp.almdina_erp.infrastructure.frappe.legacy_permission_bootstrap import (
    bootstrap_legacy_role_permissions,
)
from almdina_erp.patches.v1_0.permission_migration_helpers import ensure_permission_types


_METADATA_DOCTYPE = "Almdina Role Metadata"
_SETTINGS_DOCTYPE = "Almdina ERP Settings"
_LEGACY_ASSIGNMENT_PERMISSION = "assign_workforce_profile"
_LEGACY_ALMDINA_PERMISSION_FIELDS = frozenset(
    {
        _LEGACY_ASSIGNMENT_PERMISSION,
        "manage_users",
        "manage_factory_settings",
    }
)


def _doctype_exists(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype))


def _custom_permission_fields_by_doctype() -> dict[str, frozenset[str]]:
    grouped: defaultdict[str, set[str]] = defaultdict(set)
    for definition in CUSTOM_PERMISSION_DEFINITIONS:
        grouped[str(definition.applies_to)].add(str(definition.permission_type))
    grouped[_SETTINGS_DOCTYPE].update(_LEGACY_ALMDINA_PERMISSION_FIELDS)
    return {doctype: frozenset(fields) for doctype, fields in grouped.items()}


def _roles_with_almdina_capability_grants() -> frozenset[str]:
    """Find existing roles that already carry unmistakable Almdina grants."""

    roles: set[str] = set()
    fields_by_doctype = _custom_permission_fields_by_doctype()
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        if not _doctype_exists(permission_doctype):
            continue
        meta = frappe.get_meta(permission_doctype)
        for target_doctype, candidate_fields in fields_by_doctype.items():
            fields = sorted(field for field in candidate_fields if meta.has_field(field))
            if not fields:
                continue
            rows = frappe.get_all(
                permission_doctype,
                filters={"parent": target_doctype},
                fields=["role", *fields],
                limit_page_length=0,
            )
            for row in rows:
                role = str(row.get("role") or "").strip()
                if not role or role in PROTECTED_ROLE_NAMES:
                    continue
                if any(bool(row.get(field)) for field in fields):
                    roles.add(role)
    return frozenset(roles)


def _roles_with_permission_audit() -> frozenset[str]:
    """Treat a prior Almdina permission audit as explicit ownership evidence."""

    if not _doctype_exists("Almdina Permission Audit"):
        return frozenset()
    return frozenset(
        str(role).strip()
        for role in frappe.get_all(
            "Almdina Permission Audit",
            pluck="role",
            limit_page_length=0,
        )
        if str(role or "").strip()
    )


def _existing_almdina_role_candidates() -> tuple[str, ...]:
    candidates = (
        set(LEGACY_ROLE_CAPABILITIES)
        | set(_roles_with_almdina_capability_grants())
        | set(_roles_with_permission_audit())
    )
    return tuple(sorted(candidates.difference(PROTECTED_ROLE_NAMES)))


def _adopt_existing_workforce_roles() -> None:
    if not _doctype_exists(_METADATA_DOCTYPE):
        return
    historical = frozenset(LEGACY_ROLE_CAPABILITIES)
    for role in _existing_almdina_role_candidates():
        # Migration adopts evidence-backed roles that already exist. It never
        # creates a Role document or invents a business role on a fresh site.
        if not frappe.db.exists("Role", role):
            continue
        existing = frappe.db.get_value(_METADATA_DOCTYPE, {"role": role}, "name")
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
                "description": (
                    "Migrated historical Almdina role."
                    if role in historical
                    else "Migrated existing Almdina-managed role."
                ),
                "managed_by_almdina": 1,
            }
        ).insert(ignore_permissions=True)


def _copy_role_assignment_grants() -> None:
    new_permission = Capability.ASSIGN_USER_ROLES
    ensure_permission_types((new_permission,))
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        if not _doctype_exists(permission_doctype):
            continue
        meta = frappe.get_meta(permission_doctype)
        if not meta.has_field(_LEGACY_ASSIGNMENT_PERMISSION) or not meta.has_field(new_permission):
            continue
        rows = frappe.get_all(
            permission_doctype,
            filters={"parent": _SETTINGS_DOCTYPE, _LEGACY_ASSIGNMENT_PERMISSION: 1},
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
    """Adopt existing Almdina roles, then preserve historical access safely."""

    _adopt_existing_workforce_roles()
    # The pre-model bootstrap may have run before role metadata existed. Ensure
    # all current fields now exist, then retry the idempotent bootstrap after
    # adoption so existing users keep their effective permissions.
    ensure_permission_types(ALL_CAPABILITIES)
    bootstrap_legacy_role_permissions()
    _copy_role_assignment_grants()
    frappe.clear_cache()
