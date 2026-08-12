from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.surface_access import (
    build_surface_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    capability_flags,
    normalize_capabilities,
)

PERMISSION_CONTEXT_VERSION = 6


def build_permission_context(
    roles: Iterable[str] | None,
    granted_capabilities: Iterable[str] | None,
    *,
    system_administrator: bool = False,
) -> dict[str, Any]:
    """Build the stable permission, navigation and UI-surface context.

    ``roles`` remains in the signature for backward compatibility with older
    adapters, but it is intentionally ignored. Navigation, surface visibility
    and actions are derived from administrator-managed capability grants. The
    built-in Frappe Administrator is identified separately so it can retain the
    complete Desktop while ordinary System Manager users remain capability-bound.
    """

    del roles
    normalized_capabilities = normalize_capabilities(granted_capabilities)
    navigation = build_navigation_context(
        normalized_capabilities,
        system_administrator=system_administrator,
    )
    surfaces = build_surface_access(
        normalized_capabilities,
        system_administrator=system_administrator,
    )
    return {
        "version": PERMISSION_CONTEXT_VERSION,
        "profile": navigation["profile"],
        "capabilities": capability_flags(normalized_capabilities),
        "navigation": navigation,
        "surfaces": surfaces,
    }


__all__ = ["PERMISSION_CONTEXT_VERSION", "build_permission_context"]
