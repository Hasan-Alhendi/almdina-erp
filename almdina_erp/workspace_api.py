from __future__ import annotations

from typing import Any

import frappe
from frappe.desk.desktop import get_desktop_page as frappe_get_desktop_page

from almdina_erp.almdina_erp.application.security.permission_context import (
    build_permission_context,
)
from almdina_erp.almdina_erp.application.security.workspace_visibility import (
    filter_desktop_page_payload,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)


SYSTEM_ADMINISTRATOR = "Administrator"
ALMDINA_WORKSPACES = frozenset(
    {
        "Almdina ERP",
        "Shop Floor",
        "Almdina Control Center",
        "Almdina Reports",
        "Almdina Settings",
        "Almdina Go-Live",
    }
)


def _page_name(page: Any) -> str:
    parsed = frappe.parse_json(page)
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict):
        return str(parsed.get("name") or parsed.get("title") or parsed.get("label") or "")
    return ""


def _surface_flags(user: str) -> dict[str, bool]:
    context = build_permission_context(
        (),
        granted_capabilities(user=user),
        system_administrator=user == SYSTEM_ADMINISTRATOR,
    )
    return {
        str(key): value is True
        for key, value in dict(context.get("surfaces") or {}).items()
    }


@frappe.whitelist()
@frappe.read_only()
def get_desktop_page(page: str | dict[str, Any]) -> dict[str, Any]:
    """Return Frappe Workspace data narrowed by Almdina business surfaces.

    Frappe's native ``is_item_allowed`` checks DocType/Page/Report permissions,
    which are intentionally not the source of Almdina business authority. The
    standard builder still runs first; this adapter can only narrow its result.
    """

    payload = frappe_get_desktop_page(page)
    user = frappe.session.user
    if user == SYSTEM_ADMINISTRATOR or _page_name(page) not in ALMDINA_WORKSPACES:
        return payload
    return filter_desktop_page_payload(payload, _surface_flags(user))


__all__ = ["get_desktop_page"]
