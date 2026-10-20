"""Unit contract for customer-bot option 2."""

from __future__ import annotations

from decimal import Decimal
import unittest

from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerServiceRequest,
)
from almdina_erp.almdina_erp.application.customer_bot.final_price_service import (
    CustomerBotFinalPriceService,
    CustomerBotFinalPriceSnapshot,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)


REQUEST = CustomerServiceRequest(
    phone="+963988100101",
    service_id=BotService.FINAL_COST,
    order_name="DCO-2026-00021",
)


def _snapshot(
    *,
    key: str = "approval-1:fingerprint-1",
    amount: str = "125.00",
    currency: str = "USD",
) -> CustomerBotFinalPriceSnapshot:
    return CustomerBotFinalPriceSnapshot(
        available=True,
        amount=Decimal(amount),
        currency=currency,
        invoice_payload={
            "kind": "customer_invoice",
            "totals": [{"label": "الإجمالي النهائي", "value_usd": Decimal(amount)}],
        },
        consistency_key=key,
    )


class _Reader:
    def __init__(self, *snapshots: CustomerBotFinalPriceSnapshot | None) -> None:
        self.snapshots = list(snapshots)
        self.calls: list[tuple[str, str]] = []

    def read(self, phone: str, order_name: str) -> CustomerBotFinalPriceSnapshot | None:
        self.calls.append((phone, order_name))
        if not self.snapshots:
            return None
        return self.snapshots.pop(0)


class _Pdf:
    def __init__(self, content: bytes = b"%PDF-1.7\n") -> None:
        self.content = content
        self.calls: list[tuple[str, dict]] = []

    def render(self, order_name: str, invoice_payload: dict) -> bytes:
        self.calls.append((order_name, invoice_payload))
        return self.content


class CustomerBotFinalPriceServiceTests(unittest.TestCase):
    def test_approved_price_and_pdf_are_one_customer_invoice_result(self) -> None:
        reader = _Reader(_snapshot(), _snapshot())
        pdf = _Pdf()
        result = CustomerBotFinalPriceService(reader, pdf).execute(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.READY)
        self.assertEqual(result.amount, Decimal("125.00"))
        self.assertEqual(result.currency, "USD")
        self.assertEqual(len(result.documents), 1)
        document = result.documents[0]
        self.assertEqual(document.document_type, "customer_invoice")
        self.assertEqual(document.filename, "فاتورة-DCO-2026-00021.pdf")
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertTrue(document.content.startswith(b"%PDF"))
        self.assertEqual(pdf.calls[0][1]["totals"][0]["value_usd"], result.amount)
        self.assertEqual(reader.calls, [
            (REQUEST.phone, REQUEST.order_name),
            (REQUEST.phone, REQUEST.order_name),
        ])

    def test_unapproved_or_invalidated_price_never_reads_pdf(self) -> None:
        for snapshot in (None, CustomerBotFinalPriceSnapshot(available=False)):
            pdf = _Pdf()
            result = CustomerBotFinalPriceService(_Reader(snapshot), pdf).execute(REQUEST)
            self.assertEqual(result.code, ServiceResultCode.PRICE_UNAVAILABLE)
            self.assertEqual(pdf.calls, [])

    def test_cancelled_order_is_not_a_financial_read(self) -> None:
        reader = _Reader(CustomerBotFinalPriceSnapshot(available=False, cancelled=True))
        pdf = _Pdf()
        result = CustomerBotFinalPriceService(reader, pdf).execute(REQUEST)
        self.assertEqual(result.code, ServiceResultCode.PRICE_UNAVAILABLE)
        self.assertEqual(pdf.calls, [])

    def test_delivered_order_is_allowed_when_approval_is_current(self) -> None:
        reader = _Reader(_snapshot(), _snapshot())
        result = CustomerBotFinalPriceService(reader, _Pdf()).execute(REQUEST)
        self.assertEqual(result.code, ServiceResultCode.READY)

    def test_foreign_and_missing_orders_have_the_same_safe_result(self) -> None:
        for reader in (_Reader(None), _Reader(CustomerBotFinalPriceSnapshot(available=False))):
            result = CustomerBotFinalPriceService(reader, _Pdf()).execute(REQUEST)
            self.assertEqual(result.code, ServiceResultCode.PRICE_UNAVAILABLE)
            self.assertIsNone(result.amount)
            self.assertEqual(result.documents, ())

    def test_phone_or_approval_change_discards_the_generated_pdf(self) -> None:
        reader = _Reader(_snapshot(), _snapshot(key="approval-2:fingerprint-2"))
        pdf = _Pdf()
        result = CustomerBotFinalPriceService(reader, pdf).execute(REQUEST)
        self.assertEqual(result.code, ServiceResultCode.PRICE_DATA_CHANGED)
        self.assertEqual(result.documents, ())

    def test_pdf_failure_does_not_return_a_price_only_success(self) -> None:
        reader = _Reader(_snapshot())
        result = CustomerBotFinalPriceService(reader, _Pdf(b"")).execute(REQUEST)
        self.assertEqual(result.code, ServiceResultCode.INVOICE_FAILED)
        self.assertIsNone(result.amount)
        self.assertEqual(result.documents, ())

    def test_other_services_remain_unavailable_without_a_read(self) -> None:
        reader = _Reader(_snapshot())
        pdf = _Pdf()
        request = CustomerServiceRequest(
            phone=REQUEST.phone,
            service_id=BotService.APPROVED_CUTTING_PLAN,
            order_name=REQUEST.order_name,
        )
        result = CustomerBotFinalPriceService(reader, pdf).execute(request)
        self.assertEqual(result.code, ServiceResultCode.UNAVAILABLE)
        self.assertEqual(reader.calls, [])
        self.assertEqual(pdf.calls, [])


if __name__ == "__main__":
    unittest.main()
