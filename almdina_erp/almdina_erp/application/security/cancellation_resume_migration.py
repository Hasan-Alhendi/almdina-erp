from __future__ import annotations

from collections.abc import Mapping

from almdina_erp.almdina_erp.domain.security.authorization import Capability


def needs_resume_cancelled_grant(state: Mapping[str, bool]) -> bool:
    """Return whether a supervisor-like role needs the new resume grant."""

    if state.get(Capability.RESUME_CANCELLED_ORDER) is True:
        return False
    return state.get(Capability.RETURN_ORDER_TO_DRAFT) is True


def resume_cancelled_state_updates(
    states: Mapping[str, Mapping[str, bool]],
) -> dict[str, dict[str, bool]]:
    """Grant resume to roles that already authorize return-to-draft.

    Applying the returned states and invoking this function again yields no
    further updates, which is the idempotency contract.
    """

    updates: dict[str, dict[str, bool]] = {}
    for role, state in states.items():
        if not needs_resume_cancelled_grant(state):
            continue
        updated = dict(state)
        updated[Capability.RESUME_CANCELLED_ORDER] = True
        updates[str(role)] = updated
    return updates


__all__ = [
    "needs_resume_cancelled_grant",
    "resume_cancelled_state_updates",
]
