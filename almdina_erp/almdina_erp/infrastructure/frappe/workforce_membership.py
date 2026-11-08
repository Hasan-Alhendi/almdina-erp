from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint


MEMBERSHIP_FIELD = "custom_almdina_workforce_member"
LEGACY_ALMDINA_APP = "almdina_erp"


def sync_workforce_membership_metadata() -> None:
    """Maintain only the app-owned membership field's metadata.

    Older releases used User.default_app as a membership flag. That couples
    membership to Frappe navigation and can override Role.home_page. The marker
    is intentionally hidden/read-only: it is application state, not a landing
    route setting.
    """

    if not frappe.db.exists("DocType", "User"):
        return

    create_custom_fields(
        {
            "User": [
                {
                    "fieldname": MEMBERSHIP_FIELD,
                    "label": "Almdina Workforce Member",
                    "fieldtype": "Check",
                    "default": "0",
                    "hidden": 1,
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Application-owned membership marker; Frappe navigation remains native.",
                }
            ]
        },
        update=True,
    )

    frappe.clear_cache(doctype="User")


def backfill_legacy_workforce_membership() -> int:
    """Transition historic workforce users once; never run on every migrate.

    Existing membership flags (including intentionally removed membership) are
    left untouched by subsequent app deployments because this runs as a Patch.
    Replays are safe: users already marked are not written again.
    """
    if not frappe.db.exists("DocType", "User"):
        return 0

    # Legacy users that were explicitly placed in Almdina scope retain their
    # membership, but their existing Frappe default_app/default_workspace values
    # are preserved. Administrators can clear or change those native settings.
    legacy_users = frappe.get_all(
        "User",
        filters={"default_app": LEGACY_ALMDINA_APP},
        pluck="name",
    )

    # Audit history is also an explicit record of workforce management. It keeps
    # users discoverable when an administrator already cleared the old defaults
    # before this migration runs.
    audited_users: list[str] = []
    if frappe.db.exists("DocType", "Almdina User Audit"):
        audited_users = frappe.get_all(
            "Almdina User Audit",
            filters={"target_user": ["not in", ["Administrator", "Guest"]]},
            pluck="target_user",
            distinct=True,
        )

    members = {
        str(user)
        for user in (*legacy_users, *audited_users)
        if user and str(user) not in {"Administrator", "Guest"}
    }
    if not members:
        return 0

    # Read current flags in one query. The migration must not UPDATE every
    # User row on every deployment; even no-op writes can collide with
    # concurrent user/session maintenance and abort the whole migration.
    existing = frappe.get_all(
        "User",
        filters={"name": ["in", sorted(members)]},
        fields=["name", MEMBERSHIP_FIELD],
        limit=0,
    )
    updated = 0
    for row in existing:
        if cint(row.get(MEMBERSHIP_FIELD)) == 1:
            continue
        frappe.db.set_value(
            "User", row["name"], MEMBERSHIP_FIELD, 1, update_modified=False
        )
        updated += 1

    if updated:
        frappe.clear_cache(doctype="User")
    return updated

__all__ = [
    "MEMBERSHIP_FIELD",
    "sync_workforce_membership_metadata",
    "backfill_legacy_workforce_membership",
]
