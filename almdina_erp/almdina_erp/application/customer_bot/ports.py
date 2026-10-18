"""Outbound port for customer-bot text replies.

Adapters that implement this protocol are injected from outside Application.
The protocol has no session creation, no QR, and no provider credential.
It also does not assume a particular provider request body.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import (
    BotGatewayCapabilities,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    TextReplyRequest,
    TextSendResult,
)


@runtime_checkable
class BotTextReplyPort(Protocol):
    def capabilities(self) -> BotGatewayCapabilities: ...

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult: ...
