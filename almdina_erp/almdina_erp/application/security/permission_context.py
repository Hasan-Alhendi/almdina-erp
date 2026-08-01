from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import (
    capability_flags_for_roles,
    is_order_entry_profile,
    is_shop_floor_only,
    normalize_roles,
)

PERMISSION_CONTEXT_VERSION = 1


def build_permission_context(roles: Iterable[str] | None) -> dict[str, Any]:
    """Build the stable user-level permission context consumed by presenters.

    The application layer exposes capabilities and a navigation profile without
    depending on Frappe, HTTP, Desk, or any concrete UI implementation. Runtime
    document rules such as order state and assignment are intentionally evaluated
    later by the relevant server-side action policy.
    """

    normalized_roles = normalize_roles(roles)
    if is_order_entry_profile(normalized_roles):
        profile = "order_entry"
    elif is_shop_floor_only(normalized_roles):
        profile = "shop_floor"
    else:
        profile = "full"

    return {
        "version": PERMISSION_CONTEXT_VERSION,
        "profile": profile,
        "capabilities": capability_flags_for_roles(normalized_roles),
    }


__all__ = ["PERMISSION_CONTEXT_VERSION", "build_permission_context"]
