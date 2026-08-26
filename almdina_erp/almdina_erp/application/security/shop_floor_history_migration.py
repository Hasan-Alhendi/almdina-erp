from __future__ import annotations

from collections.abc import Mapping

from almdina_erp.almdina_erp.domain.security.authorization import (
    SHOP_FLOOR_ACCESS_CAPABILITIES,
    Capability,
)


def needs_legacy_history_grant(state: Mapping[str, bool]) -> bool:
    """Return whether a legacy Shop Floor role needs the new history grant."""

    if state.get(Capability.VIEW_SHOP_FLOOR_HISTORY) is True:
        return False
    return any(state.get(capability) is True for capability in SHOP_FLOOR_ACCESS_CAPABILITIES)


def legacy_history_state_updates(
    states: Mapping[str, Mapping[str, bool]],
) -> dict[str, dict[str, bool]]:
    """Build compatibility updates without mutating the supplied role states.

    The function is intentionally framework-free so migration policy remains
    deterministic and testable. Applying the returned states and invoking this
    function again yields no further updates, which is the idempotency contract.
    """

    updates: dict[str, dict[str, bool]] = {}
    for role, state in states.items():
        if not needs_legacy_history_grant(state):
            continue
        updated = dict(state)
        updated[Capability.VIEW_SHOP_FLOOR_HISTORY] = True
        updates[str(role)] = updated
    return updates


__all__ = [
    "legacy_history_state_updates",
    "needs_legacy_history_grant",
]
