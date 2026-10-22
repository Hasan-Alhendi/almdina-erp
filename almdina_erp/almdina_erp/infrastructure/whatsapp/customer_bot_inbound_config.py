"""Server-side OpenWA inbound connection settings for the customer bot.

Values come from trusted server storage only. The webhook body never supplies
``connection_ref``, the expected session id, or the HMAC secret. Missing or
blank values mean reception is closed; nothing is invented here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpenWAInboundConnectionConfig:
    connection_ref: str
    session_id: str
    webhook_secret: str

    @property
    def is_complete(self) -> bool:
        return bool(
            self.connection_ref.strip()
            and self.session_id.strip()
            and self.webhook_secret.strip()
        )


__all__ = ["OpenWAInboundConnectionConfig"]
