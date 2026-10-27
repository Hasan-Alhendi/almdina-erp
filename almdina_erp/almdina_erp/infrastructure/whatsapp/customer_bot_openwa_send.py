"""OpenWA send request shapes for the customer-bot outbound adapter.

Paths and bodies follow OpenWA gateway 0.25.0
(``66199d458f0cfe699a128a78f8b1872eb73f3abc``):

- ``POST /api/sessions/:sessionId/messages/send-text``
  body: ``{chatId, text}`` (optional mentions/linkPreview unused here)
- ``POST /api/sessions/:sessionId/messages/send-document``
  body: ``{chatId, filename, mimetype, base64}`` (+ optional caption)

Auth is the gateway API key header ``X-API-Key`` (role operator). A 201
``MessageResponseDto`` with ``messageId`` means the gateway accepted the send
for the session; it is not customer delivery. Optional ``Idempotency-Key``
exists on the gateway but this adapter does not send it, so
``supports_idempotent_send`` stays False.

This module does not open sockets and does not log PDF bytes or API keys.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    SendDisposition,
    TextSendResult,
)

_SESSION_TOKEN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_REASON_SAFE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class OpenWASendHttpRequest:
    method: str
    path: str
    body: dict[str, Any]


class CustomerBotOpenWASendTransport(Protocol):
    """Posts one JSON send. Implementations must not log body contents."""

    def post_json(self, request: OpenWASendHttpRequest) -> Mapping[str, Any]:
        """Return the parsed JSON object, or raise ``WhatsAppTransportError``."""
        ...


def build_send_text_request(*, session_id: str, chat_id: str, text: str) -> OpenWASendHttpRequest:
    session = _session_id(session_id)
    destination = _required(chat_id, "chatId")
    body_text = _required(text, "text")
    return OpenWASendHttpRequest(
        method="POST",
        path=f"/api/sessions/{session}/messages/send-text",
        body={"chatId": destination, "text": body_text},
    )


def build_send_document_request(
    *,
    session_id: str,
    chat_id: str,
    filename: str,
    mimetype: str,
    content: bytes,
    caption: str = "",
) -> OpenWASendHttpRequest:
    session = _session_id(session_id)
    destination = _required(chat_id, "chatId")
    name = _required(filename, "filename")
    if "/" in name or "\\" in name:
        raise ValueError("filename must be a safe basename")
    mime = _required(mimetype, "mimetype")
    if not isinstance(content, bytes) or not content:
        raise ValueError("document content is required")
    body: dict[str, Any] = {
        "chatId": destination,
        "filename": name,
        "mimetype": mime,
        "base64": base64.b64encode(content).decode("ascii"),
    }
    caption_text = str(caption or "").strip()
    if len(caption_text) > 1024:
        raise ValueError("caption exceeds the gateway limit")
    if caption_text:
        body["caption"] = caption_text
    return OpenWASendHttpRequest(
        method="POST",
        path=f"/api/sessions/{session}/messages/send-document",
        body=body,
    )


def classify_openwa_send_outcome(
    *,
    reply_id: str,
    connection_ref: str,
    destination_id: str,
    payload: Mapping[str, Any] | None = None,
    error: WhatsAppTransportError | None = None,
) -> TextSendResult:
    """Map one transport outcome to accepted / rejected / unknown."""

    if error is not None:
        return _from_error(reply_id, connection_ref, destination_id, error)
    message_id = str((payload or {}).get("messageId") or "").strip()
    if not message_id:
        return _result(
            reply_id,
            connection_ref,
            destination_id,
            SendDisposition.UNKNOWN,
            None,
            "missing_provider_message",
        )
    return _result(
        reply_id,
        connection_ref,
        destination_id,
        SendDisposition.ACCEPTED,
        message_id,
        "gateway_accepted",
    )


# Client statuses that do not prove the gateway never handed work to WhatsApp.
# 408: request/proxy timeout mid-flight. 409: OpenWA also uses this for
# IDEMPOTENCY_OUTCOME_UNKNOWN (message may already have been sent). 425/499:
# uncommon timing/client-abort codes without a pre-send guarantee.
_AMBIGUOUS_HTTP_STATUSES = frozenset({408, 409, 425, 499})


def _from_error(
    reply_id: str,
    connection_ref: str,
    destination_id: str,
    error: WhatsAppTransportError,
) -> TextSendResult:
    status_code = getattr(error, "status_code", None)
    # Rejected only when OpenWA documents a confirmed pre-send refusal:
    # validation/auth/not-found/payload-too-large (typical 4xx) and 501
    # (EngineNotSupportedError / ChannelMediaNotSupportedError — adapters refuse
    # before a live send; OpenAPI text says "nothing is sent"). Ambiguous 4xx
    # and all other 5xx (including 503) stay unknown.
    if isinstance(status_code, int) and status_code in _AMBIGUOUS_HTTP_STATUSES:
        return _result(
            reply_id,
            connection_ref,
            destination_id,
            SendDisposition.UNKNOWN,
            None,
            f"gateway_http_{status_code}",
        )
    if isinstance(status_code, int) and 400 <= status_code < 500:
        return _result(
            reply_id,
            connection_ref,
            destination_id,
            SendDisposition.REJECTED,
            None,
            f"gateway_http_{status_code}",
        )
    if status_code == 501:
        return _result(
            reply_id,
            connection_ref,
            destination_id,
            SendDisposition.REJECTED,
            None,
            "gateway_http_501",
        )
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return _result(
            reply_id,
            connection_ref,
            destination_id,
            SendDisposition.UNKNOWN,
            None,
            f"gateway_http_{status_code}",
        )
    code = str(getattr(error, "code", "") or "")
    if code == "timeout":
        reason = "send_timeout"
    elif code == "unreachable":
        reason = "send_unreachable"
    elif code == "invalid_response":
        reason = "invalid_gateway_response"
    elif code == "not_configured":
        reason = "gateway_not_configured"
    else:
        reason = "send_unknown"
    return _result(reply_id, connection_ref, destination_id, SendDisposition.UNKNOWN, None, reason)


def _result(
    reply_id: str,
    connection_ref: str,
    destination_id: str,
    disposition: SendDisposition,
    provider_message_id: str | None,
    reason_code: str,
) -> TextSendResult:
    if _REASON_SAFE.fullmatch(reason_code) is None:
        reason_code = "send_unknown"
    return TextSendResult(
        reply_id=reply_id,
        connection_ref=connection_ref,
        destination_id=destination_id,
        disposition=disposition,
        provider_message_id=provider_message_id,
        reason_code=reason_code,
    )


def _session_id(value: str) -> str:
    token = _required(value, "session_id")
    if _SESSION_TOKEN.fullmatch(token) is None:
        raise ValueError("session_id has an unsupported shape")
    return token


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = [
    "CustomerBotOpenWASendTransport",
    "OpenWASendHttpRequest",
    "build_send_document_request",
    "build_send_text_request",
    "classify_openwa_send_outcome",
]
