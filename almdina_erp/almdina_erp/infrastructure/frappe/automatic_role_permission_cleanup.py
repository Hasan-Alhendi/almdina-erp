from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    PROTECTED_ROLES,
)


ALMDINA_MODULE = "Almdina ERP"


def _almdina_business_doctypes() -> tuple[str, ...]:
    """Return app-owned non-child DocTypes whose access is capability-managed."""

    if not frappe.db.exists("DocType", "DocType"):
        return ()
    return tuple(
        sorted(
            str(name)
            for name in frappe.get_all(
                "DocType",
                filters={"module": ALMDINA_MODULE, "istable": 0},
                pluck="name",
                limit=0,
            )
            if name
        )
    )


def revoke_automatic_role_business_grants() -> None:
    """Remove legacy Almdina grants inherited from Frappe automatic roles.

    ``All`` and ``Desk User`` are attached automatically to users by Frappe and
    therefore must never carry factory business permissions. Older releases
    could leave DocPerm/Custom DocPerm rows for those roles after the role-based
    bootstrap was retired. If such a row survives, a user with an otherwise
    empty factory role can inherit create/write/delete or protected field access.

    Only app-owned Almdina DocTypes are touched. Core ERPNext DocTypes such as
    Customer are deliberately excluded so this cleanup cannot change unrelated
    ERPNext authorization policy.
    """

    doctypes = _almdina_business_doctypes()
    if not doctypes:
        return

    automatic_roles = tuple(sorted(PROTECTED_ROLES))
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        if not frappe.db.exists("DocType", permission_doctype):
            continue
        for doctype in doctypes:
            frappe.db.delete(
                permission_doctype,
                {
                    "parent": doctype,
                    "role": ["in", automatic_roles],
                },
            )

    for doctype in doctypes:
        frappe.clear_cache(doctype=doctype)

    # Automatic roles affect every System User, so clear the global permission
    # metadata after the database cleanup rather than trying to enumerate users.
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        frappe.clear_cache(doctype=permission_doctype)


__all__ = ["revoke_automatic_role_business_grants"]
