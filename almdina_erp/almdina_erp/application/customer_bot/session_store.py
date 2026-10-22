"""Persistence port for customer-bot sessions and inbound deduplication.

Adapters commit each method before returning. None of these methods may run
the conversation engine or a PDF renderer. The unique event key and the
conversation lease live in the adapter, not in process memory.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from almdina_erp.almdina_erp.domain.customer_bot.conversation import ConversationState
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import ReplyIntent


@dataclass(frozen=True, slots=True)
class BeginTurn:
    disposition: str
    revision: int | None = None
    state: ConversationState | None = None
    conversation_token: str | None = None
    event_token: str | None = None


class CustomerBotSessionStore(Protocol):
    def note_terminal(
        self,
        *,
        connection_ref: str,
        provider_event_id: str,
        fingerprint: str,
        outcome: str,
        now: datetime,
    ) -> str: ...

    def begin_turn(
        self,
        *,
        connection_ref: str,
        conversation_id: str,
        sender_id: str,
        provider_event_id: str,
        fingerprint: str,
        now: datetime,
        lease_ttl: timedelta,
    ) -> BeginTurn: ...

    def complete_turn(
        self,
        *,
        connection_ref: str,
        conversation_id: str,
        sender_id: str,
        provider_event_id: str,
        fingerprint: str,
        conversation_token: str,
        event_token: str,
        revision: int,
        state: ConversationState | None,
        now: datetime,
        acceptance_unchanged: Callable[[], bool],
        build_replies: Callable[[], tuple[ReplyIntent, ...]],
    ) -> str:
        """Commit the turn, or suppress it, while the lease token still matches.

        ``acceptance_unchanged`` and, when it passes, ``build_replies`` run
        inside the commit transaction. Reply rows are written with the new
        conversation state and the completed event. A false acceptance result
        completes the event as suppressed and stores neither state nor replies.
        """
        ...

    def abort_turn(
        self,
        *,
        connection_ref: str,
        conversation_id: str,
        sender_id: str,
        provider_event_id: str,
        conversation_token: str,
        event_token: str,
        revision: int,
    ) -> bool: ...

    def purge(
        self,
        *,
        now: datetime,
        conversation_retention: timedelta,
        event_retention: timedelta,
        limit: int,
    ) -> tuple[int, int]: ...


__all__ = ["BeginTurn", "CustomerBotSessionStore"]
