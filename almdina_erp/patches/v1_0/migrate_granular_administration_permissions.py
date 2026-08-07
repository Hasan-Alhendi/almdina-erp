from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


_SETTINGS_DOCTYPE = "Almdina ERP Settings"
_LEGACY_MANAGE_USERS = "manage_users"
_LEGACY_MANAGE_FACTORY_SETTINGS = "manage_factory_settings"

_WORKFORCE_GRANTS = (
    Capability.VIEW_USERS,
    Capability.CREATE_USERS,
    Capability.EDIT_USERS,
    Capability.ASSIGN_USER_ROLES,
    Capability.ENABLE_USERS,
    Capability.DISABLE_USERS,
    Capability.RESET_USER_PASSWORD,
)
_FACTORY_GRANTS = (
    Capability.VIEW_FACTORY_SETTINGS,
    Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
    Capability.EDIT_FACTORY_COST_DEFAULTS,
    Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
    Capability.VIEW_PRODUCTION_ROUTINGS,
)


def _doctype_exists(doctype: str) -> bool:
    return bool(frappe.db.exists("DocType", doctype))


def _materialize(
    permission_doctype: str,
    *,
    legacy_field: str,
    grants: tuple[str, ...],
) -> None:
    if not _doctype_exists(permission_doctype):
        return
    meta = frappe.get_meta(permission_doctype)
    if not meta.has_field(legacy_field):
        return
    available = tuple(grant for grant in grants if meta.has_field(grant))
    if not available:
        return
    rows = frappe.get_all(
        permission_doctype,
        filters={
            "parent": _SETTINGS_DOCTYPE,
            legacy_field: 1,
        },
        pluck="name",
        limit_page_length=0,
    )
    for name in rows:
        frappe.db.set_value(
            permission_doctype,
            name,
            {grant: 1 for grant in available},
            update_modified=False,
        )


def execute() -> None:
    """Preserve effective access before retiring broad umbrella capabilities."""

    sync_permission_types()
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        _materialize(
            permission_doctype,
            legacy_field=_LEGACY_MANAGE_USERS,
            grants=_WORKFORCE_GRANTS,
        )
        _materialize(
            permission_doctype,
            legacy_field=_LEGACY_MANAGE_FACTORY_SETTINGS,
            grants=_FACTORY_GRANTS,
        )
    frappe.clear_cache()
