from __future__ import annotations

import frappe


ALMDINA_APP = "almdina_erp"
APP_DESK_ROUTE = "/desk/almdina-erp"
LEGACY_DESK_ROUTE = "/desk"


def sync_native_app_navigation() -> None:
    """Repair only Almdina's stale native Frappe Desktop Icon route.

    Frappe persists ``add_to_apps_screen.route`` into Desktop Icon when the icon
    is first created. Updating hooks later does not rewrite an existing row. We
    migrate only the exact legacy route owned by this app and leave site-local
    custom routes untouched.
    """

    if not frappe.db.exists("DocType", "Desktop Icon"):
        return

    names = frappe.get_all(
        "Desktop Icon",
        filters={
            "app": ALMDINA_APP,
            "icon_type": "App",
            "link": LEGACY_DESK_ROUTE,
        },
        pluck="name",
    )
    if not names:
        return

    for name in names:
        frappe.db.set_value(
            "Desktop Icon",
            name,
            "link",
            APP_DESK_ROUTE,
            update_modified=False,
        )

    # These are native Frappe caches that contain Desktop Icon / app navigation
    # payloads. Clear the whole hashes because migrations are site-wide.
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")


__all__ = ["APP_DESK_ROUTE", "sync_native_app_navigation"]
