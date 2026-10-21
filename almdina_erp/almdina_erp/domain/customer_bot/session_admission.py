"""Admission rules for one trusted inbound customer-bot event.

These values describe internal processing, not provider delivery. ``processed``
means the engine turn was committed. It does not mean the customer received a
reply. A duplicate of a committed event is not a reply to send again.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from .inbound_message import InboundCustomerMessage, InboundMessageKind

PROCEED = "proceed"
PROCESSED = "processed"
DUPLICATE = "duplicate"
IN_PROGRESS = "in_progress"
CONVERSATION_BUSY = "conversation_busy"
CONFLICT = "conflict"
IGNORED = "ignored"
NOT_ACCEPTING = "not_accepting"
SUPPRESSED = "suppressed"
LOST_LEASE = "lost_lease"
FAILED = "failed"

DEFAULT_SESSION_TTL = timedelta(minutes=30)
DEFAULT_LEASE_TTL = timedelta(minutes=2)
DEFAULT_CONVERSATION_RETENTION = timedelta(days=7)
DEFAULT_EVENT_RETENTION = timedelta(days=30)
MAX_KEY_LENGTH = 140

_SENDABLE = frozenset({PROCESSED})
_RETRY_LATER = frozenset({CONVERSATION_BUSY, IN_PROGRESS, FAILED, LOST_LEASE})


def is_operational_message(message: InboundCustomerMessage) -> bool:
    """A text from someone else in a direct chat may advance a conversation."""

    return (
        message.kind is InboundMessageKind.TEXT
        and not message.from_own_account
        and not message.is_group
    )


def event_fingerprint(message: InboundCustomerMessage) -> str:
    """Hash the fields that would make this event a different message.

    The digest is what gets stored. The raw text is not kept for comparison.
    """

    occurred = message.occurred_at.astimezone(timezone.utc).isoformat()
    material = "\n".join(
        (
            message.connection_ref,
            message.provider_event_id,
            message.conversation_id,
            message.sender_id,
            message.kind.value,
            message.text,
            "1" if message.from_own_account else "0",
            "1" if message.is_group else "0",
            message.normalized_phone or "",
            occurred,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def keys_fit(message: InboundCustomerMessage) -> bool:
    values = (
        message.connection_ref,
        message.provider_event_id,
        message.conversation_id,
        message.sender_id,
    )
    return all(len(value) <= MAX_KEY_LENGTH for value in values)


def lease_is_active(token: str | None, expires_on: str | None, now_iso: str) -> bool:
    return bool(token) and bool(expires_on) and expires_on > now_iso


def classify_stored_event(
    *,
    status: str,
    stored_fingerprint: str,
    fingerprint: str,
    lease_token: str | None,
    lease_expires_on: str | None,
    now_iso: str,
) -> str:
    """Classify an event row that already exists. Never a new message."""

    if stored_fingerprint != fingerprint:
        return CONFLICT
    if status == "completed":
        return DUPLICATE
    if lease_is_active(lease_token, lease_expires_on, now_iso):
        return IN_PROGRESS
    return "reclaim"


def disposition_is_sendable(disposition: str) -> bool:
    return disposition in _SENDABLE


def disposition_retries_later(disposition: str) -> bool:
    return disposition in _RETRY_LATER


def utc_iso(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("session time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


__all__ = [
    "CONFLICT",
    "CONVERSATION_BUSY",
    "DEFAULT_CONVERSATION_RETENTION",
    "DEFAULT_EVENT_RETENTION",
    "DEFAULT_LEASE_TTL",
    "DEFAULT_SESSION_TTL",
    "DUPLICATE",
    "FAILED",
    "IGNORED",
    "IN_PROGRESS",
    "LOST_LEASE",
    "MAX_KEY_LENGTH",
    "NOT_ACCEPTING",
    "PROCEED",
    "PROCESSED",
    "SUPPRESSED",
    "classify_stored_event",
    "disposition_is_sendable",
    "disposition_retries_later",
    "event_fingerprint",
    "is_operational_message",
    "keys_fit",
    "lease_is_active",
    "utc_iso",
]
