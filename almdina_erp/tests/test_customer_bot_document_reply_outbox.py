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
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotMessageKey,
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.document_reply_spec import DocumentReplySpec
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import DOCUMENT_CAPTION_MAX
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    CANCELLED,
    CAPTION_TOO_LONG,
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
        self.render_calls = 0

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        return self._result(request, content=None)

    def materialize(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        self.render_calls += 1
        return self._result(request, content=b"%PDF-live")

    def _result(self, request: CustomerServiceRequest, *, content: bytes | None) -> CustomerServiceResult:
        if not self.available:
            return CustomerServiceResult(ServiceResultCode.PRICE_UNAVAILABLE)
        if self.consistency_key != "price-key-1":
            return CustomerServiceResult(ServiceResultCode.PRICE_DATA_CHANGED)
        document = CustomerBotDocument(
            document_type="customer_invoice",
            filename="invoice.pdf",
            mime_type="application/pdf",
            content=content,
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
        self.assertEqual(kinds, [PART_DOCUMENT])
        document_rows = [row for row in rows if row.intent.part_kind == PART_DOCUMENT]
        self.assertEqual(len(document_rows), 1)
        spec = document_rows[0].intent.document_spec
        self.assertIsInstance(spec, DocumentReplySpec)
        assert spec is not None
        self.assertEqual(spec.consistency_key, "price-key-1")
        self.assertEqual(spec.order_name, "DCO-A")
        self.assertEqual(spec.customer_id, "CUST-A")
        self.assertIn("DCO-A", spec.caption)
        self.assertIn("10.00", spec.caption)
        self.assertIn("USD", spec.caption)
        self.assertIn("0", spec.caption)
        self.assertNotIn("%PDF", document_rows[0].intent.body)
        self.assertNotIn("%PDF", spec.dumps())

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
        self.assertEqual(committed, [1])
        self.assertEqual(len(self._price_replies("doc-crash")), 1)
        again = self.accept(_message("2", "doc-crash"))
        self.assertEqual(again.disposition, DUPLICATE)
        pending = [row for row in self._price_replies("doc-crash") if row.status == PENDING]
        self.assertEqual(len(pending), 1)
        delivered = deliver_pending_replies(
            self.sessions, self.text_port, deps=self.deps(), now=self.clock.now, limit=20
        )
        self.assertTrue(any(step.status == "accepted" for step in delivered))
        self.assertTrue(self.text_port.calls)
        self.assertTrue(self.doc_port.calls)

    def test_preflight_cancels_when_price_version_changes(self) -> None:
        self.open_price_turn("doc-stale")
        self.services.consistency_key = "price-key-2"
        self._deliver_all()
        document = next(row for row in self._price_replies("doc-stale") if row.intent.part_kind == PART_DOCUMENT)
        self.assertEqual(document.status, CANCELLED)
        self.assertEqual(self.doc_port.calls, [])
        self.assertFalse(any("10.00" in call for call in self.text_port.calls))

    def test_preflight_cancels_on_identity_change(self) -> None:
        self.open_price_turn("doc-id")
        self.directory.matches[PHONE] = ("OTHER-CUST",)
        self._deliver_all()
        document = next(row for row in self._price_replies("doc-id") if row.intent.part_kind == PART_DOCUMENT)
        self.assertEqual(document.status, CANCELLED)
        self.assertEqual(self.doc_port.calls, [])
        self.assertEqual(self.text_port.calls, [])

    def test_preflight_cancels_on_epoch_change(self) -> None:
        self.open_price_turn("doc-epoch")
        self.settings.enabled = False
        self.settings.enabled = True
        self._deliver_all()
        document = next(row for row in self._price_replies("doc-epoch") if row.intent.part_kind == PART_DOCUMENT)
        self.assertEqual(document.status, CANCELLED)
        self.assertEqual(self.doc_port.calls, [])
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
        self.services.available = False
        self._deliver_all()
        hello = next(
            row for row in self.sessions.replies.values() if row.intent.provider_event_id == "doc-seq-hello"
        )
        document = next(row for row in self._price_replies("doc-seq") if row.intent.part_kind == PART_DOCUMENT)
        self.assertEqual(hello.status, "accepted")
        self.assertEqual(document.status, CANCELLED)
        self.assertEqual(self.doc_port.calls, [])

    def _deliver_all(self) -> None:
        for _index in range(6):
            step = deliver_one_reply(self.sessions, self.text_port, deps=self.deps(), now=self.clock.now)
            if step is None:
                return

    def test_caption_limit_keeps_the_custom_failure_and_does_not_retry(self) -> None:
        custom_failure = "تعذر إرسال الوصف المخصص"
        ask = 400
        exact_name = "ط" * (DOCUMENT_CAPTION_MAX - 1 - ask)
        under_name = "ط" * (DOCUMENT_CAPTION_MAX - 2 - ask)
        over_name = "ط" * (DOCUMENT_CAPTION_MAX - ask)
        self.assertEqual(len(exact_name) + 1 + ask, DOCUMENT_CAPTION_MAX)
        self.assertEqual(len(under_name) + 1 + ask, DOCUMENT_CAPTION_MAX - 1)
        self.assertEqual(len(over_name) + 1 + ask, DOCUMENT_CAPTION_MAX + 1)

        def prepare() -> None:
            self.setUp()
            self.settings.published[BotMessageKey.FINAL_PRICE] = "{order_name}"
            self.settings.published[BotMessageKey.ASK_ORDER_NUMBER] = "ب" * ask
            self.settings.published[BotMessageKey.INVOICE_FAILED] = custom_failure

        prepare()
        under = self._priced(under_name, "cap-under")
        self.assertEqual(under.disposition, PROCESSED)
        under_row = self._price_replies("cap-under")[0]
        self.assertEqual(under_row.intent.part_kind, PART_DOCUMENT)
        self.assertEqual(len(under_row.intent.document_spec.caption), DOCUMENT_CAPTION_MAX - 1)
        self.assertIn(under_name, under_row.intent.document_spec.caption)

        prepare()
        exact = self._priced(exact_name, "cap-exact")
        exact_row = self._price_replies("cap-exact")[0]
        self.assertEqual(exact_row.intent.part_kind, PART_DOCUMENT)
        self.assertEqual(len(exact_row.intent.document_spec.caption), DOCUMENT_CAPTION_MAX)

        prepare()
        over = self._priced(over_name, "cap-over")
        self.assertEqual(over.disposition, PROCESSED)
        rows = self._price_replies("cap-over")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].intent.part_kind, PART_TEXT)
        self.assertEqual(rows[0].intent.body, custom_failure)
        self.assertEqual(rows[0].intent.message_key, BotMessageKey.INVOICE_FAILED)
        self.assertEqual(rows[0].reason_code, CAPTION_TOO_LONG)
        self.assertNotIn("10.00", rows[0].intent.body)
        self.assertNotIn(over_name, rows[0].intent.body)
        self.assertIsNone(rows[0].intent.document_spec)
        again = self._priced(over_name, "cap-over")
        self.assertEqual(again.disposition, DUPLICATE)
        self.assertEqual(len(self._price_replies("cap-over")), 1)
        self._deliver_all()
        self.assertEqual(rows[0].status, "accepted")
        self.assertEqual(rows[0].reason_code, CAPTION_TOO_LONG)
        self.assertEqual(self.text_port.calls.count(custom_failure), 1)
        self.assertEqual(self.doc_port.calls, [])
        self.assertFalse(any("10.00" in call for call in self.text_port.calls))
        self._deliver_all()
        self.assertEqual(self.text_port.calls.count(custom_failure), 1)
        self.assertEqual(self.doc_port.calls, [])

    def _priced(self, order_name: str, event: str):
        self.accept(_message("hello", f"{event}-hello"))
        return accept_inbound_customer_message(
            _message("2", event),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header(order_name),)),
            stages=_Stages(),
            routes=_Routes(),
            services=self.services,
            now=self.clock.now,
        )

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
