"""Customer-bot OpenWA outbound adapter: contract shapes and outcome mapping.

Uses an in-memory HTTP transport only. Does not contact WhatsApp or a live gateway.
"""

from __future__ import annotations

import base64
import json
import unittest
from io import BytesIO
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.domain.customer_bot.document_reply import DocumentReplyRequest
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import (
    SendDisposition,
    TextReplyRequest,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_openwa_outbound import (
    try_build_customer_bot_openwa_outbound,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
    deliver_customer_bot_replies,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.config import OpenWAConfig
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_http_transport import (
    UrlOpenCustomerBotOpenWATransport,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_reply import (
    OpenWACustomerBotReply,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_send import (
    OpenWASendHttpRequest,
    build_send_document_request,
    build_send_text_request,
)


class _RecordingTransport:
    def __init__(self, *, payload=None, error=None) -> None:
        self.payload = payload if payload is not None else {"messageId": "wa-1", "timestamp": 1}
        self.error = error
        self.calls: list[OpenWASendHttpRequest] = []

    def post_json(self, request: OpenWASendHttpRequest):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return dict(self.payload)


def _text_request() -> TextReplyRequest:
    return TextReplyRequest(
        reply_id="reply-text-1",
        connection_ref="conn-bot",
        destination_id="963988100101@c.us",
        text="مرحبا",
    )


def _document_request() -> DocumentReplyRequest:
    return DocumentReplyRequest(
        reply_id="reply-doc-1",
        connection_ref="conn-bot",
        destination_id="963988100101@c.us",
        filename="فاتورة.pdf",
        mime_type="application/pdf",
        content=b"%PDF-1.4 bot",
    )


class OpenWASendContractTests(unittest.TestCase):
    def test_text_request_matches_gateway_dto_fields(self) -> None:
        request = build_send_text_request(
            session_id="session-a",
            chat_id="963988100101@c.us",
            text="hello",
        )
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/api/sessions/session-a/messages/send-text")
        self.assertEqual(request.body, {"chatId": "963988100101@c.us", "text": "hello"})

    def test_document_request_matches_gateway_media_dto(self) -> None:
        pdf = b"%PDF-bytes"
        request = build_send_document_request(
            session_id="session-a",
            chat_id="963988100101@c.us",
            filename="invoice.pdf",
            mimetype="application/pdf",
            content=pdf,
        )
        self.assertEqual(request.path, "/api/sessions/session-a/messages/send-document")
        self.assertEqual(request.body["chatId"], "963988100101@c.us")
        self.assertEqual(request.body["filename"], "invoice.pdf")
        self.assertEqual(request.body["mimetype"], "application/pdf")
        self.assertEqual(request.body["base64"], base64.b64encode(pdf).decode("ascii"))
        self.assertNotIn("caption", request.body)


class OpenWACustomerBotReplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = _RecordingTransport()
        self.port = OpenWACustomerBotReply(
            self.transport,
            session_id="session-bot",
            connection_ref="conn-bot",
        )

    def test_accepted_text_uses_session_destination_and_body(self) -> None:
        result = self.port.send_text_reply(_text_request())
        self.assertEqual(result.disposition, SendDisposition.ACCEPTED)
        self.assertEqual(result.provider_message_id, "wa-1")
        call = self.transport.calls[0]
        self.assertEqual(call.path, "/api/sessions/session-bot/messages/send-text")
        self.assertEqual(call.body["chatId"], "963988100101@c.us")
        self.assertEqual(call.body["text"], "مرحبا")
        self.assertFalse(self.port.capabilities().supports_idempotent_send)

    def test_accepted_document_carries_filename_mime_and_bytes(self) -> None:
        result = self.port.send_document_reply(_document_request())
        self.assertEqual(result.disposition, SendDisposition.ACCEPTED)
        call = self.transport.calls[0]
        self.assertEqual(call.path, "/api/sessions/session-bot/messages/send-document")
        self.assertEqual(call.body["filename"], "فاتورة.pdf")
        self.assertEqual(call.body["mimetype"], "application/pdf")
        self.assertEqual(
            base64.b64decode(call.body["base64"]),
            b"%PDF-1.4 bot",
        )

    def test_confirmed_refusals_are_rejected(self) -> None:
        for status in (400, 404, 413, 422, 501):
            with self.subTest(status=status):
                port = OpenWACustomerBotReply(
                    _RecordingTransport(
                        error=WhatsAppTransportError("refused", status_code=status)
                    ),
                    session_id="session-bot",
                    connection_ref="conn-bot",
                )
                result = port.send_text_reply(_text_request())
                self.assertEqual(result.disposition, SendDisposition.REJECTED)
                self.assertEqual(result.reason_code, f"gateway_http_{status}")
                self.assertIsNone(result.provider_message_id)

    def test_ambiguous_4xx_are_unknown(self) -> None:
        # 408: timeout mid-flight — send may have started.
        # 409: OpenWA also returns IDEMPOTENCY_OUTCOME_UNKNOWN (may have sent).
        for status in (408, 409, 425, 499):
            with self.subTest(status=status):
                result = OpenWACustomerBotReply(
                    _RecordingTransport(
                        error=WhatsAppTransportError("ambiguous", status_code=status)
                    ),
                    session_id="session-bot",
                    connection_ref="conn-bot",
                ).send_document_reply(_document_request())
                self.assertEqual(result.disposition, SendDisposition.UNKNOWN)
                self.assertEqual(result.reason_code, f"gateway_http_{status}")

    def test_timeout_disconnect_and_5xx_are_unknown(self) -> None:
        cases = (
            (WhatsAppTransportError("late", code="timeout"), "send_timeout"),
            (WhatsAppTransportError("down", code="unreachable"), "send_unreachable"),
            (WhatsAppTransportError("fault", status_code=503), "gateway_http_503"),
            (WhatsAppTransportError("fault", status_code=500), "gateway_http_500"),
            (WhatsAppTransportError("bad", code="invalid_response"), "invalid_gateway_response"),
        )
        for error, reason in cases:
            with self.subTest(reason=reason):
                result = OpenWACustomerBotReply(
                    _RecordingTransport(error=error),
                    session_id="session-bot",
                    connection_ref="conn-bot",
                ).send_document_reply(_document_request())
                self.assertEqual(result.disposition, SendDisposition.UNKNOWN)
                self.assertEqual(result.reason_code, reason)

    def test_missing_message_id_is_unknown(self) -> None:
        result = OpenWACustomerBotReply(
            _RecordingTransport(payload={"timestamp": 1}),
            session_id="session-bot",
            connection_ref="conn-bot",
        ).send_text_reply(_text_request())
        self.assertEqual(result.disposition, SendDisposition.UNKNOWN)
        self.assertEqual(result.reason_code, "missing_provider_message")

    def test_errors_do_not_embed_secrets_or_pdf(self) -> None:
        port = OpenWACustomerBotReply(
            _RecordingTransport(
                error=WhatsAppTransportError(
                    "secret=api-key-should-not-leak base64=AAAA",
                    status_code=400,
                )
            ),
            session_id="session-bot",
            connection_ref="conn-bot",
        )
        result = port.send_document_reply(_document_request())
        self.assertEqual(result.disposition, SendDisposition.REJECTED)
        dumped = json.dumps(
            {
                "reply_id": result.reply_id,
                "reason_code": result.reason_code,
                "provider_message_id": result.provider_message_id,
                "disposition": result.disposition.value,
            }
        )
        self.assertNotIn("api-key", dumped)
        self.assertNotIn("AAAA", dumped)
        self.assertNotIn("%PDF", dumped)
        self.assertEqual(result.reason_code, "gateway_http_400")


class UrlOpenTransportTests(unittest.TestCase):
    def test_posts_api_key_and_json_path_without_logging_body(self) -> None:
        seen: list[Request] = []

        class _Response:
            def read(self):
                return b'{"messageId":"wa-http","timestamp":9}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout=0):
            seen.append(request)
            return _Response()

        transport = UrlOpenCustomerBotOpenWATransport(
            OpenWAConfig(base_url="http://gateway.test", api_key="test-key-only"),
            opener=opener,
        )
        payload = transport.post_json(
            build_send_text_request(
                session_id="sid",
                chat_id="chat@c.us",
                text="hi",
            )
        )
        self.assertEqual(payload["messageId"], "wa-http")
        self.assertEqual(len(seen), 1)
        request = seen[0]
        self.assertEqual(request.full_url, "http://gateway.test/api/sessions/sid/messages/send-text")
        self.assertEqual(request.headers.get("X-API-Key") or request.get_header("X-api-key"), "test-key-only")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {"chatId": "chat@c.us", "text": "hi"})

    def test_http_error_omits_response_body(self) -> None:
        def opener(request, timeout=0):
            raise HTTPError(
                request.full_url,
                400,
                "bad",
                hdrs=None,
                fp=BytesIO(b'{"message":"contains-api-secret"}'),
            )

        transport = UrlOpenCustomerBotOpenWATransport(
            OpenWAConfig(base_url="http://gateway.test", api_key="secret-key"),
            opener=opener,
        )
        with self.assertRaises(WhatsAppTransportError) as raised:
            transport.post_json(
                build_send_text_request(session_id="sid", chat_id="c@c.us", text="x")
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertNotIn("api-secret", str(raised.exception))
        self.assertNotIn("secret-key", str(raised.exception))

    def test_timeout_maps_to_transport_code(self) -> None:
        def opener(request, timeout=0):
            raise URLError(TimeoutError("timed out"))

        transport = UrlOpenCustomerBotOpenWATransport(
            OpenWAConfig(base_url="http://gateway.test", api_key="k"),
            opener=opener,
        )
        with self.assertRaises(WhatsAppTransportError) as raised:
            transport.post_json(
                build_send_text_request(session_id="sid", chat_id="c@c.us", text="x")
            )
        self.assertEqual(raised.exception.code, "timeout")


class OutboxOpenWAWiringTests(unittest.TestCase):
    """Reply group order through the OpenWA adapter with a fake transport."""

    def test_text_then_document_and_unknown_blocks_without_resend(self) -> None:
        from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
            ReplyDeliveryDeps,
            deliver_one_reply,
        )
        from almdina_erp.almdina_erp.domain.customer_bot.document_reply_spec import DocumentReplySpec
        from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
            PART_DOCUMENT,
            PART_TEXT,
            ReplyIntent,
            UNKNOWN,
        )
        from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
        from almdina_erp.tests.test_customer_bot_inbound_session import (
            NOW,
            PHONE,
            CUSTOMER,
            _Directory,
            _Services,
            _Settings,
        )

        sessions = MemoryCustomerBotSessionStore()
        settings = _Settings()
        directory = _Directory()
        services = _Services()
        spec = DocumentReplySpec(
            service_id="final_cost",
            document_type="customer_invoice",
            order_name="DCO-A",
            consistency_key="price-key-1",
            filename="invoice.pdf",
            mime_type="application/pdf",
            customer_id=CUSTOMER,
            normalized_phone=PHONE,
            acceptance_epoch=settings.acceptance_epoch,
            amount="1",
            currency="USD",
        )
        sessions._store_replies(
            (
                ReplyIntent(
                    connection_ref="conn-a",
                    provider_event_id="evt-wire",
                    conversation_id="chat-a",
                    destination_id="chat-a",
                    sequence=0,
                    body="price line",
                    part_kind=PART_TEXT,
                    customer_id=CUSTOMER,
                    normalized_phone=PHONE,
                    acceptance_epoch=settings.acceptance_epoch,
                ),
                ReplyIntent(
                    connection_ref="conn-a",
                    provider_event_id="evt-wire",
                    conversation_id="chat-a",
                    destination_id="chat-a",
                    sequence=1,
                    body="invoice.pdf",
                    part_kind=PART_DOCUMENT,
                    document_spec=spec,
                    customer_id=CUSTOMER,
                    normalized_phone=PHONE,
                    acceptance_epoch=settings.acceptance_epoch,
                ),
            )
        )
        transport = _RecordingTransport()
        port = OpenWACustomerBotReply(
            transport, session_id="session-bot", connection_ref="conn-a"
        )
        deps = ReplyDeliveryDeps(
            settings=settings,
            directory=directory,
            services=services,
            document_port=port,
        )
        first = deliver_one_reply(sessions, port, deps=deps, now=NOW)
        self.assertEqual(first.status, "accepted")
        self.assertEqual(transport.calls[0].path.endswith("send-text"), True)
        second = deliver_one_reply(sessions, port, deps=deps, now=NOW)
        self.assertEqual(second.status, "accepted")
        self.assertEqual(transport.calls[1].path.endswith("send-document"), True)
        self.assertEqual(len(transport.calls), 2)

        # Unknown does not return to pending and is not resent.
        sessions._store_replies(
            (
                ReplyIntent(
                    connection_ref="conn-a",
                    provider_event_id="evt-unk",
                    conversation_id="chat-a",
                    destination_id="chat-a",
                    sequence=0,
                    body="again",
                    part_kind=PART_TEXT,
                    customer_id=CUSTOMER,
                    normalized_phone=PHONE,
                    acceptance_epoch=settings.acceptance_epoch,
                ),
            )
        )
        failing = OpenWACustomerBotReply(
            _RecordingTransport(error=WhatsAppTransportError("late", code="timeout")),
            session_id="session-bot",
            connection_ref="conn-a",
        )
        unknown = deliver_one_reply(
            sessions,
            failing,
            deps=ReplyDeliveryDeps(
                settings=settings,
                directory=directory,
                services=services,
                document_port=failing,
            ),
            now=NOW,
        )
        self.assertEqual(unknown.status, UNKNOWN)
        again = deliver_one_reply(
            sessions,
            failing,
            deps=ReplyDeliveryDeps(
                settings=settings,
                directory=directory,
                services=services,
                document_port=failing,
            ),
            now=NOW,
        )
        self.assertIsNone(again)


class LiveDeliveryGateTests(unittest.TestCase):
    def test_live_flag_stays_false(self) -> None:
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)

    def test_factory_skips_secrets_and_sockets_when_live_disabled(self) -> None:
        with mock.patch(
            "almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_http_transport.UrlOpenCustomerBotOpenWATransport"
        ) as transport_cls:
            self.assertIsNone(try_build_customer_bot_openwa_outbound(live_enabled=False))
        transport_cls.assert_not_called()

    def test_deliver_entry_builds_no_client_while_disabled(self) -> None:
        with mock.patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_openwa_outbound.try_build_customer_bot_openwa_outbound"
        ) as build:
            self.assertEqual(deliver_customer_bot_replies(), 0)
        build.assert_not_called()
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)


if __name__ == "__main__":
    unittest.main()
