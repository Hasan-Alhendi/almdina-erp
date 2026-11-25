from __future__ import annotations

import frappe


ALMDINA_APP = "almdina_erp"
APP_DESK_ROUTE = "/desk/almdina-erp"
LEGACY_DESK_ROUTE = "/desk"


def _sync_desktop_icon_route() -> bool:
    """Repair only Almdina's stale native Frappe Desktop Icon route.

    Frappe persists ``add_to_apps_screen.route`` into Desktop Icon when the icon
    is first created. Updating hooks later does not rewrite an existing row. We
    migrate only the exact legacy route owned by this app and leave site-local
    custom routes untouched.
    """

    if not frappe.db.exists("DocType", "Desktop Icon"):
        return False

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
        return False

    for name in names:
        frappe.db.set_value(
            "Desktop Icon",
            name,
            "link",
            APP_DESK_ROUTE,
            update_modified=False,
        )
    return True


def _clear_incomplete_site_dock_layers() -> bool:
    """Drop non-standard Almdina Dock layers so the shipped standard dock wins.

    Frappe 16.60 keeps site/user Dock arrangements over the app's exported rail.
    An incomplete pre-upgrade site layer that only listed Reports hid the primary
    Almdina ERP shell. Clearing those layers is idempotent and restores the
    exported dock without touching other apps.
    """

    if not frappe.db.exists("DocType", "Dock"):
        return False

    names = frappe.get_all(
        "Dock",
        filters={"app": ALMDINA_APP, "standard": 0},
        pluck="name",
    )
    if not names:
        return False

    for name in names:
        frappe.delete_doc("Dock", name, force=True, ignore_permissions=True)
    return True


def sync_native_app_navigation() -> None:
    """Repair Almdina-owned native Desk navigation metadata after migrate."""

    changed = False
    changed = _sync_desktop_icon_route() or changed
    changed = _clear_incomplete_site_dock_layers() or changed
    if not changed:
        return

    # These are native Frappe caches that contain Desktop Icon / app navigation
    # payloads. Clear the whole hashes because migrations are site-wide.
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")


__all__ = ["APP_DESK_ROUTE", "sync_native_app_navigation"]
