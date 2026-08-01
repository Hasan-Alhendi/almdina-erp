from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import (
    capability_flags,
    is_order_entry_profile,
    is_shop_floor_only,
    normalize_capabilities,
    normalize_roles,
)

PERMISSION_CONTEXT_VERSION = 2


def build_permission_context(
    roles: Iterable[str] | None,
    granted_capabilities: Iterable[str] | None,
) -> dict[str, Any]:
    """Build the stable permission context consumed by all Desk presenters.

    Role assignments are resolved by the Frappe infrastructure adapter before
    entering this framework-independent use case. The application layer only
    formats the resulting capability set and navigation profile.
    """

    normalized_roles = normalize_roles(roles)
    normalized_capabilities = normalize_capabilities(granted_capabilities)
    if is_order_entry_profile(normalized_roles):
        profile = "order_entry"
    elif is_shop_floor_only(normalized_roles):
        profile = "shop_floor"
    else:
        profile = "full"

    return {
        "version": PERMISSION_CONTEXT_VERSION,
        "profile": profile,
        "capabilities": capability_flags(normalized_capabilities),
    }


__all__ = ["PERMISSION_CONTEXT_VERSION", "build_permission_context"]
