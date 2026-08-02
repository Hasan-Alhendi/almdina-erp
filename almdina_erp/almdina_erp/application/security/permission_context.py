from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    capability_flags,
    normalize_capabilities,
)

PERMISSION_CONTEXT_VERSION = 3


def build_permission_context(
    roles: Iterable[str] | None,
    granted_capabilities: Iterable[str] | None,
) -> dict[str, Any]:
    """Build the stable permission and shared-shell navigation context.

    ``roles`` remains in the signature for backward compatibility with older
    adapters, but it is intentionally ignored. Navigation, page presentation
    and actions are derived exclusively from administrator-managed capability
    grants.
    """

    del roles
    normalized_capabilities = normalize_capabilities(granted_capabilities)
    navigation = build_navigation_context(normalized_capabilities)
    return {
        "version": PERMISSION_CONTEXT_VERSION,
        "profile": navigation["profile"],
        "capabilities": capability_flags(normalized_capabilities),
        "navigation": navigation,
    }


__all__ = ["PERMISSION_CONTEXT_VERSION", "build_permission_context"]
