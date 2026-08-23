from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


MEMBERSHIP_FIELD = "custom_almdina_workforce_member"
LEGACY_ALMDINA_APP = "almdina_erp"


def sync_workforce_membership_metadata() -> None:
    """Create the app-owned workforce membership marker and backfill legacy sites.

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
    for user in sorted(members):
        if frappe.db.exists("User", user):
            frappe.db.set_value(
                "User",
                user,
                MEMBERSHIP_FIELD,
                1,
                update_modified=False,
            )

    frappe.clear_cache(doctype="User")


__all__ = ["MEMBERSHIP_FIELD", "sync_workforce_membership_metadata"]
