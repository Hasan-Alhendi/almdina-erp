from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CUSTOM_PERMISSION_DEFINITIONS,
)


def sync_permission_types() -> None:
    """Install the capability columns managed through Role Permission Manager.

    Permission Type itself creates the required DocPerm and Custom DocPerm fields
    in Frappe v16. No role assignment is seeded here: the System Manager remains
    the sole owner of which roles receive each business capability.
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


__all__ = ["sync_permission_types"]
