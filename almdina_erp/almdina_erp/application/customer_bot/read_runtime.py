"""Read the current customer-bot switch and published texts.

A later inbound layer calls this on every message. It does not reuse a value
stored inside a conversation. This module does not receive messages or send
them.
"""

from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.customer_bot.message_templates import validate_texts

from .settings_commands import CustomerBotSettingsStore


@dataclass(frozen=True, slots=True)
class CustomerBotRuntime:
    enabled: bool
    accepting_messages: bool
    revision: int
    acceptance_epoch: int
    published: dict[str, str] | None


def next_acceptance_epoch(currently_enabled: bool, acceptance_epoch: int, enabled: bool) -> int:
    """Advance the cycle only when the switch leaves the on position.

    A later return to on keeps the new epoch. A turn that started on the old
    epoch can see that the switch passed through off, even if it is on again.
    """

    if currently_enabled and not enabled:
        return acceptance_epoch + 1
    return acceptance_epoch


def read_customer_bot_runtime(store: CustomerBotSettingsStore) -> CustomerBotRuntime:
    snapshot = store.load()
    published_ok = not validate_texts(snapshot.published)
    return CustomerBotRuntime(
        enabled=snapshot.enabled,
        accepting_messages=bool(snapshot.enabled and published_ok),
        revision=snapshot.revision,
        acceptance_epoch=snapshot.acceptance_epoch,
        published=dict(snapshot.published) if published_ok else None,
    )


__all__ = ["CustomerBotRuntime", "next_acceptance_epoch", "read_customer_bot_runtime"]
