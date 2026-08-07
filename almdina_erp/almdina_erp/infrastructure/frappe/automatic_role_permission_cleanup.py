from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
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
    """Remove legacy Almdina grants inherited from protected system roles.

    ``All`` and ``Desk User`` are attached automatically to users by Frappe,
    while ``System Manager`` is a platform-wide administration role. None of
    them may become an implicit source of factory business capabilities.

    Only app-owned Almdina DocTypes are touched. Core ERPNext DocTypes such as
    Customer are deliberately excluded so this cleanup cannot change unrelated
    ERPNext authorization policy.
    """

    doctypes = _almdina_business_doctypes()
    if not doctypes:
        return

    protected_roles = tuple(sorted(PROTECTED_SYSTEM_ROLES))
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        if not frappe.db.exists("DocType", permission_doctype):
            continue
        for doctype in doctypes:
            frappe.db.delete(
                permission_doctype,
                {
                    "parent": doctype,
                    "role": ["in", protected_roles],
                },
            )

    for doctype in doctypes:
        frappe.clear_cache(doctype=doctype)

    # Protected roles may affect many System Users, so clear global permission
    # metadata after cleanup rather than relying on one user's cache only.
    for permission_doctype in ("DocPerm", "Custom DocPerm"):
        frappe.clear_cache(doctype=permission_doctype)


__all__ = ["revoke_automatic_role_business_grants"]
