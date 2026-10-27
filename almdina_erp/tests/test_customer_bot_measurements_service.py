"""Unit contracts for the order-measurements customer-bot service."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerServiceRequest,
    CustomerServiceResult,
)
from almdina_erp.almdina_erp.application.customer_bot.measurements_service import (
    CustomerBotMeasurementsService,
    CustomerBotMeasurementsSnapshot,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_measurements_pdf import (
    _print_measurements_html,
)
from almdina_erp.almdina_erp.infrastructure.printing.measurements_print_document import (
    measurements_print_html,
    order_print_payload,
)


REQUEST = CustomerServiceRequest(
    phone="+963988100101",
    service_id=BotService.MEASUREMENTS,
    order_name="DCO-2026-00021",
)
ROOT = Path(__file__).resolve().parents[1]


def _ready(key: str = "same") -> CustomerBotMeasurementsSnapshot:
    return CustomerBotMeasurementsSnapshot(
        available=True,
        order_name="DCO-2026-00021",
        consistency_key=key,
    )


class _Reader:
    def __init__(self, snapshots: list[CustomerBotMeasurementsSnapshot | None]) -> None:
        self.snapshots = list(snapshots)
        self.calls: list[tuple[str, str]] = []

    def read(self, phone: str, order_name: str):
        self.calls.append((phone, order_name))
        return self.snapshots.pop(0)


class _Pdf:
    def __init__(self, content: bytes | Exception = b"%PDF-1.4\n") -> None:
        self.content = content
        self.calls: list[tuple[str, str]] = []

    def render(self, phone: str, order_name: str) -> bytes:
        self.calls.append((phone, order_name))
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


class CustomerBotMeasurementsServiceTests(unittest.TestCase):
    def test_saved_measurements_return_one_document_without_price(self) -> None:
        reader = _Reader([_ready(), _ready()])
        pdf = _Pdf()
        described = CustomerBotMeasurementsService(reader, pdf).execute(REQUEST)
        self.assertEqual(described.code, ServiceResultCode.MEASUREMENTS_READY)
        self.assertIsNone(described.documents[0].content)
        self.assertEqual(pdf.calls, [])

        renderer = _Reader([_ready(), _ready()])
        result = CustomerBotMeasurementsService(renderer, pdf).materialize(REQUEST)

        self.assertEqual(result.code, ServiceResultCode.MEASUREMENTS_READY)
        self.assertIsNone(result.amount)
        self.assertIsNone(result.currency)
        self.assertEqual(len(result.documents), 1)
        document = result.documents[0]
        self.assertEqual(document.document_type, "order_measurements")
        self.assertEqual(document.mime_type, "application/pdf")
        self.assertEqual(document.filename, "قياسات-DCO-2026-00021.pdf")
        self.assertEqual(document.content, b"%PDF-1.4\n")
        self.assertEqual(pdf.calls, [(REQUEST.phone, REQUEST.order_name)])
        self.assertEqual(renderer.calls, [pdf.calls[0], pdf.calls[0]])

    def test_other_services_stay_unavailable_on_this_port(self) -> None:
        pdf = _Pdf()
        result = CustomerBotMeasurementsService(_Reader([]), pdf).execute(
            CustomerServiceRequest(
                phone=REQUEST.phone,
                service_id=BotService.FINAL_COST,
                order_name=REQUEST.order_name,
            )
        )
        self.assertEqual(result.code, ServiceResultCode.UNAVAILABLE)
        self.assertEqual(pdf.calls, [])

    def test_missing_cancelled_and_empty_measurements_do_not_render(self) -> None:
        for snapshot in (
            None,
            CustomerBotMeasurementsSnapshot(available=False, cancelled=True),
            CustomerBotMeasurementsSnapshot(available=False),
        ):
            pdf = _Pdf()
            result = CustomerBotMeasurementsService(_Reader([snapshot]), pdf).execute(REQUEST)
            self.assertEqual(result.code, ServiceResultCode.MEASUREMENTS_UNAVAILABLE)
            self.assertEqual(result.documents, ())
            self.assertEqual(pdf.calls, [])

    def test_changed_measurements_or_ownership_discard_the_rendered_file(self) -> None:
        cases = (
            [_ready("before"), _ready("after")],
            [_ready(), None],
            [_ready(), CustomerBotMeasurementsSnapshot(available=False, cancelled=True)],
        )
        for snapshots in cases:
            pdf = _Pdf(b"%PDF-stale")
            result = CustomerBotMeasurementsService(_Reader(snapshots), pdf).materialize(REQUEST)
            self.assertEqual(result.code, ServiceResultCode.MEASUREMENTS_DATA_CHANGED)
            self.assertEqual(result.documents, ())
            self.assertEqual(pdf.calls, [(REQUEST.phone, REQUEST.order_name)])

    def test_renderer_failure_and_invalid_bytes_are_not_success(self) -> None:
        for content in (RuntimeError("pdf"), b"", b"not-a-pdf"):
            result = CustomerBotMeasurementsService(_Reader([_ready()]), _Pdf(content)).materialize(
                REQUEST
            )
            self.assertEqual(result.code, ServiceResultCode.MEASUREMENTS_PDF_FAILED)
            self.assertEqual(result.documents, ())

    def test_projection_keeps_measurement_rows_and_drops_internal_prices(self) -> None:
        payload = order_print_payload(
            {
                "name": "DCO-2026-00021",
                "customer": "CUST-A",
                "order_notes": "ملاحظة الزبون",
                "important_note_comment": "INTERNAL-NOTE-9941",
                "owner": "employee@example.com",
                "total_cost_usd": 98765.43,
                "pieces": [
                    {
                        "piece_type": "Special",
                        "width_cm": 41.5,
                        "length_cm": 92,
                        "qty": 2,
                        "notes": "مقبض",
                        "extra_double": 1,
                        "edge_long_right": 1,
                        "edge_long_right_type_override": "EDGE-GOLD",
                        "extra_double_unit_price_usd": 98765.43,
                        "margin_percent": 40,
                    }
                ],
            }
        )
        html = measurements_print_html(
            payload,
            language="ar",
            translator=lambda message: message,
            customer_phone="0988000111",
        )
        self.assertIn("41.5", html)
        self.assertIn("92", html)
        self.assertIn("ملاحظة الزبون", html)
        self.assertIn("Add-ons: Double Edge", html)
        self.assertIn("EDGE-GOLD", html)
        for hidden in (
            "98765.43",
            "INTERNAL-NOTE-9941",
            "employee@example.com",
            "margin_percent",
            "Unit price",
        ):
            self.assertNotIn(hidden, html)

    def test_temporary_files_are_removed_after_success_and_failure(self) -> None:
        seen: list[Path] = []

        def succeed(command, **_kwargs):
            pdf = Path(next(part.split("=", 1)[1] for part in command if part.startswith("--print-to-pdf=")))
            pdf.write_bytes(b"%PDF-1.4\n")
            seen.append(pdf.parent)
            return SimpleNamespace(returncode=0)

        content = _print_measurements_html("<html></html>", executable="/bin/true", runner=succeed)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertFalse(seen[0].exists())

        def fail(command, **_kwargs):
            pdf = Path(next(part.split("=", 1)[1] for part in command if part.startswith("--print-to-pdf=")))
            seen.append(pdf.parent)
            return SimpleNamespace(returncode=1)

        with self.assertRaises(ValueError):
            _print_measurements_html("<html></html>", executable="/bin/true", runner=fail)
        self.assertFalse(seen[1].exists())

    def test_print_keeps_dimension_cells_as_table_cells(self) -> None:
        from urllib.parse import unquote, urlparse

        captured: dict[str, str] = {}

        def capture(command, **_kwargs):
            captured["html"] = Path(unquote(urlparse(command[-1]).path)).read_text(encoding="utf-8")
            pdf = Path(next(part.split("=", 1)[1] for part in command if part.startswith("--print-to-pdf=")))
            pdf.write_bytes(b"%PDF-1.4\n")
            return SimpleNamespace(returncode=0)

        _print_measurements_html(
            '<head><style>.ltr{display:inline-block}</style></head><td class="ltr">45</td>',
            executable="/bin/true",
            runner=capture,
        )
        self.assertLess(
            captured["html"].find(".ltr{display:inline-block}"),
            captured["html"].find("td.ltr{display:table-cell}"),
        )
        self.assertIn(">45<", captured["html"])

    def test_reader_and_adapter_do_not_use_retired_grants_or_send_paths(self) -> None:
        reader = (
            ROOT / "almdina_erp" / "infrastructure" / "frappe" / "customer_bot_measurements_reader.py"
        ).read_text(encoding="utf-8")
        adapter = (
            ROOT / "almdina_erp" / "infrastructure" / "frappe" / "customer_bot_measurements_pdf.py"
        ).read_text(encoding="utf-8")
        service = (
            ROOT / "almdina_erp" / "application" / "customer_bot" / "measurements_service.py"
        ).read_text(encoding="utf-8")
        for source in (reader, adapter, service):
            self.assertNotIn("Customer Bot Phone Access", source)
            self.assertNotIn("infrastructure.whatsapp", source)
            self.assertNotIn("import whatsapp", source.lower())
            self.assertNotIn("set_value", source)
            self.assertNotIn("recalculate_", source)
            self.assertNotIn(".save(", source)
            self.assertNotIn("for_update", source)
        self.assertNotIn("import frappe", service)
        self.assertIn("resolve_customer_identity", reader)
        self.assertNotIn("get_doc", reader)
        self.assertNotIn("get_pdf", adapter)
        self.assertNotIn("send_document", adapter)
        self.assertIn("measurements_print_html", adapter)
        whatsapp = (
            ROOT / "almdina_erp" / "infrastructure" / "whatsapp" / "frappe_adapters.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def render_measurements_pdf", whatsapp)
        self.assertIn("order_print_payload", whatsapp)


class CustomerServiceResultTests(unittest.TestCase):
    def test_measurements_ready_rejects_price_fields(self) -> None:
        with self.assertRaises(ValueError):
            CustomerServiceResult(
                ServiceResultCode.MEASUREMENTS_READY,
                amount=1,
            )
