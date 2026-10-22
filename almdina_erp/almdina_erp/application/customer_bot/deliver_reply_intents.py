"""Send claimed reply intents through the existing text-reply port.

This does not decide that a provider acceptance reached the customer, and it
does not send a reply again after ``unknown`` or after a crash that left the
row in ``processing``. OpenWA is not assumed to deduplicate sends. Abandoned
claims become ``unknown`` through ``recover_abandoned_claims`` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    DEFAULT_REPLY_CLAIM_TTL,
    PROCESSING,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    TextReplyRequest,
    TextSendResult,
)

from .dispatch_text_reply import dispatch_text_reply
from .ports import BotTextReplyPort
from .reply_outbox import ClaimedReply, CustomerBotReplyOutbox


@dataclass(frozen=True, slots=True)
class ReplyDelivery:
    reply_id: str
    status: str


def recover_abandoned_reply_claims(
    outbox: CustomerBotReplyOutbox,
    *,
    now: datetime | None = None,
    claim_ttl: timedelta = DEFAULT_REPLY_CLAIM_TTL,
    limit: int = 50,
) -> int:
    """Mark expired processing claims as unknown. No gateway call runs here."""

    if now is None:
        now = datetime.now(timezone.utc)
    return outbox.recover_abandoned_claims(now=now, claim_ttl=claim_ttl, limit=limit)


def deliver_one_reply(
    outbox: CustomerBotReplyOutbox,
    port: BotTextReplyPort,
    *,
    now: datetime | None = None,
) -> ReplyDelivery | None:
    """Claim one pending reply, call the port, then store the result.

    The port runs after ``claim_next`` has committed. An exception from the
    port is not rewritten into ``unknown`` and does not return the row to
    ``pending``. A failure while storing the result leaves the row in
    ``processing`` until claim recovery marks it ``unknown``.
    """

    if now is None:
        now = datetime.now(timezone.utc)
    claimed = outbox.claim_next(now=now)
    if claimed is None:
        return None
    try:
        result = dispatch_text_reply(port, _request(claimed))
    except Exception:
        return ReplyDelivery(claimed.reply_id, PROCESSING)
    if not isinstance(result, TextSendResult):
        return ReplyDelivery(claimed.reply_id, PROCESSING)
    try:
        saved = outbox.record_result(
            reply_id=claimed.reply_id,
            claim_token=claimed.claim_token,
            result=result,
            now=now,
        )
    except Exception:
        return ReplyDelivery(claimed.reply_id, PROCESSING)
    if not saved:
        return ReplyDelivery(claimed.reply_id, PROCESSING)
    return ReplyDelivery(claimed.reply_id, result.disposition.value)


def deliver_pending_replies(
    outbox: CustomerBotReplyOutbox,
    port: BotTextReplyPort,
    *,
    limit: int = 20,
    now: datetime | None = None,
    claim_ttl: timedelta = DEFAULT_REPLY_CLAIM_TTL,
) -> tuple[ReplyDelivery, ...]:
    """Recover abandoned claims, then send pending replies that remain eligible.

    This scan is the durable recovery path. A queue job is not required for
    the row to be found again. ``unknown`` and still-live ``processing`` rows
    are not sent again.
    """

    if now is None:
        now = datetime.now(timezone.utc)
    recover_abandoned_reply_claims(outbox, now=now, claim_ttl=claim_ttl, limit=limit)
    bounded = max(1, min(int(limit), 100))
    delivered: list[ReplyDelivery] = []
    for _ in range(bounded):
        step = deliver_one_reply(outbox, port, now=now)
        if step is None:
            break
        delivered.append(step)
        if step.status == PROCESSING:
            break
    return tuple(delivered)


def _request(claimed: ClaimedReply) -> TextReplyRequest:
    return TextReplyRequest(
        reply_id=claimed.reply_id,
        connection_ref=claimed.connection_ref,
        destination_id=claimed.destination_id,
        text=claimed.body,
    )


__all__ = [
    "ReplyDelivery",
    "deliver_one_reply",
    "deliver_pending_replies",
    "recover_abandoned_reply_claims",
]
