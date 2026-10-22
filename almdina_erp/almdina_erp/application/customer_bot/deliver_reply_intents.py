"""Send claimed reply intents through injected reply ports.

Preflight runs after the claim commits and before any gateway call. A cancel
stores ``cancelled`` without sending. Provider acceptance is not customer
delivery. Abandoned claims become ``unknown`` through
``recover_abandoned_claims`` only. Preflight does not guarantee that data stay
unchanged after the network request begins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from almdina_erp.almdina_erp.domain.customer_bot.document_reply import DocumentReplyRequest
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    CANCELLED,
    DEFAULT_REPLY_CLAIM_TTL,
    PART_DOCUMENT,
    PART_TEXT,
    PROCESSING,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    TextReplyRequest,
    TextSendResult,
)

from .conversation_ports import CustomerBotServicePort, UnavailableCustomerBotServices
from .dispatch_document_reply import dispatch_document_reply
from .dispatch_text_reply import dispatch_text_reply
from .phone_access_ports import CustomerPhoneDirectory
from .ports import BotDocumentReplyPort, BotTextReplyPort
from .reply_outbox import ClaimedReply, CustomerBotReplyOutbox
from .settings_commands import CustomerBotSettingsStore
from .verify_reply_before_send import verify_reply_before_send


@dataclass(frozen=True, slots=True)
class ReplyDelivery:
    reply_id: str
    status: str


@dataclass(frozen=True, slots=True)
class ReplyDeliveryDeps:
    """Runtime checks and ports used between claim and gateway send."""

    settings: CustomerBotSettingsStore
    directory: CustomerPhoneDirectory
    services: CustomerBotServicePort = UnavailableCustomerBotServices()
    document_port: BotDocumentReplyPort | None = None


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
    deps: ReplyDeliveryDeps | None = None,
    now: datetime | None = None,
) -> ReplyDelivery | None:
    """Claim one pending reply, preflight, call the port, then store the result.

    The port runs after ``claim_next`` has committed. An exception from the
    port is not rewritten into ``unknown`` and does not return the row to
    ``pending``. A failure while storing the result leaves the row in
    ``processing`` until claim recovery marks it ``unknown``. When preflight
    cancels, the row becomes ``cancelled`` and the gateway is not called.
    """

    if now is None:
        now = datetime.now(timezone.utc)
    claimed = outbox.claim_next(now=now)
    if claimed is None:
        return None
    if deps is not None:
        preflight = verify_reply_before_send(
            claimed,
            settings=deps.settings,
            directory=deps.directory,
            services=deps.services,
        )
        if not preflight.should_send:
            try:
                saved = outbox.record_cancelled(
                    reply_id=claimed.reply_id,
                    claim_token=claimed.claim_token,
                    reason_code=preflight.reason_code,
                    now=now,
                )
            except Exception:
                return ReplyDelivery(claimed.reply_id, PROCESSING)
            if not saved:
                return ReplyDelivery(claimed.reply_id, PROCESSING)
            return ReplyDelivery(claimed.reply_id, CANCELLED)
        try:
            result = _dispatch(claimed, port, deps=deps, document=preflight.document)
        except Exception:
            return ReplyDelivery(claimed.reply_id, PROCESSING)
    else:
        # Legacy unit-test path: text parts only, no preflight wiring.
        if claimed.part_kind != PART_TEXT:
            return ReplyDelivery(claimed.reply_id, PROCESSING)
        try:
            result = dispatch_text_reply(port, _text_request(claimed))
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
    deps: ReplyDeliveryDeps | None = None,
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
        step = deliver_one_reply(outbox, port, deps=deps, now=now)
        if step is None:
            break
        delivered.append(step)
        if step.status == PROCESSING:
            break
    return tuple(delivered)


def _dispatch(claimed, port, *, deps: ReplyDeliveryDeps, document):
    if claimed.part_kind == PART_DOCUMENT:
        if document is None or deps.document_port is None:
            raise BotDocumentUnavailable()
        return dispatch_document_reply(
            deps.document_port,
            DocumentReplyRequest(
                reply_id=claimed.reply_id,
                connection_ref=claimed.connection_ref,
                destination_id=claimed.destination_id,
                filename=document.filename,
                mime_type=document.mime_type,
                content=document.content,
            ),
        )
    if claimed.part_kind != PART_TEXT:
        raise BotDocumentUnavailable()
    return dispatch_text_reply(port, _text_request(claimed))


def _text_request(claimed: ClaimedReply) -> TextReplyRequest:
    return TextReplyRequest(
        reply_id=claimed.reply_id,
        connection_ref=claimed.connection_ref,
        destination_id=claimed.destination_id,
        text=claimed.body,
    )


class BotDocumentUnavailable(RuntimeError):
    """Document bytes or document port missing after a send decision."""


__all__ = [
    "ReplyDelivery",
    "ReplyDeliveryDeps",
    "deliver_one_reply",
    "deliver_pending_replies",
    "recover_abandoned_reply_claims",
]
