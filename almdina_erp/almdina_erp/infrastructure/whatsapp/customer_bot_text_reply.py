"""Text replies for the customer bot through the existing OpenWA client.

This does not create a session, read the factory session, or change
``OpenWAClient``. A caller has to supply the client and the session id.

Classification follows OpenWA's own send-failure contract as seen from HTTP
status alone. A 4xx or 501 proves the request was refused before a successful
hand-off. A 5xx, including 503, does not: OpenWA uses 503 for recipient-lookup
timeouts that happen before send and also for generic service-unavailable
faults that its idempotency layer treats as an uncertain outcome. A timeout,
dropped connection, or unreadable body is ``unknown`` and must not be sent
again by this adapter.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import (
    BotGatewayCapabilities,
)
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    SendDisposition,
    TextReplyRequest,
    TextSendResult,
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
            return _failure(request, error)
        message_id = str(getattr(receipt, "message_id", "") or "").strip()
        if not message_id:
            return _result(request, SendDisposition.UNKNOWN, None, "missing_provider_message")
        return _result(request, SendDisposition.ACCEPTED, message_id, "gateway_accepted")


def _failure(request: TextReplyRequest, error: WhatsAppTransportError) -> TextSendResult:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return _result(request, SendDisposition.REJECTED, None, f"gateway_http_{status_code}")
    if status_code == 501:
        return _result(request, SendDisposition.REJECTED, None, "gateway_http_501")
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return _result(request, SendDisposition.UNKNOWN, None, f"gateway_http_{status_code}")
    code = str(getattr(error, "code", "") or "")
    if code == "timeout":
        reason = "send_timeout"
    elif code == "unreachable":
        reason = "send_unreachable"
    elif code == "invalid_response":
        reason = "invalid_gateway_response"
    else:
        reason = "send_unknown"
    return _result(request, SendDisposition.UNKNOWN, None, reason)


def _result(
    request: TextReplyRequest,
    disposition: SendDisposition,
    provider_message_id: str | None,
    reason_code: str,
) -> TextSendResult:
    return TextSendResult(
        reply_id=request.reply_id,
        connection_ref=request.connection_ref,
        destination_id=request.destination_id,
        disposition=disposition,
        provider_message_id=provider_message_id,
        reason_code=reason_code,
    )


__all__ = ["OpenWACustomerBotTextReply"]
