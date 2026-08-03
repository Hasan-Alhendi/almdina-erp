from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.permission_context import (
    build_permission_context,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)


ALMDINA_APP = "almdina_erp"
ALMDINA_MODULE = "Almdina ERP"
SYSTEM_ADMINISTRATOR = "Administrator"


def _context() -> dict[str, Any]:
    user = frappe.session.user
    return build_permission_context(
        (),
        granted_capabilities(user=user),
        system_administrator=user == SYSTEM_ADMINISTRATOR,
    )


def _workspace_name(page: Any) -> str:
    if isinstance(page, str):
        return page
    if not isinstance(page, dict):
        return ""
    return str(page.get("name") or page.get("title") or page.get("label") or "")


def _filter_workspaces(bootinfo: dict[str, Any], allowed: set[str]) -> None:
    if not allowed:
        return

    workspaces = bootinfo.get("workspaces")
    if isinstance(workspaces, dict):
        pages = workspaces.get("pages")
        if isinstance(pages, list):
            pages = [page for page in pages if _workspace_name(page) in allowed]
            workspaces["pages"] = pages
            bootinfo["workspaces"] = workspaces
            bootinfo["allowed_workspaces"] = pages

    module_map = bootinfo.get("module_wise_workspaces")
    if isinstance(module_map, dict):
        filtered: dict[str, Any] = {}
        for module, values in module_map.items():
            if module != ALMDINA_MODULE:
                continue
            if isinstance(values, list):
                kept = [value for value in values if _workspace_name(value) in allowed]
                if kept:
                    filtered[module] = kept
            elif _workspace_name(values) in allowed:
                filtered[module] = values
        bootinfo["module_wise_workspaces"] = filtered

    icons = bootinfo.get("desktop_icons")
    if isinstance(icons, list):
        bootinfo["desktop_icons"] = [
            icon
            for icon in icons
            if isinstance(icon, dict)
            and str(icon.get("module_name") or icon.get("label") or "") in allowed
        ]


def _filter_apps(bootinfo: dict[str, Any]) -> None:
    app_data = bootinfo.get("app_data")
    if isinstance(app_data, list):
        bootinfo["app_data"] = [
            dict(app)
            for app in app_data
            if isinstance(app, dict)
            and (app.get("app_name") or app.get("name")) == ALMDINA_APP
        ]

    apps_data = bootinfo.get("apps_data")
    if isinstance(apps_data, dict):
        apps = apps_data.get("apps")
        if isinstance(apps, list):
            apps_data["apps"] = [
                app
                for app in apps
                if (
                    app.get("name") if isinstance(app, dict) else app
                )
                == ALMDINA_APP
            ]
        bootinfo["apps_data"] = apps_data


def _apply_shared_shell(bootinfo: dict[str, Any]) -> None:
    context = _context()
    navigation = context["navigation"]

    # Permission flags are safe to expose to every session. Navigation changes
    # are applied only when the user owns at least one Almdina capability.
    bootinfo["almdina_permissions"] = context
    bootinfo["almdina_navigation"] = navigation
    if not navigation.get("shared_shell"):
        return

    bootinfo["almdina_shared_shell"] = 1
    bootinfo["home_page"] = navigation["home_page"]
    bootinfo["default_route"] = navigation["default_route"]

    # Ordinary Almdina users stay inside the factory application. The built-in
    # Administrator deliberately keeps Frappe's complete app/workspace registry
    # so /desk can render the standard Desktop and every installed app remains usable.
    if navigation.get("app_only"):
        allowed = set(navigation.get("workspaces") or ())
        bootinfo["almdina_allowed_apps"] = [ALMDINA_APP]
        _filter_workspaces(bootinfo, allowed)
        _filter_apps(bootinfo)

        apps_data = bootinfo.get("apps_data")
        if isinstance(apps_data, dict):
            apps_data["default_path"] = navigation["default_route"]


def boot_session(bootinfo: dict[str, Any]) -> None:
    """Attach the read-only shared-shell authorization context."""

    _apply_shared_shell(bootinfo)


def extend_bootinfo(bootinfo: dict[str, Any] | None = None) -> None:
    """Repeat the idempotent filter after Frappe assembles application metadata."""

    if bootinfo:
        _apply_shared_shell(bootinfo)
