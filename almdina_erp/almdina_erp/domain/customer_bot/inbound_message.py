"""One inbound customer-bot event, independent of any provider payload.

``sender_id`` is the provider's participant identifier. It is not a phone
number, even when it contains digits or a WhatsApp-looking suffix. The
gateway adapter is responsible, later, for verifying a phone from a trusted
source and passing only that verified value. This model does not contact a
provider and does not prove who sent the message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .checks import required_bool, required_token

_E164_PHONE = re.compile(r"^\+[1-9]\d{7,14}$")


class InboundMessageKind(str, Enum):
    TEXT = "text"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class InboundCustomerMessage:
    connection_ref: str
    provider_event_id: str
    conversation_id: str
    sender_id: str
    occurred_at: datetime
    kind: InboundMessageKind
    text: str
    from_own_account: bool
    is_group: bool
    normalized_phone: str | None

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
        object.__setattr__(self, "sender_id", required_token(self.sender_id, "sender_id"))
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be a timezone-aware datetime")
        if not isinstance(self.kind, InboundMessageKind):
            raise ValueError("kind must be an InboundMessageKind")
        if not isinstance(self.text, str):
            raise ValueError("text must be a string")
        required_bool(self.from_own_account, "from_own_account")
        required_bool(self.is_group, "is_group")
        if self.normalized_phone is not None and _E164_PHONE.fullmatch(self.normalized_phone) is None:
            raise ValueError(
                "normalized_phone must be an E.164 value already verified by the gateway adapter"
            )


def build_inbound_customer_message(
    *,
    connection_ref: str,
    provider_event_id: str,
    conversation_id: str,
    sender_id: str,
    occurred_at: datetime,
    kind: InboundMessageKind,
    text: str,
    from_own_account: bool,
    is_group: bool,
    trusted_normalized_phone: str | None = None,
) -> InboundCustomerMessage:
    """Build an inbound event without reading a phone out of ``sender_id``.

    ``trusted_normalized_phone`` is used only when the gateway adapter has
    already decided the value is a verified phone. ``None`` always leaves
    ``normalized_phone`` empty.
    """

    return InboundCustomerMessage(
        connection_ref=connection_ref,
        provider_event_id=provider_event_id,
        conversation_id=conversation_id,
        sender_id=sender_id,
        occurred_at=occurred_at,
        kind=kind,
        text=text,
        from_own_account=from_own_account,
        is_group=is_group,
        normalized_phone=_trusted_phone(trusted_normalized_phone),
    )


def _trusted_phone(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("trusted_normalized_phone must be a string or None")
    phone = value.strip()
    if _E164_PHONE.fullmatch(phone) is None:
        raise ValueError("trusted_normalized_phone must already be E.164")
    return phone
