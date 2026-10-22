"""Pure pilot-mode values for the customer bot (no Frappe, no OpenWA I/O).

Server storage and admin commands live in the Frappe adapter. Domain and
Application never import this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
)


@dataclass(frozen=True, slots=True)
class CustomerBotPilotConfig:
    """Operational pilot gate. Missing phone or start time means not ready."""

    enabled: bool
    phone_e164: str | None
    started_at: datetime | None
    transport_armed: bool

    @property
    def is_ready(self) -> bool:
        return bool(self.enabled and self.phone_e164 and self.started_at is not None)

    def admits_phone(self, normalized_phone: str | None) -> bool:
        if not self.is_ready:
            return False
        if not isinstance(normalized_phone, str) or not normalized_phone:
            return False
        return normalized_phone == self.phone_e164

    def admits_intent(self, *, normalized_phone: str | None, created_on: datetime | None) -> bool:
        if not self.admits_phone(normalized_phone):
            return False
        if created_on is None or self.started_at is None:
            return False
        created = created_on if created_on.tzinfo is not None else created_on.replace(tzinfo=timezone.utc)
        started = (
            self.started_at
            if self.started_at.tzinfo is not None
            else self.started_at.replace(tzinfo=timezone.utc)
        )
        return created >= started


def parse_pilot_phone(raw: object) -> str:
    """Return a trusted E.164 value or raise ``CustomerPhoneError`` / ``ValueError``."""

    return normalize_customer_phone(raw)


def pilot_phone_or_none(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return normalize_customer_phone(raw)
    except CustomerPhoneError:
        return None


__all__ = [
    "CustomerBotPilotConfig",
    "parse_pilot_phone",
    "pilot_phone_or_none",
]
