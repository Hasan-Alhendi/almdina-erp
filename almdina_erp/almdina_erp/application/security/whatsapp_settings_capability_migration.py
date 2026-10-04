from __future__ import annotations

from collections.abc import Mapping

from almdina_erp.almdina_erp.domain.security.authorization import Capability


def needs_whatsapp_session_grant(state: Mapping[str, bool]) -> bool:
    """Preserve session management for roles that already viewed factory settings."""

    if state.get(Capability.MANAGE_WHATSAPP_SESSION) is True:
        return False
    return state.get(Capability.VIEW_FACTORY_SETTINGS) is True


def needs_whatsapp_message_grant(state: Mapping[str, bool]) -> bool:
    """Preserve message editing for roles that already edited print identity."""

    if state.get(Capability.EDIT_WHATSAPP_MESSAGES) is True:
        return False
    return state.get(Capability.EDIT_FACTORY_PRINT_IDENTITY) is True


def whatsapp_settings_capability_updates(
    states: Mapping[str, Mapping[str, bool]],
) -> dict[str, dict[str, bool]]:
    """Split WhatsApp authority off the previous factory-settings grants.

    Applying the returned states and invoking this function again yields no
    further updates, which is the idempotency contract.
    """

    updates: dict[str, dict[str, bool]] = {}
    for role, state in states.items():
        session_needed = needs_whatsapp_session_grant(state)
        messages_needed = needs_whatsapp_message_grant(state)
        if not session_needed and not messages_needed:
            continue
        updated = dict(state)
        if session_needed:
            updated[Capability.MANAGE_WHATSAPP_SESSION] = True
        if messages_needed:
            updated[Capability.EDIT_WHATSAPP_MESSAGES] = True
        updates[str(role)] = updated
    return updates


__all__ = [
    "needs_whatsapp_message_grant",
    "needs_whatsapp_session_grant",
    "whatsapp_settings_capability_updates",
]
