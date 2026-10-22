"""Port for the reply outbox.

Claim and record each commit on their own. The gateway call sits between
them and must not run inside the inbound-event transaction. Abandoned
processing claims become ``unknown`` without another send.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import DEFAULT_REPLY_CLAIM_TTL
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import TextSendResult


@dataclass(frozen=True, slots=True)
class ClaimedReply:
    reply_id: str
    claim_token: str
    connection_ref: str
    provider_event_id: str
    conversation_id: str
    destination_id: str
    sequence: int
    body: str
    attempt_count: int


class CustomerBotReplyOutbox(Protocol):
    def claim_next(self, *, now: datetime) -> ClaimedReply | None:
        """Move one pending reply to processing, or return none.

        The claim commits before this returns. A second worker cannot claim
        the same row. A later sequence stays unclaimed until every earlier
        sequence of that event is ``accepted``.
        """
        ...

    def record_result(
        self,
        *,
        reply_id: str,
        claim_token: str,
        result: TextSendResult,
        now: datetime,
    ) -> bool:
        """Store the gateway result only for the worker that holds the claim."""
        ...

    def recover_abandoned_claims(
        self,
        *,
        now: datetime,
        claim_ttl: timedelta = DEFAULT_REPLY_CLAIM_TTL,
        limit: int = 50,
    ) -> int:
        """Turn expired ``processing`` rows into ``unknown`` without resending.

        The update is conditioned on the stored claim token and status so a
        late worker cannot overwrite a newer outcome. Active claims younger
        than ``claim_ttl`` are left alone.
        """
        ...
