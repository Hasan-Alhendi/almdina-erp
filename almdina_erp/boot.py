from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.permission_context import (
    build_permission_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    is_order_entry_profile,
    is_shop_floor_only,
)

SHOP_FLOOR_WORKSPACE = "Shop Floor"
SHOP_FLOOR_PAGE = "shop-floor-inbox"
ORDER_ENTRY_ICON_MODULES = frozenset({"Almdina ERP"})
ALLOWED_MODULES_FOR_SHOP_FLOOR = ("Almdina ERP",)


def _roles() -> frozenset[str]:
    return frozenset(frappe.get_roles())


def _attach_permission_context(
    bootinfo: dict[str, Any], roles: frozenset[str]
) -> None:
    """Expose one immutable permission vocabulary to every Desk presenter."""

    bootinfo["almdina_permissions"] = build_permission_context(roles)


def _filter_order_entry(bootinfo: dict[str, Any]) -> None:
    bootinfo["almdina_order_entry_only"] = 1
    bootinfo["almdina_allowed_apps"] = ["almdina_erp"]

    module_map = bootinfo.get("module_wise_workspaces")
    if isinstance(module_map, dict):
        bootinfo["module_wise_workspaces"] = {
            key: value
            for key, value in module_map.items()
            if key in ORDER_ENTRY_ICON_MODULES
        }

    allowed_workspaces: set[str] = set()
    workspaces = bootinfo.get("workspaces")
    if isinstance(workspaces, dict):
        pages = workspaces.get("pages")
        if isinstance(pages, list):
            kept = [
                page
                for page in pages
                if not isinstance(page, dict)
                or page.get("module") in ORDER_ENTRY_ICON_MODULES
                or page.get("app") == "almdina_erp"
                or page.get("for_user") == frappe.session.user
            ]
            if kept:
                workspaces["pages"] = kept
                pages = kept
        for page in pages or []:
            if isinstance(page, dict):
                if page.get("name"):
                    allowed_workspaces.add(page["name"])
                if page.get("title"):
                    allowed_workspaces.add(page["title"])

    icons = bootinfo.get("desktop_icons")
    if isinstance(icons, list) and allowed_workspaces:
        bootinfo["desktop_icons"] = [
            icon
            for icon in icons
            if isinstance(icon, dict)
            and (
                icon.get("module_name") in allowed_workspaces
                or icon.get("label") in allowed_workspaces
            )
        ]


def _filter_shop_floor(bootinfo: dict[str, Any]) -> None:
    bootinfo["almdina_shop_floor_only"] = 1
    bootinfo["almdina_shop_floor_home"] = SHOP_FLOOR_PAGE
    bootinfo["almdina_allowed_pages"] = [SHOP_FLOOR_PAGE]
    bootinfo["default_route"] = f"/app/{SHOP_FLOOR_PAGE}"
    bootinfo["home_page"] = SHOP_FLOOR_PAGE

    workspaces = bootinfo.get("workspaces")
    if isinstance(workspaces, dict) and workspaces.get("pages"):
        pages = [
            page
            for page in workspaces["pages"]
            if (page.get("name") if isinstance(page, dict) else page)
            == SHOP_FLOOR_WORKSPACE
        ]
        if not pages:
            pages = [
                page
                for page in workspaces["pages"]
                if isinstance(page, dict)
                and str(page.get("title") or page.get("label") or "")
                in {SHOP_FLOOR_WORKSPACE, "صالة الإنتاج"}
            ]
        workspaces["pages"] = pages
        bootinfo["workspaces"] = workspaces
        bootinfo["allowed_workspaces"] = pages

    bootinfo["workspace_sidebar_item"] = {}
    bootinfo["sidebar_pages"] = []
    bootinfo["allowed_pages"] = [SHOP_FLOOR_PAGE]

    app_data = bootinfo.get("app_data")
    if isinstance(app_data, list):
        trimmed = []
        for app in app_data:
            if not isinstance(app, dict):
                continue
            name = app.get("app_name") or app.get("name")
            if name != "almdina_erp":
                continue
            app = dict(app)
            app["workspaces"] = [SHOP_FLOOR_WORKSPACE]
            app["app_route"] = f"/app/{SHOP_FLOOR_PAGE}"
            app["modules"] = list(ALLOWED_MODULES_FOR_SHOP_FLOOR)
            trimmed.append(app)
        bootinfo["app_data"] = trimmed

    bootinfo["desktop_icons"] = []

    module_map = bootinfo.get("module_wise_workspaces")
    if isinstance(module_map, dict):
        bootinfo["module_wise_workspaces"] = {
            key: [workspace for workspace in (value or []) if workspace == SHOP_FLOOR_WORKSPACE]
            for key, value in module_map.items()
            if key in ALLOWED_MODULES_FOR_SHOP_FLOOR
        }


def boot_session(bootinfo: dict[str, Any]) -> None:
    """Apply read-only navigation and presentation authorization policy."""

    roles = _roles()
    _attach_permission_context(bootinfo, roles)
    if is_order_entry_profile(roles):
        _filter_order_entry(bootinfo)
        return
    if is_shop_floor_only(roles):
        _filter_shop_floor(bootinfo)


def extend_bootinfo(bootinfo: dict[str, Any] | None = None) -> None:
    """Second read-only pass after Frappe assembles application metadata."""

    if not bootinfo:
        return

    roles = _roles()
    _attach_permission_context(bootinfo, roles)
    if bootinfo.get("almdina_order_entry_only") or is_order_entry_profile(roles):
        bootinfo["almdina_order_entry_only"] = 1
        bootinfo["almdina_allowed_apps"] = ["almdina_erp"]
        return

    if not bootinfo.get("almdina_shop_floor_only"):
        if not is_shop_floor_only(roles):
            return
        bootinfo["almdina_shop_floor_only"] = 1

    apps_data = bootinfo.get("apps_data")
    if isinstance(apps_data, dict):
        apps = apps_data.get("apps") or []
        apps_data["apps"] = [
            app
            for app in apps
            if (app.get("name") if isinstance(app, dict) else app) == "almdina_erp"
        ]
        apps_data["default_path"] = f"/app/{SHOP_FLOOR_PAGE}"
        bootinfo["apps_data"] = apps_data

    bootinfo["workspace_sidebar_item"] = {}
    bootinfo["desktop_icons"] = []
    bootinfo["home_page"] = SHOP_FLOOR_PAGE
    bootinfo["default_route"] = f"/app/{SHOP_FLOOR_PAGE}"
