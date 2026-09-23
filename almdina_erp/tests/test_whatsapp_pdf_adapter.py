from __future__ import annotations

import unittest

from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppError
from almdina_erp.almdina_erp.infrastructure.whatsapp.measurement_pdf import (
    PDF_FAILED_MESSAGE,
    html_to_pdf_bytes,
    html_to_pdf_via_chromium,
)


class MeasurementPdfAdapterTests(unittest.TestCase):
    def test_chromium_print_to_pdf_uses_headless_shell(self) -> None:
        captured: list[list[str]] = []

        def runner(args: list[str], **_kwargs: object) -> SimpleNamespace:
            captured.append(args)
            pdf_arg = next(item for item in args if str(item).startswith("--print-to-pdf="))
            Path(str(pdf_arg).split("=", 1)[1]).write_bytes(b"%PDF-1.4\n")
            return SimpleNamespace(returncode=0)

        pdf = html_to_pdf_via_chromium(
            "<html><body>قياسات</body></html>",
            chromium_path="/tmp/headless_shell",
            runner=runner,
        )
        self.assertEqual(pdf, b"%PDF-1.4\n")
        self.assertEqual(captured[0][0], "/tmp/headless_shell")
        self.assertIn("--headless", captured[0])
        self.assertTrue(any(str(item).startswith("--print-to-pdf=") for item in captured[0]))

    def test_chromium_print_rejects_empty_html(self) -> None:
        with self.assertRaises(WhatsAppError) as raised:
            html_to_pdf_via_chromium("  ", chromium_path="/tmp/headless_shell")
        self.assertEqual(raised.exception.code, "pdf_failed")

    def test_html_pdf_prefers_chromium(self) -> None:
        def runner(args: list[str], **_kwargs: object) -> SimpleNamespace:
            pdf_arg = next(item for item in args if str(item).startswith("--print-to-pdf="))
            Path(str(pdf_arg).split("=", 1)[1]).write_bytes(b"%PDF-chrome")
            return SimpleNamespace(returncode=0)

        def fallback(_html: str) -> bytes:
            raise AssertionError("fallback should not run when chromium succeeds")

        pdf = html_to_pdf_bytes(
            "<html><body>قياسات</body></html>",
            chromium_path="/tmp/headless_shell",
            runner=runner,
            fallback=fallback,
        )
        self.assertEqual(pdf, b"%PDF-chrome")

    def test_html_pdf_falls_back_when_chromium_fails(self) -> None:
        def runner(*_args: object, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(returncode=1)

        pdf = html_to_pdf_bytes(
            "<html><body>قياسات</body></html>",
            chromium_path="/tmp/headless_shell",
            runner=runner,
            fallback=lambda _html: b"%PDF-fallback",
        )
        self.assertEqual(pdf, b"%PDF-fallback")

    def test_html_pdf_maps_missing_engines_to_arabic_error(self) -> None:
        def runner(*_args: object, **_kwargs: object) -> SimpleNamespace:
            raise OSError("chromium missing")

        def fallback(_html: str) -> bytes:
            raise OSError('No wkhtmltopdf executable found: "b\'\'"')

        with self.assertRaises(WhatsAppError) as raised:
            html_to_pdf_bytes(
                "<html><body>قياسات</body></html>",
                chromium_path="/tmp/headless_shell",
                runner=runner,
                fallback=fallback,
            )
        self.assertEqual(raised.exception.code, "pdf_failed")
        self.assertEqual(str(raised.exception), PDF_FAILED_MESSAGE)

    def test_html_pdf_rejects_empty_markup(self) -> None:
        with self.assertRaises(WhatsAppError) as raised:
            html_to_pdf_bytes("  ", fallback=lambda _html: b"%PDF-nope")
        self.assertEqual(raised.exception.code, "pdf_failed")


if __name__ == "__main__":
    unittest.main()
