from __future__ import annotations

import frappe


ALMDINA_APP = "almdina_erp"
APP_DESK_ROUTE = "/desk/almdina-erp"
LEGACY_DESK_ROUTE = "/desk"
PRIMARY_SHELL = "Almdina ERP"


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


def dock_layer_has_primary_shell(dock_name: str) -> bool:
    """Return True when a Dock layer still exposes the primary Almdina shell."""

    if not dock_name or not frappe.db.exists("DocType", "Dock Item"):
        return False

    items = frappe.get_all(
        "Dock Item",
        filters={"parent": dock_name, "parenttype": "Dock"},
        fields=["link_type", "link_to", "hidden"],
    )
    for item in items:
        if (
            str(item.get("link_type") or "") == "Sidebar"
            and str(item.get("link_to") or "") == PRIMARY_SHELL
            and not int(item.get("hidden") or 0)
        ):
            return True
    return False


def list_incomplete_almdina_dock_layers() -> list[str]:
    """Non-standard Almdina Dock layers that omit the primary shell.

    Complete site/user arrangements that still name ``Almdina ERP`` are left
    alone. Only layers that hide the primary shell (for example a Reports-only
    pre-upgrade site layer) are candidates for reset.
    """

    if not frappe.db.exists("DocType", "Dock"):
        return []

    names = frappe.get_all(
        "Dock",
        filters={"app": ALMDINA_APP, "standard": 0},
        pluck="name",
    )
    return [name for name in names if not dock_layer_has_primary_shell(name)]


def _clear_incomplete_site_dock_layers() -> bool:
    """Drop only incomplete non-standard Almdina Dock layers.

    Frappe 16.60 keeps site/user Dock arrangements over the app's exported rail.
    An incomplete pre-upgrade site layer that only listed Reports hid the primary
    Almdina ERP shell. Clearing those incomplete layers is idempotent and restores
    the exported dock without wiping healthy custom arrangements.
    """

    names = list_incomplete_almdina_dock_layers()
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


__all__ = [
    "APP_DESK_ROUTE",
    "PRIMARY_SHELL",
    "dock_layer_has_primary_shell",
    "list_incomplete_almdina_dock_layers",
    "sync_native_app_navigation",
]
