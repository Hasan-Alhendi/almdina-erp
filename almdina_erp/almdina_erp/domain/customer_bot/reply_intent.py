"""One text reply owed for a committed inbound event.

The row is the durable handoff to a later sender. Provider acceptance is a
later status on that row and is not customer delivery. Nothing here stores a
gateway secret or treats a sender id as a phone number.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from .checks import required_token
from .session_admission import utc_iso

PENDING = "pending"
PROCESSING = "processing"
ACCEPTED = "accepted"
REJECTED = "rejected"
UNKNOWN = "unknown"

REPLY_STATUSES = frozenset({PENDING, PROCESSING, ACCEPTED, REJECTED, UNKNOWN})
TERMINAL_REPLY_STATUSES = frozenset({ACCEPTED, REJECTED, UNKNOWN})
MAX_REPLIES_PER_EVENT = 20
# Bound above OpenWAClient's default HTTP timeout (45s). A live claim is not
# cut short by a shorter arbitrary delay. After this lease an abandoned claim
# becomes unknown without another send.
DEFAULT_REPLY_CLAIM_TTL = timedelta(minutes=2)
ABANDONED_CLAIM_REASON = "claim_abandoned"


@dataclass(frozen=True, slots=True)
class ReplyIntent:
    connection_ref: str
    provider_event_id: str
    conversation_id: str
    destination_id: str
    sequence: int
    body: str

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
        if not isinstance(self.body, str) or not self.body.strip():
            raise ValueError("body is required")
        object.__setattr__(self, "body", self.body.strip())

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

    ``pending`` and ``processing`` wait. ``rejected`` and ``unknown`` keep
    later rows stored and unsent. No automatic retry or skip runs here.
    """

    return status != ACCEPTED


def claim_is_abandoned(claimed_on: str | None, now: datetime, claim_ttl: timedelta) -> bool:
    """True when a processing claim has outlived the known send lease."""

    if not claimed_on or claim_ttl <= timedelta(0):
        return False
    return claimed_on < utc_iso(now - claim_ttl)
