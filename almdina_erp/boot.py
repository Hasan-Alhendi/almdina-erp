from __future__ import annotations

from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.permission_context import (
    build_permission_context,
)
from almdina_erp.almdina_erp.application.presentation.shortcut_icon_catalog import (
    apply_sidebar_icon_catalog,
)
from almdina_erp.almdina_erp.infrastructure.frappe.ui_language_catalog import (
    almdina_ui_languages,
)
from almdina_erp.almdina_erp.application.security.workspace_visibility import (
    project_workspace_page,
    workspace_item_allowed,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)


ALMDINA_APP = "almdina_erp"
ALMDINA_MODULE = "Almdina ERP"
ALMDINA_WORKSPACE_ROUTE = "/desk/almdina-erp"
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


def _workspace_page_allowed(
    page: Any,
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> bool:
    """Authorize a v16 workspace/sidebar record.

    Link/URL rows are business destinations, not Workspaces. They must be checked
    against their exact Almdina surface *before* the Workspace allow-list so a
    translated sidebar link cannot inherit visibility from an allowed parent.
    """

    if isinstance(page, str):
        return page in allowed
    if not isinstance(page, dict):
        return False

    parent = str(page.get("parent_page") or "")
    page_type = str(page.get("type") or "Workspace").strip().lower()

    if page_type in {"link", "url"}:
        decision = workspace_item_allowed(page, surfaces)
        if decision is not None:
            return decision
        # Unknown child links inside the Almdina shell fail closed. New
        # destinations must be classified in workspace_visibility explicitly.
        if parent in allowed or parent == ALMDINA_MODULE:
            return False
        return False

    return _workspace_name(page) in allowed


def _project_allowed_pages(
    pages: Any,
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> Any:
    if not isinstance(pages, list):
        return pages
    return [
        project_workspace_page(page, surfaces)
        for page in pages
        if _workspace_page_allowed(page, allowed=allowed, surfaces=surfaces)
    ]


def _filter_workspace_container(
    bootinfo: dict[str, Any],
    key: str,
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> None:
    """Filter one Frappe workspace registry while preserving its metadata.

    Frappe v16 uses ``sidebar_pages`` for the persistent Desk rail. Older builds
    and some boot paths still expose ``workspaces``. Both must be projected or a
    denied entry can remain visible even though the other registry was filtered.
    """

    container = bootinfo.get(key)
    if not isinstance(container, dict):
        return
    pages = container.get("pages")
    if isinstance(pages, list):
        projected = _project_allowed_pages(pages, allowed=allowed, surfaces=surfaces)
        container["pages"] = projected
        bootinfo[key] = container
        if key == "workspaces":
            bootinfo["allowed_workspaces"] = projected


def _sidebar_item_allowed(
    item: Any,
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> bool:
    """Authorize one Frappe 16.60 ``module_sidebars`` row."""

    if not isinstance(item, dict):
        return False
    item_type = str(item.get("type") or "").strip()
    if item_type in {"Section Break", "Spacer"}:
        return True

    link_type = str(item.get("link_type") or "").strip()
    link_to = str(item.get("link_to") or "").strip()
    if link_type == "Workspace" or item_type == "Workspace":
        return link_to in allowed or _workspace_name(item) in allowed

    decision = workspace_item_allowed(item, surfaces)
    if decision is not None:
        return decision
    # Unknown Almdina destinations fail closed; non-Almdina shells are dropped
    # before item filtering, so remaining unknowns stay hidden.
    return False


def _project_module_sidebar(
    sidebar: Any,
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> dict[str, Any] | None:
    if not isinstance(sidebar, dict):
        return None
    projected = dict(sidebar)
    items = projected.get("items")
    if isinstance(items, list):
        projected["items"] = [
            item
            for item in items
            if _sidebar_item_allowed(item, allowed=allowed, surfaces=surfaces)
        ]
    return projected


def _filter_module_sidebars(
    bootinfo: dict[str, Any],
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> None:
    """Project Frappe 16.60 ``module_sidebars`` / dock shells for app-only users.

    Frappe replaced ``workspace_sidebar_item`` / ``module_wise_workspaces`` with
    ``module_sidebars`` keyed by shell identity and ``app_data[].dock``. Filtering
    only the legacy keys leaves foreign ERPNext/Frappe shells in the rail and can
    leave ``home_shell`` pointing at Build/Accounts for factory users.
    """

    container = bootinfo.get("module_sidebars")
    if not isinstance(container, dict):
        return

    filtered: dict[str, Any] = {}
    for shell, sidebar in container.items():
        if not isinstance(sidebar, dict):
            continue
        if str(sidebar.get("app") or "") != ALMDINA_APP:
            continue
        projected = _project_module_sidebar(
            sidebar,
            allowed=allowed,
            surfaces=surfaces,
        )
        if projected is not None:
            filtered[str(shell)] = projected
    bootinfo["module_sidebars"] = filtered

    dock = bootinfo.get("dock")
    if isinstance(dock, dict):
        bootinfo["dock"] = {
            app: rows
            for app, rows in dock.items()
            if app == ALMDINA_APP and isinstance(rows, list)
        }

    kept_shells = set(filtered)
    entity_module = bootinfo.get("entity_module")
    if isinstance(entity_module, dict):
        bootinfo["entity_module"] = {
            entity: shell
            for entity, shell in entity_module.items()
            if shell in kept_shells
        }

    canonical = bootinfo.get("canonical_shell")
    if isinstance(canonical, dict):
        bootinfo["canonical_shell"] = {
            kind: {
                name: shell
                for name, shell in mapping.items()
                if shell in kept_shells
            }
            for kind, mapping in canonical.items()
            if isinstance(mapping, dict)
        }

    if ALMDINA_MODULE in kept_shells:
        bootinfo["home_shell"] = ALMDINA_MODULE
    elif kept_shells:
        bootinfo["home_shell"] = next(iter(kept_shells))


def _filter_workspaces(
    bootinfo: dict[str, Any],
    allowed: set[str],
    surfaces: dict[str, bool],
) -> None:
    if not allowed:
        return

    # v16.60 module sidebars + dock shells (authoritative desk rail).
    _filter_module_sidebars(bootinfo, allowed=allowed, surfaces=surfaces)

    # Legacy/compatibility workspace registries still present on some paths.
    _filter_workspace_container(
        bootinfo,
        "sidebar_pages",
        allowed=allowed,
        surfaces=surfaces,
    )
    _filter_workspace_container(
        bootinfo,
        "workspaces",
        allowed=allowed,
        surfaces=surfaces,
    )

    module_map = bootinfo.get("module_wise_workspaces")
    if isinstance(module_map, dict):
        filtered: dict[str, Any] = {}
        for module, values in module_map.items():
            if module != ALMDINA_MODULE:
                continue
            if isinstance(values, list):
                kept = _project_allowed_pages(values, allowed=allowed, surfaces=surfaces)
                if kept:
                    filtered[module] = kept
            elif _workspace_page_allowed(values, allowed=allowed, surfaces=surfaces):
                filtered[module] = project_workspace_page(values, surfaces)
        bootinfo["module_wise_workspaces"] = filtered

    icons = bootinfo.get("desktop_icons")
    if isinstance(icons, list):
        bootinfo["desktop_icons"] = [
            icon
            for icon in icons
            if isinstance(icon, dict)
            and str(icon.get("module_name") or icon.get("label") or "") in allowed
        ]


def _filter_app_workspaces(
    app: dict[str, Any],
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> dict[str, Any]:
    projected = dict(app)
    workspaces = projected.get("workspaces")
    if isinstance(workspaces, list):
        projected["workspaces"] = _project_allowed_pages(
            workspaces,
            allowed=allowed,
            surfaces=surfaces,
        )
    return projected


def _filter_apps(
    bootinfo: dict[str, Any],
    *,
    allowed: set[str],
    surfaces: dict[str, bool],
) -> None:
    app_data = bootinfo.get("app_data")
    if isinstance(app_data, list):
        bootinfo["app_data"] = [
            _filter_app_workspaces(dict(app), allowed=allowed, surfaces=surfaces)
            for app in app_data
            if isinstance(app, dict)
            and (app.get("app_name") or app.get("name")) == ALMDINA_APP
        ]

    apps_data = bootinfo.get("apps_data")
    if isinstance(apps_data, dict):
        apps = apps_data.get("apps")
        if isinstance(apps, list):
            projected_apps: list[Any] = []
            for app in apps:
                name = app.get("name") if isinstance(app, dict) else app
                if name != ALMDINA_APP:
                    continue
                if isinstance(app, dict):
                    projected_apps.append(
                        _filter_app_workspaces(app, allowed=allowed, surfaces=surfaces)
                    )
                else:
                    projected_apps.append(app)
            apps_data["apps"] = projected_apps
        bootinfo["apps_data"] = apps_data


def _set_almdina_app_route(bootinfo: dict[str, Any], route: str) -> None:
    app_data = bootinfo.get("app_data")
    if not isinstance(app_data, list):
        return

    for app in app_data:
        if not isinstance(app, dict):
            continue
        if (app.get("app_name") or app.get("name")) == ALMDINA_APP:
            app["app_route"] = route


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

    # Ordinary Almdina users stay inside the factory application. The built-in
    # Administrator deliberately keeps Frappe's complete app/workspace registry
    # so /desk can render the standard Desktop and every installed app remains usable.
    if navigation.get("app_only"):
        allowed = set(navigation.get("workspaces") or ())
        surfaces = {
            str(key): value is True
            for key, value in dict(context.get("surfaces") or {}).items()
        }
        bootinfo["almdina_allowed_apps"] = [ALMDINA_APP]
        _filter_workspaces(bootinfo, allowed, surfaces)
        _filter_apps(bootinfo, allowed=allowed, surfaces=surfaces)
    else:
        # /desk is the Administrator's Desktop. The Almdina app card itself must
        # still enter the factory workspace instead of returning to Desktop.
        _set_almdina_app_route(bootinfo, ALMDINA_WORKSPACE_ROUTE)


def _apply_ui_languages(bootinfo: dict[str, Any]) -> None:
    """Expose the Desk language-switcher catalog without closing the workforce set."""

    bootinfo["almdina_ui_languages"] = almdina_ui_languages()


def boot_session(bootinfo: dict[str, Any]) -> None:
    """Attach the read-only shared-shell authorization context."""

    _apply_shared_shell(bootinfo)
    apply_sidebar_icon_catalog(bootinfo)
    _apply_ui_languages(bootinfo)


def extend_bootinfo(bootinfo: dict[str, Any] | None = None) -> None:
    """Repeat the idempotent filter after Frappe assembles application metadata."""

    if bootinfo:
        _apply_shared_shell(bootinfo)
        apply_sidebar_icon_catalog(bootinfo)
        _apply_ui_languages(bootinfo)
