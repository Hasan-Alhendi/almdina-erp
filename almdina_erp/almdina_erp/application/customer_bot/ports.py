"""Outbound ports for customer-bot replies.

Adapters that implement these protocols are injected from outside Application.
The protocols have no session creation, no QR, and no provider credential.
They also do not assume a particular provider request body.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from almdina_erp.almdina_erp.domain.customer_bot.document_reply import DocumentReplyRequest
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


@runtime_checkable
class BotDocumentReplyPort(Protocol):
    def send_document_reply(self, request: DocumentReplyRequest) -> TextSendResult: ...
