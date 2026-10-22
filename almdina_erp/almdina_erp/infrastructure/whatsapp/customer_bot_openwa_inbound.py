"""Map an OpenWA 0.25 webhook envelope onto the internal inbound contract.

Signature verification uses the original request body bytes. Mapping never
reads a phone out of ``from``, ``author``, ``@lid``, ``contact.number``, or
the message body. ``deliveryId`` is for tracing only; retries that change it
keep the same ``idempotencyKey`` as ``provider_event_id``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundCustomerMessage,
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import fit_session_key

OPENWA_MESSAGE_RECEIVED = "message.received"
_SIGNATURE_PREFIX = "sha256="
_TEXT_TYPE = "text"


class OpenWAInboundError(ValueError):
    """A webhook envelope cannot be trusted or mapped."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def verify_openwa_signature(*, raw_body: bytes, signature_header: object, secret: str) -> bool:
    """Return True only when ``X-OpenWA-Signature`` matches HMAC-SHA256 of ``raw_body``."""

    if not isinstance(raw_body, (bytes, bytearray)):
        return False
    if not isinstance(secret, str) or not secret:
        return False
    if not isinstance(signature_header, str) or not signature_header.startswith(_SIGNATURE_PREFIX):
        return False
    provided = signature_header[len(_SIGNATURE_PREFIX) :]
    if not provided or any(ch not in "0123456789abcdef" for ch in provided.lower()):
        return False
    expected = hmac.new(secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided.lower())


def sign_openwa_body(raw_body: bytes, secret: str) -> str:
    """Build the OpenWA signature header value for tests and probes."""

    digest = hmac.new(secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).hexdigest()
    return f"{_SIGNATURE_PREFIX}{digest}"


def parse_openwa_envelope(raw_body: bytes) -> dict[str, Any]:
    """Parse the signed JSON object without re-serializing it for verification."""

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OpenWAInboundError("invalid_json") from error
    if not isinstance(payload, dict):
        raise OpenWAInboundError("invalid_envelope")
    return payload


def map_openwa_message_received(
    envelope: Mapping[str, Any],
    *,
    connection_ref: str,
) -> InboundCustomerMessage:
    """Convert a verified ``message.received`` envelope into ``InboundCustomerMessage``."""

    event = _required_str(envelope.get("event"), "event")
    if event != OPENWA_MESSAGE_RECEIVED:
        raise OpenWAInboundError("unsupported_event")
    provider_event_id = _required_str(envelope.get("idempotencyKey"), "idempotencyKey")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise OpenWAInboundError("invalid_data")

    conversation_id = _required_str(data.get("chatId"), "chatId")
    is_group = _required_bool(data.get("isGroup"), "isGroup")
    from_own_account = _required_bool(data.get("fromMe"), "fromMe")
    is_status = bool(data.get("isStatusBroadcast"))
    sender_id = _sender_id(data, is_group=is_group)
    occurred_at = _occurred_at(data.get("timestamp"))
    message_type = data.get("type")
    if not isinstance(message_type, str) or not message_type.strip():
        raise OpenWAInboundError("invalid_type")
    body = data.get("body")
    if body is None:
        text = ""
    elif isinstance(body, str):
        text = body
    else:
        raise OpenWAInboundError("invalid_body")

    # Status/story and non-text traffic stay non-operational (ignored) without
    # inventing attachment replies. ``isStatusBroadcast`` does not become a phone.
    kind = (
        InboundMessageKind.TEXT
        if message_type.strip() == _TEXT_TYPE and not is_status
        else InboundMessageKind.OTHER
    )

    trusted_phone = trusted_phone_from_openwa_sender_phone(data.get("senderPhone"))
    # Fit keys to DocType Data/unique limits without prefix truncation (hash when oversize).
    return build_inbound_customer_message(
        connection_ref=fit_session_key(connection_ref),
        provider_event_id=fit_session_key(provider_event_id),
        conversation_id=fit_session_key(conversation_id),
        sender_id=fit_session_key(sender_id),
        occurred_at=occurred_at,
        kind=kind,
        text=text if kind is InboundMessageKind.TEXT else "",
        from_own_account=from_own_account,
        is_group=is_group,
        trusted_normalized_phone=trusted_phone,
    )


def trusted_phone_from_openwa_sender_phone(raw: object) -> str | None:
    """Normalize OpenWA ``senderPhone`` to E.164, or return None.

    OpenWA supplies MSISDN digits when LID resolution succeeds. Digits are
    treated as an already-complete international number when a leading ``+``
    makes a valid E.164 value. Country codes are never invented for short local
    forms outside the shared normalizer. Provider ids, guessed contact numbers,
    and message body text are never consulted here.
    """

    if raw is None or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return normalize_customer_phone(text)
    except CustomerPhoneError as first:
        if first.code == "provider_identifier":
            return None
    if not text.isdigit():
        return None
    try:
        return normalize_customer_phone(f"+{text}")
    except CustomerPhoneError:
        return None


def _sender_id(data: Mapping[str, Any], *, is_group: bool) -> str:
    if is_group:
        author = data.get("author")
        if isinstance(author, str) and author.strip():
            return author.strip()
        raise OpenWAInboundError("missing_author")
    sender = data.get("from")
    if isinstance(sender, str) and sender.strip():
        return sender.strip()
    raise OpenWAInboundError("missing_from")


def _occurred_at(raw: object) -> datetime:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise OpenWAInboundError("invalid_timestamp")
    if raw <= 0:
        raise OpenWAInboundError("invalid_timestamp")
    # OpenWA message timestamps are unix seconds.
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise OpenWAInboundError("invalid_timestamp") from error


def _required_str(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise OpenWAInboundError(f"missing_{field}")
    return raw.strip()


def _required_bool(raw: object, field: str) -> bool:
    if not isinstance(raw, bool):
        raise OpenWAInboundError(f"invalid_{field}")
    return raw


__all__ = [
    "OPENWA_MESSAGE_RECEIVED",
    "OpenWAInboundError",
    "map_openwa_message_received",
    "parse_openwa_envelope",
    "sign_openwa_body",
    "trusted_phone_from_openwa_sender_phone",
    "verify_openwa_signature",
]
