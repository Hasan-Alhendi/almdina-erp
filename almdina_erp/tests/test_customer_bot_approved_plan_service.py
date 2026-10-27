"""Unit contracts for the approved cutting-plan customer-bot service."""

from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.customer_bot.approved_plan_service import (
    CustomerBotApprovedPlanService,
    CustomerBotApprovedPlanSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerServiceRequest,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)


REQUEST = CustomerServiceRequest(
    phone="+963988100101",
    service_id=BotService.APPROVED_CUTTING_PLAN,
    order_name="DCO-2026-00021",
)


def _snapshot(
    *,
    plan_name: str = "CP-2026-00021-1",
    revision: int = 1,
    source_type: str = "System",
    consistency_key: str = "same",
) -> CustomerBotApprovedPlanSnapshot:
    return CustomerBotApprovedPlanSnapshot(
        available=True,
        plan_name=plan_name,
        revision=revision,
        source_type=source_type,
        consistency_key=consistency_key,
    )


class _Reader:
    def __init__(self, *snapshots: CustomerBotApprovedPlanSnapshot | None) -> None:
        self.snapshots = list(snapshots)
        self.calls: list[tuple[str, str]] = []

    def read(self, phone: str, order_name: str):
        self.calls.append((phone, order_name))
        if not self.snapshots:
            raise AssertionError("the test did not provide a snapshot")
        return self.snapshots.pop(0)


class _Pdf:
    def __init__(self, content: bytes = b"%PDF-plan") -> None:
        self.content = content
        self.calls: list[tuple[str, str]] = []

    def render(self, order_name: str, plan_name: str) -> bytes:
        self.calls.append((order_name, plan_name))
        return self.content


class CustomerBotApprovedPlanServiceTests(unittest.TestCase):
    def test_approved_system_plan_returns_a_neutral_pdf_document(self) -> None:
        reader = _Reader(_snapshot(), _snapshot())
        pdf = _Pdf()

        described = CustomerBotApprovedPlanService(reader, pdf).execute(REQUEST)
        self.assertEqual(described.code, ServiceResultCode.PLAN_READY)
        self.assertEqual(pdf.calls, [])
        self.assertIsNone(described.documents[0].content)

        renderer = _Reader(_snapshot(), _snapshot())
        result = CustomerBotApprovedPlanService(renderer, pdf).materialize(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.PLAN_READY)
        self.assertEqual(pdf.calls, [("DCO-2026-00021", "CP-2026-00021-1")])
        self.assertEqual(len(result.documents), 1)
        document = result.documents[0]
        self.assertEqual(document.document_type, "approved_cutting_plan")
        self.assertEqual(document.filename, "خطة-قص-DCO-2026-00021-rev-1.pdf")
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertEqual(document.content, b"%PDF-plan")

    def test_approved_uploaded_plan_keeps_the_uploaded_plan_identity(self) -> None:
        reader = _Reader(
            _snapshot(source_type="Uploaded DXF", plan_name="CP-UPLOAD-1"),
            _snapshot(source_type="Uploaded DXF", plan_name="CP-UPLOAD-1"),
        )
        pdf = _Pdf()

        result = CustomerBotApprovedPlanService(reader, pdf).materialize(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.PLAN_READY)
        self.assertEqual(pdf.calls, [("DCO-2026-00021", "CP-UPLOAD-1")])

    def test_missing_or_invalid_plan_never_calls_pdf(self) -> None:
        for snapshot in (None, CustomerBotApprovedPlanSnapshot(available=False)):
            reader = _Reader(snapshot)
            pdf = _Pdf()

            result = CustomerBotApprovedPlanService(reader, pdf).execute(REQUEST)

            self.assertEqual(result.code, ServiceResultCode.PLAN_UNAVAILABLE)
            self.assertEqual(pdf.calls, [])
            self.assertEqual(result.documents, ())

    def test_cancelled_order_never_calls_pdf(self) -> None:
        reader = _Reader(CustomerBotApprovedPlanSnapshot(available=False, cancelled=True))
        pdf = _Pdf()

        result = CustomerBotApprovedPlanService(reader, pdf).execute(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.PLAN_UNAVAILABLE)
        self.assertEqual(pdf.calls, [])

    def test_plan_change_discards_generated_pdf(self) -> None:
        reader = _Reader(
            _snapshot(consistency_key="before"),
            _snapshot(revision=2, consistency_key="after"),
        )
        pdf = _Pdf()

        result = CustomerBotApprovedPlanService(reader, pdf).materialize(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.PLAN_DATA_CHANGED)
        self.assertEqual(len(pdf.calls), 1)
        self.assertEqual(result.documents, ())

    def test_pdf_failure_does_not_return_success(self) -> None:
        reader = _Reader(_snapshot())
        pdf = _Pdf(content=b"")

        result = CustomerBotApprovedPlanService(reader, pdf).materialize(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.PLAN_PDF_FAILED)
        self.assertEqual(result.documents, ())
        self.assertEqual(len(reader.calls), 1)

    def test_other_services_are_not_read(self) -> None:
        reader = _Reader(_snapshot())
        pdf = _Pdf()
        request = CustomerServiceRequest(
            phone=REQUEST.phone,
            service_id=BotService.FINAL_COST,
            order_name=REQUEST.order_name,
        )

        result = CustomerBotApprovedPlanService(reader, pdf).execute(request)

        self.assertEqual(result.code, ServiceResultCode.UNAVAILABLE)
        self.assertEqual(reader.calls, [])
        self.assertEqual(pdf.calls, [])
