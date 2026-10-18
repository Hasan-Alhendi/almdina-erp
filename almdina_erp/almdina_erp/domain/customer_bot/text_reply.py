"""A text reply request and the three send outcomes a gateway may report.

Provider acceptance is not customer delivery. A confirmed rejection and an
unknown outcome are different: the unknown case includes a timeout after the
provider may already have accepted the message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .checks import required_token

_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SendDisposition(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TextReplyRequest:
    reply_id: str
    connection_ref: str
    destination_id: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reply_id", required_token(self.reply_id, "reply_id"))
        object.__setattr__(self, "connection_ref", required_token(self.connection_ref, "connection_ref"))
        object.__setattr__(
            self,
            "destination_id",
            required_token(self.destination_id, "destination_id"),
        )
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text is required")
        object.__setattr__(self, "text", self.text.strip())


@dataclass(frozen=True, slots=True)
class TextSendResult:
    """Outcome of one text-reply attempt.

    ``ACCEPTED`` means the provider accepted the send request. It does not
    mean the customer received the message. ``REJECTED`` means a confirmed
    refusal. ``UNKNOWN`` means the outcome could not be determined.
    """

    reply_id: str
    connection_ref: str
    destination_id: str
    disposition: SendDisposition
    provider_message_id: str | None
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reply_id", required_token(self.reply_id, "reply_id"))
        object.__setattr__(self, "connection_ref", required_token(self.connection_ref, "connection_ref"))
        object.__setattr__(
            self,
            "destination_id",
            required_token(self.destination_id, "destination_id"),
        )
        if not isinstance(self.disposition, SendDisposition):
            raise ValueError("disposition must be a SendDisposition")
        if self.disposition is SendDisposition.ACCEPTED:
            if self.provider_message_id is not None:
                object.__setattr__(
                    self,
                    "provider_message_id",
                    required_token(self.provider_message_id, "provider_message_id"),
                )
        elif self.provider_message_id is not None:
            raise ValueError("only an accepted send may carry a provider message id")
        reason_code = required_token(self.reason_code, "reason_code")
        if _REASON_CODE.fullmatch(reason_code) is None:
            raise ValueError("reason_code must be a short machine token")
        object.__setattr__(self, "reason_code", reason_code)


def provider_acceptance_confirms_customer_delivery(_result: TextSendResult) -> bool:
    """Acceptance, rejection, and unknown outcomes are not delivery receipts."""

    return False


def is_confirmed_rejection(result: TextSendResult) -> bool:
    return result.disposition is SendDisposition.REJECTED


def is_unknown_send_outcome(result: TextSendResult) -> bool:
    return result.disposition is SendDisposition.UNKNOWN
