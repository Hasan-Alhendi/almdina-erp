"""OpenWA text-reply mapping. The client contract stays the one already shipped."""

from __future__ import annotations

import inspect
import unittest

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.application.whatsapp.ports import MessageReceipt
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    SendDisposition,
    TextReplyRequest,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_text_reply import (
    OpenWACustomerBotTextReply,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.openwa_client import OpenWAClient


def _request() -> TextReplyRequest:
    return TextReplyRequest(
        reply_id="reply-7",
        connection_ref="connection-a",
        destination_id="chat-a",
        text="مرحبًا",
    )


class _Client:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def send_text(self, session_id: str, chat_id: str, text: str):
        self.calls.append((session_id, chat_id, text))
        if self.error is not None:
            raise self.error
        return self.result


class OpenWACustomerBotTextReplyTests(unittest.TestCase):
    def test_send_text_contract_is_unchanged(self) -> None:
        parameters = tuple(inspect.signature(OpenWAClient.send_text).parameters)
        self.assertEqual(parameters, ("self", "session_id", "chat_id", "text"))

    def test_accepted_call_uses_send_text(self) -> None:
        client = _Client(result=MessageReceipt(message_id="wa-msg-9", timestamp=10))
        port = OpenWACustomerBotTextReply(client, "session-1")
        result = port.send_text_reply(_request())
        self.assertEqual(client.calls, [("session-1", "chat-a", "مرحبًا")])
        self.assertEqual(result.disposition, SendDisposition.ACCEPTED)
        self.assertEqual(result.provider_message_id, "wa-msg-9")
        self.assertFalse(port.capabilities().supports_idempotent_send)
        self.assertFalse(port.capabilities().supports_interactive_options)

    def test_confirmed_pre_send_http_refusals_are_rejected(self) -> None:
        cases = (
            (400, "gateway_http_400"),
            (404, "gateway_http_404"),
            (409, "gateway_http_409"),
            (501, "gateway_http_501"),
        )
        for status, reason in cases:
            with self.subTest(status=status):
                result = OpenWACustomerBotTextReply(
                    _Client(error=WhatsAppTransportError("refused", status_code=status)),
                    "session-1",
                ).send_text_reply(_request())
                self.assertEqual(result.disposition, SendDisposition.REJECTED)
                self.assertEqual(result.reason_code, reason)
                self.assertIsNone(result.provider_message_id)

    def test_http_503_and_other_5xx_are_unknown(self) -> None:
        for status in (500, 503, 502):
            with self.subTest(status=status):
                result = OpenWACustomerBotTextReply(
                    _Client(error=WhatsAppTransportError("fault", status_code=status)),
                    "session-1",
                ).send_text_reply(_request())
                self.assertEqual(result.disposition, SendDisposition.UNKNOWN)
                self.assertEqual(result.reason_code, f"gateway_http_{status}")

    def test_timeout_and_disconnect_are_unknown(self) -> None:
        timeout = OpenWACustomerBotTextReply(
            _Client(error=WhatsAppTransportError("late", code="timeout")),
            "session-1",
        ).send_text_reply(_request())
        dropped = OpenWACustomerBotTextReply(
            _Client(error=WhatsAppTransportError("down", code="unreachable")),
            "session-1",
        ).send_text_reply(_request())
        self.assertEqual(timeout.disposition, SendDisposition.UNKNOWN)
        self.assertEqual(timeout.reason_code, "send_timeout")
        self.assertEqual(dropped.disposition, SendDisposition.UNKNOWN)
        self.assertEqual(dropped.reason_code, "send_unreachable")
