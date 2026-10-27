"""Unregistered and conflicting phones receive only the published guidance."""

from __future__ import annotations

import unittest
from dataclasses import replace

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.reply_outbox import ClaimedReply
from almdina_erp.almdina_erp.application.customer_bot.verify_reply_before_send import (
    verify_reply_before_send,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    ReplyDeliveryDeps,
    deliver_pending_replies,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import BotMessageKey
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import default_texts
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import CANCELLED, PART_DOCUMENT, PART_TEXT
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import IGNORED, PROCESSED
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
from almdina_erp.tests.test_customer_bot_inbound_session import (
    NOW,
    _Directory,
    _Orders,
    _Routes,
    _Services,
    _Settings,
    _Stages,
    _header,
    _message,
)


UNKNOWN = "+963988100199"
CONFLICT = "+963988100188"
GUIDANCE = default_texts()[BotMessageKey.UNREGISTERED_PHONE]


class _Port:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.documents: list[bytes] = []

    def capabilities(self) -> BotGatewayCapabilities:
        return BotGatewayCapabilities(True, False, False)

    def send_text_reply(self, request):
        self.texts.append(request.text)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-guidance",
            reason_code="gateway_accepted",
        )

    def send_document_reply(self, request):
        self.documents.append(request.content)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-doc",
            reason_code="gateway_accepted",
        )


class UnregisteredDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = _Settings()
        self.directory = _Directory()
        self.directory.matches = {
            "+963988100101": ("CUST-A",),
            CONFLICT: ("CUST-1", "CUST-2"),
        }
        self.sessions = MemoryCustomerBotSessionStore()
        self.orders = _Orders((_header("DCO-A"), _header("DCO-SECRET", customer="CUST-1")))
        self.port = _Port()

    def _accept(self, phone: str, event: str, **kwargs):
        return accept_inbound_customer_message(
            _message("hello", event, trusted_normalized_phone=phone, **kwargs),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=self.orders,
            stages=_Stages(),
            routes=_Routes(),
            services=_Services(),
            now=NOW,
        )

    def _deliver(self):
        before = self.directory.calls
        delivered = deliver_pending_replies(
            self.sessions,
            self.port,
            deps=ReplyDeliveryDeps(
                settings=self.settings,
                directory=self.directory,
                services=_Services(),
                document_port=self.port,
            ),
            now=NOW,
            limit=10,
        )
        return before, delivered

    def test_unregistered_and_conflict_guidance_reaches_the_test_transport(self) -> None:
        for phone, event in ((UNKNOWN, "unknown-phone"), (CONFLICT, "conflict-phone")):
            with self.subTest(phone=phone):
                self.setUp()
                outcome = self._accept(phone, event)
                self.assertEqual(outcome.disposition, PROCESSED)
                self.assertEqual(outcome.messages[0].key, BotMessageKey.UNREGISTERED_PHONE)
                self.assertEqual(outcome.documents, ())
                self.assertEqual(self.orders.list_calls, 0)
                rows = list(self.sessions.replies.values())
                self.assertEqual(len(rows), 1)
                intent = rows[0].intent
                self.assertEqual(intent.message_key, BotMessageKey.UNREGISTERED_PHONE)
                self.assertIsNone(intent.customer_id)
                self.assertEqual(intent.normalized_phone, phone)
                self.assertEqual(intent.part_kind, PART_TEXT)
                self.assertIsNone(intent.document_spec)
                before, delivered = self._deliver()
                self.assertEqual(self.directory.calls, before)
                self.assertEqual([step.status for step in delivered], ["accepted"])
                self.assertEqual(self.port.texts, [GUIDANCE])
                self.assertEqual(self.port.documents, [])
                self.assertNotIn("CUST-", self.port.texts[0])
                self.assertNotIn("DCO-", self.port.texts[0])

    def test_arbitrary_text_without_a_customer_is_not_sent(self) -> None:
        self._accept(UNKNOWN, "tamper")
        row = next(iter(self.sessions.replies.values()))
        row.intent = replace(row.intent, message_key=None, body="CUST-1 owns DCO-SECRET")
        before, delivered = self._deliver()
        self.assertEqual([step.status for step in delivered], [CANCELLED])
        self.assertEqual(self.port.texts, [])
        self.assertEqual(self.port.documents, [])
        self.assertEqual(self.directory.calls, before)

    def test_public_marker_does_not_allow_a_different_body_or_a_document(self) -> None:
        self._accept(UNKNOWN, "body")
        row = next(iter(self.sessions.replies.values()))
        row.intent = replace(row.intent, body="CUST-2 DCO-SECRET")
        _before, delivered = self._deliver()
        self.assertEqual(delivered[0].status, CANCELLED)
        self.assertEqual(self.port.texts, [])

        smuggled = ClaimedReply(
            reply_id="smuggle",
            claim_token="claim",
            connection_ref="conn-a",
            provider_event_id="doc-smuggle",
            conversation_id="chat-a",
            destination_id="chat-a",
            sequence=0,
            body="invoice.pdf",
            attempt_count=1,
            part_kind=PART_DOCUMENT,
            customer_id=None,
            normalized_phone=UNKNOWN,
            acceptance_epoch=self.settings.acceptance_epoch,
            message_key=BotMessageKey.UNREGISTERED_PHONE,
        )
        decision = verify_reply_before_send(
            smuggled,
            settings=self.settings,
            directory=self.directory,
            services=_Services(),
        )
        self.assertFalse(decision.should_send)
        self.assertEqual(self.port.documents, [])

    def test_groups_and_own_account_stay_ignored(self) -> None:
        group = self._accept(UNKNOWN, "group", is_group=True)
        own = self._accept(UNKNOWN, "own", from_own_account=True)
        self.assertEqual(group.disposition, IGNORED)
        self.assertEqual(own.disposition, IGNORED)
        self.assertEqual(self.sessions.replies, {})
        self.assertEqual(self.orders.list_calls, 0)


if __name__ == "__main__":
    unittest.main()
