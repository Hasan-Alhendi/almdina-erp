from __future__ import annotations

from collections.abc import Iterable

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import capability_definition


def ensure_permission_types(capabilities: Iterable[str]) -> None:
    """Create custom Permission Type fields needed by a migration only.

    Migrations must materialize legacy grants before the normal post-migrate
    reconciliation re-saves role matrices. Calling the full synchronizer here
    would reverse that order and could drop access before it is copied.
    """

    if not frappe.db.exists("DocType", "Permission Type"):
        return
    for capability in dict.fromkeys(str(value) for value in capabilities if value):
        definition = capability_definition(capability)
        if not definition.custom:
            continue
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


__all__ = ["ensure_permission_types"]
