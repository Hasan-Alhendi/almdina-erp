"""PDF generation happens once, on a document send attempt.

Webhook acceptance and text preflight may read eligibility. They must not
call the PDF port. A failed or stale render is cancelled and is not a
successful send.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.approved_plan_service import (
    CustomerBotApprovedPlanService,
    CustomerBotApprovedPlanSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    ReplyDeliveryDeps,
    deliver_pending_replies,
)
from almdina_erp.almdina_erp.application.customer_bot.final_price_service import (
    CustomerBotFinalPriceService,
    CustomerBotFinalPriceSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.measurements_service import (
    CustomerBotMeasurementsService,
    CustomerBotMeasurementsSnapshot,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import BotService
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    CANCELLED,
    PART_DOCUMENT,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import PROCESSED
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
from almdina_erp.tests.test_customer_bot_inbound_session import (
    _Directory,
    _Orders,
    _Routes,
    _Settings,
    _Stages,
    _header,
    _message,
)


def _price_snapshot(key: str = "price-1") -> CustomerBotFinalPriceSnapshot:
    return CustomerBotFinalPriceSnapshot(
        available=True,
        amount=Decimal("10.00"),
        currency="USD",
        invoice_payload={"kind": "customer_invoice", "totals": []},
        consistency_key=key,
    )


def _plan_snapshot(key: str = "plan-1") -> CustomerBotApprovedPlanSnapshot:
    return CustomerBotApprovedPlanSnapshot(
        available=True,
        plan_name="CP-1",
        revision=1,
        source_type="System",
        consistency_key=key,
    )


def _measurements_snapshot(key: str = "measure-1") -> CustomerBotMeasurementsSnapshot:
    return CustomerBotMeasurementsSnapshot(
        available=True,
        order_name="DCO-A",
        consistency_key=key,
    )


class _Unchanged:
    pass


_UNCHANGED = _Unchanged()


class _Reader:
    def __init__(self, current, pdf: "_Pdf") -> None:
        self.current = current
        self.pdf = pdf
        self.calls = 0

    def read(self, phone: str, order_name: str):
        del phone, order_name
        self.calls += 1
        if self.pdf.calls and self.pdf.after_render is not _UNCHANGED:
            return self.pdf.after_render
        return self.current


class _Pdf:
    def __init__(self, settings: _Settings | None = None, *, fail: str = "") -> None:
        self.settings = settings
        self.fail = fail
        self.calls: list[tuple] = []
        self.after_render = _UNCHANGED

    def render(self, *args) -> bytes:
        self.calls.append(args)
        if self.settings is not None and self.fail == "disable":
            self.settings.enabled = False
        if self.fail == "boom":
            raise RuntimeError("chromium failed")
        if self.fail == "empty":
            return b""
        return b"%PDF-once"


class _TextPort:
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
            provider_message_id="wa-text",
            reason_code="gateway_accepted",
        )


class _DocumentPort:
    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.captions: list[str] = []

    def send_document_reply(self, request):
        self.calls.append(request.content)
        self.captions.append(request.caption)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="wa-doc",
            reason_code="gateway_accepted",
        )


def _chromium_executable() -> str:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "chromium" / "chrome-linux" / "headless_shell"
        if candidate.is_file():
            return str(candidate)
    return ""


class _ChromiumPdf:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.after_render = _UNCHANGED
        self.executable = _chromium_executable()

    def render(self, *args) -> bytes:
        from almdina_erp.almdina_erp.infrastructure.whatsapp.measurement_pdf import (
            html_to_pdf_via_chromium,
        )

        self.calls.append(args)
        return html_to_pdf_via_chromium(
            "<html><body><p>phase-1 invoice</p></body></html>",
            chromium_path=self.executable,
        )


class PdfDeliveryPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = _Settings()
        self.directory = _Directory()
        self.sessions = MemoryCustomerBotSessionStore()
        self.text_port = _TextPort()
        self.document_port = _DocumentPort()

    def _service(self, kind: str, pdf: _Pdf):
        if kind == BotService.FINAL_COST:
            return CustomerBotFinalPriceService(_Reader(_price_snapshot(), pdf), pdf), "2"
        if kind == BotService.APPROVED_CUTTING_PLAN:
            return CustomerBotApprovedPlanService(_Reader(_plan_snapshot(), pdf), pdf), "3"
        return CustomerBotMeasurementsService(_Reader(_measurements_snapshot(), pdf), pdf), "4"

    def _run(self, kind: str, pdf: _Pdf, event: str):
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        service, digit = self._service(kind, pdf)
        opened = accept_inbound_customer_message(
            _message("hello", f"{event}-hello"),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"),)),
            stages=_Stages(),
            routes=_Routes(),
            services=service,
            now=NOW,
        )
        self.assertEqual(opened.disposition, PROCESSED)
        selected = accept_inbound_customer_message(
            _message(digit, event),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"),)),
            stages=_Stages(),
            routes=_Routes(),
            services=service,
            now=NOW,
        )
        self.assertEqual(selected.disposition, PROCESSED)
        self.assertEqual(pdf.calls, [])
        specs = [
            row.intent.document_spec
            for row in self.sessions.replies.values()
            if row.intent.provider_event_id == event and row.intent.part_kind == PART_DOCUMENT
        ]
        self.assertEqual(len(specs), 1)
        dumped = specs[0].dumps()
        self.assertNotIn("%PDF", dumped)
        self.assertNotIn("http://", dumped)
        self.assertNotIn("/home/", dumped)
        self.assertNotIn("\\", dumped.replace("\\n", ""))
        return service

    def _deps(self, service) -> ReplyDeliveryDeps:
        return ReplyDeliveryDeps(
            settings=self.settings,
            directory=self.directory,
            services=service,
            document_port=self.document_port,
        )

    def test_webhook_and_text_checks_render_nothing_and_send_renders_once(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        for kind in (
            BotService.FINAL_COST,
            BotService.APPROVED_CUTTING_PLAN,
            BotService.MEASUREMENTS,
        ):
            with self.subTest(kind=kind):
                self.setUp()
                pdf = _Pdf()
                service = self._run(kind, pdf, f"pdf-{kind}")
                original = service.execute

                def execute(request, _original=original):
                    self.assertEqual(pdf.calls, [])
                    return _original(request)

                service.execute = execute
                deliver_pending_replies(
                    self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
                )
                self.assertEqual(len(pdf.calls), 1)
                self.assertEqual(self.document_port.calls, [b"%PDF-once"])
                self.assertEqual(len(self.document_port.captions), 1)
                caption = self.document_port.captions[0]
                self.assertIn("DCO-A", caption)
                self.assertIn("0", caption)
                if kind == BotService.FINAL_COST:
                    self.assertIn("10.00", caption)
                    self.assertIn("USD", caption)
                self.assertFalse(any("10.00" in text for text in self.text_port.calls))

    def test_stop_during_pdf_render_does_not_reach_the_gateway(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        pdf = _Pdf(settings=self.settings, fail="disable")
        service = self._run(BotService.FINAL_COST, pdf, "pdf-stop")
        deliver_pending_replies(
            self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
        )
        self.assertEqual(len(pdf.calls), 1)
        self.assertEqual(self.document_port.calls, [])
        cancelled = [
            row for row in self.sessions.replies.values() if row.status == CANCELLED
        ]
        self.assertTrue(cancelled)

    def test_change_during_render_does_not_send_the_file(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        cases = (
            (BotService.FINAL_COST, _price_snapshot("price-2")),
            (BotService.FINAL_COST, None),
            (BotService.APPROVED_CUTTING_PLAN, _plan_snapshot("plan-2")),
            (BotService.MEASUREMENTS, _measurements_snapshot("measure-2")),
        )
        for kind, changed in cases:
            with self.subTest(kind=kind):
                self.setUp()
                pdf = _Pdf()
                pdf.after_render = changed
                service = self._run(kind, pdf, f"stale-{kind}")
                deliver_pending_replies(
                    self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
                )
                self.assertEqual(len(pdf.calls), 1)
                self.assertEqual(self.document_port.calls, [])
                document_rows = [
                    row
                    for row in self.sessions.replies.values()
                    if row.intent.part_kind == PART_DOCUMENT
                ]
                self.assertTrue(document_rows)
                self.assertTrue(all(row.status == CANCELLED for row in document_rows))
                self.assertTrue(all(row.status != "unknown" for row in document_rows))

    def test_bot_disabled_during_render_cancels_before_the_gateway(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        pdf = _Pdf(self.settings, fail="disable")
        service = self._run(BotService.FINAL_COST, pdf, "disabled-mid-render")
        deliver_pending_replies(
            self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
        )
        self.assertEqual(len(pdf.calls), 1)
        self.assertEqual(self.document_port.calls, [])
        document_row = next(
            row for row in self.sessions.replies.values() if row.intent.part_kind == PART_DOCUMENT
        )
        self.assertEqual(document_row.status, CANCELLED)
        self.assertEqual(document_row.reason_code, "bot_disabled")

    def test_render_failure_is_cancelled_and_not_retried(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        pdf = _Pdf(fail="boom")
        service = self._run(BotService.MEASUREMENTS, pdf, "render-fail")
        deliver_pending_replies(
            self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
        )
        self.assertEqual(len(pdf.calls), 1)
        self.assertEqual(self.document_port.calls, [])
        document_row = next(
            row for row in self.sessions.replies.values() if row.intent.part_kind == PART_DOCUMENT
        )
        self.assertEqual(document_row.status, "accepted")
        self.assertIn(
            "تعذّر تجهيز ملف قياسات هذا الطلب حالياً، يرجى المحاولة لاحقاً أو التواصل مع الموظف.",
            self.text_port.calls,
        )
        self.assertTrue(all("10.00" not in text for text in self.text_port.calls))
        again = deliver_pending_replies(
            self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
        )
        self.assertEqual(self.document_port.calls, [])
        self.assertTrue(all(step.reply_id != document_row.reply_id for step in again))
        self.assertEqual(len(pdf.calls), 1)

    def test_invoice_render_failure_sends_no_amount_and_no_file(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        pdf = _Pdf(fail="boom")
        service = self._run(BotService.FINAL_COST, pdf, "invoice-fail")
        deliver_pending_replies(
            self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
        )
        self.assertEqual(self.document_port.calls, [])
        self.assertEqual(self.document_port.captions, [])
        self.assertIn(
            "تعذّر تجهيز فاتورة هذا الطلب حالياً، يرجى المحاولة لاحقاً أو التواصل مع الموظف.",
            self.text_port.calls,
        )
        self.assertTrue(all("10.00" not in text and "USD" not in text for text in self.text_port.calls))
        self.assertEqual(len(pdf.calls), 1)

    @unittest.skipUnless(_chromium_executable(), "site chromium headless_shell is not present")
    def test_real_chromium_is_idle_during_receipt_and_runs_once_on_send(self) -> None:
        from almdina_erp.tests.test_customer_bot_inbound_session import NOW

        pdf = _ChromiumPdf()
        service = self._run(BotService.FINAL_COST, pdf, "real-chromium")
        deliver_pending_replies(
            self.sessions, self.text_port, deps=self._deps(service), now=NOW, limit=12
        )
        self.assertEqual(len(pdf.calls), 1)
        self.assertEqual(len(self.document_port.calls), 1)
        content = self.document_port.calls[0]
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 500)


if __name__ == "__main__":
    unittest.main()
