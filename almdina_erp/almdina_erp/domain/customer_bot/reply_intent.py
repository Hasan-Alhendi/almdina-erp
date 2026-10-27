"""One ordered reply part owed for a committed inbound event.

A part is text or a durable document descriptor. Provider acceptance is a
later status on that row and is not customer delivery. Nothing here stores a
gateway secret, a PDF, or a public URL.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from .checks import required_token
from .document_reply_spec import DocumentReplySpec
from .session_admission import utc_iso

PENDING = "pending"
PROCESSING = "processing"
ACCEPTED = "accepted"
REJECTED = "rejected"
UNKNOWN = "unknown"
CANCELLED = "cancelled"

PART_TEXT = "text"
PART_DOCUMENT = "document"

REPLY_STATUSES = frozenset({PENDING, PROCESSING, ACCEPTED, REJECTED, UNKNOWN, CANCELLED})
TERMINAL_REPLY_STATUSES = frozenset({ACCEPTED, REJECTED, UNKNOWN, CANCELLED})
PART_KINDS = frozenset({PART_TEXT, PART_DOCUMENT})
MAX_REPLIES_PER_EVENT = 20
# Bound above OpenWAClient's default HTTP timeout (45s). A live claim is not
# cut short by a shorter arbitrary delay. After this lease an abandoned claim
# becomes unknown without another send.
DEFAULT_REPLY_CLAIM_TTL = timedelta(minutes=2)
ABANDONED_CLAIM_REASON = "claim_abandoned"
CAPTION_TOO_LONG = "caption_too_long"


@dataclass(frozen=True, slots=True)
class ReplyIntent:
    connection_ref: str
    provider_event_id: str
    conversation_id: str
    destination_id: str
    sequence: int
    body: str
    part_kind: str = PART_TEXT
    document_spec: DocumentReplySpec | None = None
    customer_id: str | None = None
    normalized_phone: str | None = None
    acceptance_epoch: int | None = None
    message_key: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "connection_ref", required_token(self.connection_ref, "connection_ref"))
        object.__setattr__(
            self,
            "provider_event_id",
            required_token(self.provider_event_id, "provider_event_id"),
        )
        object.__setattr__(
            self,
            "conversation_id",
            required_token(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self,
            "destination_id",
            required_token(self.destination_id, "destination_id"),
        )
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if self.part_kind not in PART_KINDS:
            raise ValueError("part_kind must be text or document")
        if self.part_kind is PART_TEXT or self.part_kind == PART_TEXT:
            if not isinstance(self.body, str) or not self.body.strip():
                raise ValueError("body is required for a text reply")
            if self.document_spec is not None:
                raise ValueError("a text reply cannot carry a document spec")
            object.__setattr__(self, "body", self.body.strip())
        else:
            if self.document_spec is None:
                raise ValueError("a document reply needs a document spec")
            if not isinstance(self.body, str) or not self.body.strip():
                object.__setattr__(self, "body", self.document_spec.filename)
            else:
                object.__setattr__(self, "body", self.body.strip())
        if self.acceptance_epoch is not None and (
            type(self.acceptance_epoch) is not int or self.acceptance_epoch < 0
        ):
            raise ValueError("acceptance_epoch must be a non-negative integer")
        if self.customer_id is not None:
            object.__setattr__(self, "customer_id", required_token(self.customer_id, "customer_id"))
        if self.normalized_phone is not None:
            object.__setattr__(
                self, "normalized_phone", required_token(self.normalized_phone, "normalized_phone")
            )
        if self.message_key is not None:
            object.__setattr__(self, "message_key", required_token(self.message_key, "message_key"))
        if self.reason_code is not None:
            object.__setattr__(self, "reason_code", required_token(self.reason_code, "reason_code"))

    def reply_id(self) -> str:
        return stable_reply_id(self.connection_ref, self.provider_event_id, self.sequence)


def stable_reply_id(connection_ref: str, provider_event_id: str, sequence: int) -> str:
    """Stable id for one ordered reply of one event on one connection."""

    material = f"{connection_ref}\n{provider_event_id}\n{sequence}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"cbot-reply-{digest}"


def ordered_reply_intents(intents: tuple[ReplyIntent, ...]) -> tuple[ReplyIntent, ...]:
    """Require sequence 0..n-1 for a single event. Extra replies are refused."""

    if len(intents) > MAX_REPLIES_PER_EVENT:
        raise ValueError("too many reply intents for one event")
    if not intents:
        return ()
    head = intents[0]
    sequences = [item.sequence for item in intents]
    if sequences != list(range(len(intents))):
        raise ValueError("reply intents must be ordered from zero without gaps")
    for item in intents:
        if item.connection_ref != head.connection_ref or item.provider_event_id != head.provider_event_id:
            raise ValueError("reply intents for one commit must share the event")
        if item.conversation_id != head.conversation_id:
            raise ValueError("reply intents for one commit must share the conversation")
    return intents


def blocks_later_reply(status: str) -> bool:
    """A later sequence may send only after every earlier one is accepted.

    ``pending`` and ``processing`` wait. ``rejected``, ``unknown``, and
    ``cancelled`` keep later rows stored and unsent. Text acceptance never
    implies the rest of the reply group was delivered.
    """

    return status != ACCEPTED


def claim_is_abandoned(claimed_on: str | None, now: datetime, claim_ttl: timedelta) -> bool:
    """True when a processing claim has outlived the known send lease."""

    if not claimed_on or claim_ttl <= timedelta(0):
        return False
    return claimed_on < utc_iso(now - claim_ttl)


__all__ = [
    "ABANDONED_CLAIM_REASON",
    "ACCEPTED",
    "CAPTION_TOO_LONG",
    "CANCELLED",
    "DEFAULT_REPLY_CLAIM_TTL",
    "MAX_REPLIES_PER_EVENT",
    "PART_DOCUMENT",
    "PART_KINDS",
    "PART_TEXT",
    "PENDING",
    "PROCESSING",
    "REJECTED",
    "REPLY_STATUSES",
    "ReplyIntent",
    "TERMINAL_REPLY_STATUSES",
    "UNKNOWN",
    "blocks_later_reply",
    "claim_is_abandoned",
    "ordered_reply_intents",
    "stable_reply_id",
]
