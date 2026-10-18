"""What a customer-bot gateway claims it can do.

Every flag is explicit. A gateway that omits a feature reports False.
Nothing here promises that every provider supports text, menus, or safe retries.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checks import required_bool


@dataclass(frozen=True, slots=True)
class BotGatewayCapabilities:
    sends_text: bool
    supports_interactive_options: bool
    supports_idempotent_send: bool

    def __post_init__(self) -> None:
        required_bool(self.sends_text, "sends_text")
        required_bool(self.supports_interactive_options, "supports_interactive_options")
        required_bool(self.supports_idempotent_send, "supports_idempotent_send")
