"""Text replies for the customer bot through the existing OpenWA client.

Bot-only adapter. Outcome mapping uses ``classify_openwa_send_outcome`` from
the bot send module; factory WhatsApp sends never import this file. This does
not create a session, read QR, or change ``OpenWAClient``.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import (
    BotGatewayCapabilities,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    TextReplyRequest,
    TextSendResult,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_send import (
    classify_openwa_send_outcome,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.openwa_client import OpenWAClient

_CAPABILITIES = BotGatewayCapabilities(
    sends_text=True,
    supports_interactive_options=False,
    supports_idempotent_send=False,
)


class OpenWACustomerBotTextReply:
    def __init__(self, client: OpenWAClient, session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id is required")
        self._client = client
        self._session_id = session_id.strip()

    def capabilities(self) -> BotGatewayCapabilities:
        return _CAPABILITIES

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult:
        try:
            receipt = self._client.send_text(self._session_id, request.destination_id, request.text)
        except WhatsAppTransportError as error:
            return classify_openwa_send_outcome(
                reply_id=request.reply_id,
                connection_ref=request.connection_ref,
                destination_id=request.destination_id,
                error=error,
            )
        message_id = str(getattr(receipt, "message_id", "") or "").strip()
        payload = {"messageId": message_id} if message_id else {}
        return classify_openwa_send_outcome(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            payload=payload,
        )


__all__ = ["OpenWACustomerBotTextReply"]
