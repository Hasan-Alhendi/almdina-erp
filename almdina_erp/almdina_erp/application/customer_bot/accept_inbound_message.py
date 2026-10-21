"""Accept one trusted inbound event and commit at most one engine turn.

The caller is an internal adapter that already authenticated the provider
connection. This module does not expose an HTTP route, does not read a phone
from ``sender_id``, and does not send a reply.

Crash window: ``complete_turn`` commits the new session state and marks the
event complete in one short transaction, before this function returns the
messages. The acceptance epoch is checked inside that transaction. If the
process dies after that commit and before the caller receives the result, a
later call with the same event returns ``duplicate`` and no messages. The
outputs are not stored, so they cannot be sent again from this layer. That is
at-most-once handoff to transport, not exactly-once delivery.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotMessage,
    ConversationContext,
)
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import InboundCustomerMessage
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    CONFLICT,
    DEFAULT_LEASE_TTL,
    DEFAULT_SESSION_TTL,
    DUPLICATE,
    FAILED,
    IGNORED,
    PROCEED,
    IN_PROGRESS,
    LOST_LEASE,
    NOT_ACCEPTING,
    PROCESSED,
    SUPPRESSED,
    disposition_is_sendable,
    disposition_retries_later,
    event_fingerprint,
    is_operational_message,
    keys_fit,
)

from .conversation_ports import CustomerBotServicePort
from .handle_conversation import handle_customer_conversation
from .order_followup_ports import (
    CustomerOrderHeaderReader,
    ProductionRouteCatalog,
    ProductionStageReader,
)
from .phone_access_ports import CustomerPhoneDirectory
from .read_runtime import read_customer_bot_runtime
from .session_store import CustomerBotSessionStore
from .settings_commands import CustomerBotSettingsStore


class InboundAcceptance:
    """One internal outcome. ``sendable`` is true only for a newly committed turn."""

    __slots__ = ("disposition", "documents", "messages", "published", "retry_later", "sendable")

    def __init__(
        self,
        disposition: str,
        *,
        messages: tuple[BotMessage, ...] = (),
        documents: tuple[CustomerBotDocument, ...] = (),
        published: dict[str, str] | None = None,
    ) -> None:
        self.disposition = disposition
        self.sendable = disposition_is_sendable(disposition)
        self.retry_later = disposition_retries_later(disposition)
        self.messages = messages
        self.documents = documents
        self.published = published

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InboundAcceptance):
            return NotImplemented
        return (
            self.disposition == other.disposition
            and self.messages == other.messages
            and self.documents == other.documents
            and self.published == other.published
        )


def accept_inbound_customer_message(
    message: InboundCustomerMessage,
    *,
    sessions: CustomerBotSessionStore,
    settings: CustomerBotSettingsStore,
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    services: CustomerBotServicePort,
    now: datetime | None = None,
    session_ttl: timedelta = DEFAULT_SESSION_TTL,
    lease_ttl: timedelta = DEFAULT_LEASE_TTL,
) -> InboundAcceptance:
    """Run the current engine once, or refuse without calling it."""

    if now is None:
        now = datetime.now(timezone.utc)
    if not keys_fit(message):
        raise ValueError("inbound identifiers exceed the session key length")
    fingerprint = event_fingerprint(message)
    if not is_operational_message(message):
        return _quiet(sessions.note_terminal(
            connection_ref=message.connection_ref,
            provider_event_id=message.provider_event_id,
            fingerprint=fingerprint,
            outcome=IGNORED,
            now=now,
        ))
    runtime = read_customer_bot_runtime(settings)
    if not runtime.accepting_messages:
        return _quiet(sessions.note_terminal(
            connection_ref=message.connection_ref,
            provider_event_id=message.provider_event_id,
            fingerprint=fingerprint,
            outcome=NOT_ACCEPTING,
            now=now,
        ))
    acceptance_epoch = runtime.acceptance_epoch
    begun = sessions.begin_turn(
        connection_ref=message.connection_ref,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        provider_event_id=message.provider_event_id,
        fingerprint=fingerprint,
        now=now,
        lease_ttl=lease_ttl,
    )
    if begun.disposition != PROCEED:
        return _quiet(begun.disposition)
    identity = (
        message.connection_ref,
        message.conversation_id,
        message.sender_id,
        message.provider_event_id,
    )
    try:
        turn = handle_customer_conversation(
            message,
            begun.state,
            ConversationContext(enabled=True, now=now, session_ttl=session_ttl),
            directory,
            headers,
            stages,
            routes,
            services,
        )
    except Exception:
        released = sessions.abort_turn(
            connection_ref=identity[0],
            conversation_id=identity[1],
            sender_id=identity[2],
            provider_event_id=identity[3],
            conversation_token=begun.conversation_token or "",
            event_token=begun.event_token or "",
            revision=begun.revision or 0,
        )
        return _quiet(FAILED if released else LOST_LEASE)
    published: dict[str, str] = {}

    def acceptance_unchanged() -> bool:
        current = settings.published_if_same_acceptance(acceptance_epoch)
        if current is None:
            return False
        published.clear()
        published.update(current)
        return True

    outcome = sessions.complete_turn(
        connection_ref=identity[0],
        conversation_id=identity[1],
        sender_id=identity[2],
        provider_event_id=identity[3],
        fingerprint=fingerprint,
        conversation_token=begun.conversation_token or "",
        event_token=begun.event_token or "",
        revision=begun.revision or 0,
        state=turn.state,
        now=now,
        acceptance_unchanged=acceptance_unchanged,
    )
    if outcome != PROCESSED:
        return _quiet(outcome)
    return InboundAcceptance(
        PROCESSED,
        messages=turn.messages,
        documents=turn.documents,
        published=dict(published),
    )


def _quiet(disposition: str) -> InboundAcceptance:
    if disposition == PROCESSED:
        disposition = DUPLICATE
    if disposition in {IN_PROGRESS, CONFLICT, DUPLICATE, IGNORED, NOT_ACCEPTING, SUPPRESSED, LOST_LEASE, FAILED}:
        return InboundAcceptance(disposition)
    return InboundAcceptance(disposition)


__all__ = ["InboundAcceptance", "accept_inbound_customer_message"]
