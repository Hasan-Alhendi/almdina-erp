from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    eligible_roles_display,
    encode_eligible_roles,
)


def _migrate(doctype: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        return
    meta = frappe.get_meta(doctype)
    required_fields = {
        "operational_role",
        "eligible_roles_json",
        "eligible_roles_display",
    }
    if not all(meta.has_field(fieldname) for fieldname in required_fields):
        return

    rows = frappe.get_all(
        doctype,
        fields=[
            "name",
            "operational_role",
            "eligible_roles_json",
            "eligible_roles_display",
        ],
        limit_page_length=0,
    )
    for row in rows:
        raw = str(row.eligible_roles_json or "").strip()
        legacy_role = str(row.operational_role or "").strip()
        if raw or not legacy_role:
            continue
        roles = (legacy_role,)
        frappe.db.set_value(
            doctype,
            row.name,
            {
                "eligible_roles_json": encode_eligible_roles(roles),
                "eligible_roles_display": eligible_roles_display(roles),
            },
            update_modified=False,
        )


def execute() -> None:
    """Convert one historical role into a one-item eligible role snapshot."""

    _migrate("Production Routing Stage")
    _migrate("Production Stage")


__all__ = ["execute"]
