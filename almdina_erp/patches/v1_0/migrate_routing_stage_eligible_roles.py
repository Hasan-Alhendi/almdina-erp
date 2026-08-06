from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
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
        try:
            roles = decode_eligible_roles(
                raw,
                legacy_role=legacy_role or None,
            )
        except ValueError:
            # A malformed partially-migrated row is recoverable only from its
            # historical Link. Never invent a role when both sources are empty.
            roles = (legacy_role,) if legacy_role else ()
        if not roles:
            continue

        encoded = encode_eligible_roles(roles)
        display = eligible_roles_display(roles)
        if raw == encoded and str(row.eligible_roles_display or "") == display:
            continue
        frappe.db.set_value(
            doctype,
            row.name,
            {
                "eligible_roles_json": encoded,
                "eligible_roles_display": display,
                "operational_role": roles[0],
            },
            update_modified=False,
        )


def execute() -> None:
    """Normalize historical stage role snapshots without creating role defaults."""

    _migrate("Production Routing Stage")
    _migrate("Production Stage")


__all__ = ["execute"]
