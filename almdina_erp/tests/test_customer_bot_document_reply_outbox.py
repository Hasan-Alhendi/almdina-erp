"""Durable document intents, preflight cancel, and crash-window recovery."""

from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerServiceRequest,
    CustomerServiceResult,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    ReplyDeliveryDeps,
    deliver_one_reply,
    deliver_pending_replies,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import BotService, ServiceResultCode
from almdina_erp.almdina_erp.domain.customer_bot.document_reply_spec import DocumentReplySpec
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    CANCELLED,
    PART_DOCUMENT,
    PART_TEXT,
    PENDING,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import DUPLICATE, FAILED, PROCESSED
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
from almdina_erp.tests.test_customer_bot_inbound_session import (
    NOW,
    PHONE,
    _Clock,
    _Directory,
    _Orders,
    _Routes,
    _Settings,
    _Stages,
    _header,
    _message,
)


class _DocServices:
    def __init__(self) -> None:
        self.consistency_key = "price-key-1"
        self.amount = Decimal("10.00")
        self.available = True

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        if not self.available:
            return CustomerServiceResult(ServiceResultCode.PRICE_UNAVAILABLE)
        document = CustomerBotDocument(
            document_type="customer_invoice",
            filename="invoice.pdf",
            mime_type="application/pdf",
            content=b"%PDF-live",
            order_name=request.order_name,
            consistency_key=self.consistency_key,
            service_id=BotService.FINAL_COST,
            amount=str(self.amount),
            currency="USD",
        )
        return CustomerServiceResult(
            ServiceResultCode.READY,
            amount=self.amount,
            currency="USD",
            documents=(document,),
        )


class _TextGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def capabilities(self) -> BotGatewayCapabilities:
        return BotGatewayCapabilities(True, False, False)

    def send_text_reply(self, request):
        self.calls.append(request.text)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-text-1",
            reason_code="gateway_accepted",
        )


class _DocumentGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def send_document_reply(self, request):
        self.calls.append(request.filename)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-doc-1",
            reason_code="gateway_accepted",
        )


class DocumentReplyOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.settings = _Settings()
        self.directory = _Directory()
        self.sessions = MemoryCustomerBotSessionStore()
        self.services = _DocServices()
        self.text_port = _TextGateway()
        self.doc_port = _DocumentGateway()

    def accept(self, message, **kwargs):
        return accept_inbound_customer_message(
            message,
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"),)),
            stages=_Stages(),
            routes=_Routes(),
            services=self.services,
            now=self.clock.now,
            **kwargs,
        )

    def open_price_turn(self, event: str, **kwargs):
        self.accept(_message("hello", f"{event}-hello"))
        return self.accept(_message("2", event, **kwargs))

    def deps(self) -> ReplyDeliveryDeps:
        return ReplyDeliveryDeps(
            settings=self.settings,
            directory=self.directory,
            services=self.services,
            document_port=self.doc_port,
        )

    def _price_replies(self, event: str):
        return [
            row
            for row in self.sessions.replies.values()
            if row.intent.provider_event_id == event
        ]

    def test_document_intent_persists_without_pdf_bytes(self) -> None:
        outcome = self.open_price_turn("doc-1")
        self.assertEqual(outcome.disposition, PROCESSED)
        rows = sorted(self._price_replies("doc-1"), key=lambda row: row.intent.sequence)
        kinds = [row.intent.part_kind for row in rows]
        self.assertIn(PART_TEXT, kinds)
        self.assertIn(PART_DOCUMENT, kinds)
        document_rows = [row for row in rows if row.intent.part_kind == PART_DOCUMENT]
        self.assertEqual(len(document_rows), 1)
        spec = document_rows[0].intent.document_spec
        self.assertIsInstance(spec, DocumentReplySpec)
        assert spec is not None
        self.assertEqual(spec.consistency_key, "price-key-1")
        self.assertEqual(spec.order_name, "DCO-A")
        self.assertEqual(spec.customer_id, "CUST-A")
        self.assertNotIn("%PDF", document_rows[0].intent.body)

    def test_document_insert_failure_rolls_back_event_and_state(self) -> None:
        self.accept(_message("hello", "doc-fail-hello"))
        before = self.sessions.conversations[("conn-a", "chat-a", "sender-a")].revision
        original = self.sessions.complete_turn

        def boom(**kwargs):
            def failing_build():
                intents = kwargs["build_replies"]()
                raise RuntimeError(f"document insert failed after {len(intents)} intents")

            return original(**{**kwargs, "build_replies": failing_build})

        self.sessions.complete_turn = boom
        failed = self.accept(_message("2", "doc-fail"))
        self.assertEqual(failed.disposition, FAILED)
        self.assertEqual(self.sessions.conversations[("conn-a", "chat-a", "sender-a")].revision, before)
        self.assertEqual(self._price_replies("doc-fail"), [])
        self.assertNotIn(("conn-a", "doc-fail"), self.sessions.events)

    def test_crash_after_commit_recovers_without_rerunning_turn(self) -> None:
        self.accept(_message("hello", "doc-crash-hello"))
        committed: list[int] = []

        def mark(count: int) -> None:
            committed.append(count)
            raise RuntimeError("simulate worker stop after commit")

        with self.assertRaises(RuntimeError):
            self.accept(_message("2", "doc-crash"), on_replies_committed=mark)
        self.assertEqual(len(committed), 1)
        self.assertGreaterEqual(len(self._price_replies("doc-crash")), 2)
        again = self.accept(_message("2", "doc-crash"))
        self.assertEqual(again.disposition, DUPLICATE)
        pending = [row for row in self._price_replies("doc-crash") if row.status == PENDING]
        self.assertGreaterEqual(len(pending), 2)
        delivered = deliver_pending_replies(
            self.sessions, self.text_port, deps=self.deps(), now=self.clock.now, limit=20
        )
        self.assertTrue(any(step.status == "accepted" for step in delivered))
        self.assertTrue(self.text_port.calls)
        self.assertTrue(self.doc_port.calls)

    def test_preflight_cancels_when_price_version_changes(self) -> None:
        self.open_price_turn("doc-stale")
        # Drain welcome replies first so the price group is next.
        while True:
            claimed_preview = [
                row
                for row in self.sessions.replies.values()
                if row.status == PENDING and row.intent.provider_event_id != "doc-stale"
            ]
            if not claimed_preview:
                break
            deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
        self.text_port.calls.clear()
        self.services.consistency_key = "price-key-2"
        step = deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
        self.assertIsNotNone(step)
        assert step is not None
        self.assertEqual(step.status, CANCELLED)
        self.assertEqual(self.text_port.calls, [])
        self.assertEqual(self.doc_port.calls, [])

    def test_preflight_cancels_on_identity_change(self) -> None:
        self.open_price_turn("doc-id")
        self._drain_non_event("doc-id")
        self.text_port.calls.clear()
        self.doc_port.calls.clear()
        self.directory.matches[PHONE] = ("OTHER-CUST",)
        step = deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
        self.assertEqual(step.status, CANCELLED)
        self.assertEqual(self.text_port.calls, [])

    def test_preflight_cancels_on_epoch_change(self) -> None:
        self.open_price_turn("doc-epoch")
        self._drain_non_event("doc-epoch")
        self.text_port.calls.clear()
        self.doc_port.calls.clear()
        self.settings.enabled = False
        self.settings.enabled = True
        step = deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
        self.assertEqual(step.status, CANCELLED)
        self.assertEqual(self.text_port.calls, [])

    def test_lost_claim_rejects_stale_worker_write(self) -> None:
        self.accept(_message("hello", "doc-claim"))
        claimed = self.sessions.claim_next(now=self.clock.now)
        assert claimed is not None
        self.clock.now = NOW + timedelta(minutes=5)
        recovered = self.sessions.recover_abandoned_claims(
            now=self.clock.now, claim_ttl=timedelta(minutes=2)
        )
        self.assertEqual(recovered, 1)
        saved = self.sessions.record_result(
            reply_id=claimed.reply_id,
            claim_token=claimed.claim_token,
            result=TextSendResult(
                reply_id=claimed.reply_id,
                connection_ref=claimed.connection_ref,
                destination_id=claimed.destination_id,
                disposition=SendDisposition.ACCEPTED,
                provider_message_id="late",
                reason_code="gateway_accepted",
            ),
            now=self.clock.now,
        )
        self.assertFalse(saved)
        cancelled = self.sessions.record_cancelled(
            reply_id=claimed.reply_id,
            claim_token=claimed.claim_token,
            reason_code="stale",
            now=self.clock.now,
        )
        self.assertFalse(cancelled)

    def test_text_success_does_not_imply_document_success(self) -> None:
        self.open_price_turn("doc-seq")
        self._drain_non_event("doc-seq")
        self.text_port.calls.clear()
        self.doc_port.calls.clear()
        first = deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
        self.assertEqual(first.status, "accepted")
        self.services.available = False
        second = deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
        self.assertEqual(second.status, CANCELLED)
        self.assertEqual(len(self.doc_port.calls), 0)

    def _drain_non_event(self, event: str) -> None:
        while True:
            pending_other = [
                row
                for row in self.sessions.replies.values()
                if row.status == PENDING and row.intent.provider_event_id != event
            ]
            if not pending_other:
                return
            deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)


if __name__ == "__main__":
    unittest.main()
