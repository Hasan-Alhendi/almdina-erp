"""Customer-bot OpenWA outbound adapter for text and in-memory PDF replies.

Domain and Application stay free of OpenWA details. This adapter builds the
gateway JSON shapes, posts through an injected transport, and maps outcomes to
``accepted`` / ``rejected`` / ``unknown``. It does not create sessions, read
QR, or touch the factory WhatsApp send path. PDF bytes stay in memory for the
request body only; they are never written to File or logged.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.domain.customer_bot.document_reply import DocumentReplyRequest
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import (
    BotGatewayCapabilities,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    TextReplyRequest,
    TextSendResult,
)

from .customer_bot_openwa_send import (
    CustomerBotOpenWASendTransport,
    build_send_document_request,
    build_send_text_request,
    classify_openwa_send_outcome,
)

# Idempotency-Key is optional on the gateway and unused here, so the capability
# stays False: Application must not auto-retry on that basis.
_CAPABILITIES = BotGatewayCapabilities(
    sends_text=True,
    supports_interactive_options=False,
    supports_idempotent_send=False,
)


class OpenWACustomerBotReply:
    """Implements both bot reply ports against one OpenWA session."""

    def __init__(
        self,
        transport: CustomerBotOpenWASendTransport,
        *,
        session_id: str,
        connection_ref: str,
    ) -> None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id is required")
        if not isinstance(connection_ref, str) or not connection_ref.strip():
            raise ValueError("connection_ref is required")
        self._transport = transport
        self._session_id = session_id.strip()
        self._connection_ref = connection_ref.strip()

    def capabilities(self) -> BotGatewayCapabilities:
        return _CAPABILITIES

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult:
        self._guard_connection(request.connection_ref, request.destination_id)
        try:
            http = build_send_text_request(
                session_id=self._session_id,
                chat_id=request.destination_id,
                text=request.text,
            )
            payload = self._transport.post_json(http)
        except WhatsAppTransportError as error:
            return classify_openwa_send_outcome(
                reply_id=request.reply_id,
                connection_ref=request.connection_ref,
                destination_id=request.destination_id,
                error=error,
            )
        except Exception:
            return classify_openwa_send_outcome(
                reply_id=request.reply_id,
                connection_ref=request.connection_ref,
                destination_id=request.destination_id,
                error=WhatsAppTransportError("send failed", code="send_unknown"),
            )
        return classify_openwa_send_outcome(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            payload=payload,
        )

    def send_document_reply(self, request: DocumentReplyRequest) -> TextSendResult:
        self._guard_connection(request.connection_ref, request.destination_id)
        try:
            http = build_send_document_request(
                session_id=self._session_id,
                chat_id=request.destination_id,
                filename=request.filename,
                mimetype=request.mime_type,
                content=request.content,
            )
            payload = self._transport.post_json(http)
        except WhatsAppTransportError as error:
            return classify_openwa_send_outcome(
                reply_id=request.reply_id,
                connection_ref=request.connection_ref,
                destination_id=request.destination_id,
                error=error,
            )
        except Exception:
            return classify_openwa_send_outcome(
                reply_id=request.reply_id,
                connection_ref=request.connection_ref,
                destination_id=request.destination_id,
                error=WhatsAppTransportError("send failed", code="send_unknown"),
            )
        return classify_openwa_send_outcome(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            payload=payload,
        )

    def _guard_connection(self, connection_ref: str, destination_id: str) -> None:
        if connection_ref != self._connection_ref:
            raise WhatsAppTransportError("connection_ref mismatch", code="send_unknown")
        if not isinstance(destination_id, str) or not destination_id.strip():
            raise WhatsAppTransportError("destination missing", code="send_unknown")


__all__ = ["OpenWACustomerBotReply"]
