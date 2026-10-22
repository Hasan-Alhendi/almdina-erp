"""Pure customer-bot operations mode values (no Frappe, no OpenWA I/O).

Server storage and admin commands live in the Frappe adapter. Domain and
Application never import this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

OPS_MODE_OFF = "off"
OPS_MODE_PILOT = "pilot"
OPS_MODE_PRODUCTION = "production"
OPS_MODES = frozenset({OPS_MODE_OFF, OPS_MODE_PILOT, OPS_MODE_PRODUCTION})


@dataclass(frozen=True, slots=True)
class CustomerBotOpsConfig:
    """Operational accept/transport gate for off, pilot, and production.

    Missing start time means not ready in every non-off mode. Pilot also
    requires a trusted E.164. Production admits every trusted phone once ready;
    it never invents a phone from ``@lid`` or message text.
    """

    mode: str
    pilot_phone_e164: str | None
    started_at: datetime | None
    transport_armed: bool
    transport_live: bool

    @property
    def is_ready(self) -> bool:
        if self.mode == OPS_MODE_OFF:
            return False
        if self.started_at is None:
            return False
        if self.mode == OPS_MODE_PILOT:
            return bool(self.pilot_phone_e164)
        if self.mode == OPS_MODE_PRODUCTION:
            return True
        return False

    def admits_inbound_phone(self, normalized_phone: str | None) -> bool:
        if not self.is_ready:
            return False
        if not isinstance(normalized_phone, str) or not normalized_phone:
            return False
        if self.mode == OPS_MODE_PILOT:
            return normalized_phone == self.pilot_phone_e164
        if self.mode == OPS_MODE_PRODUCTION:
            return True
        return False

    def admits_intent(
        self,
        *,
        normalized_phone: str | None,
        created_on: datetime | None,
    ) -> bool:
        if not self.admits_inbound_phone(normalized_phone):
            return False
        if created_on is None or self.started_at is None:
            return False
        created = (
            created_on
            if created_on.tzinfo is not None
            else created_on.replace(tzinfo=timezone.utc)
        )
        started = (
            self.started_at
            if self.started_at.tzinfo is not None
            else self.started_at.replace(tzinfo=timezone.utc)
        )
        return created >= started

    @property
    def claim_eligible_phone(self) -> str | None:
        """Pilot claims one phone; production claims any phone (``None`` filter)."""

        if self.mode == OPS_MODE_PILOT and self.pilot_phone_e164:
            return self.pilot_phone_e164
        return None


__all__ = [
    "OPS_MODES",
    "OPS_MODE_OFF",
    "OPS_MODE_PILOT",
    "OPS_MODE_PRODUCTION",
    "CustomerBotOpsConfig",
]
