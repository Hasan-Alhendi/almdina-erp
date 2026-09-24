from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.whatsapp.message_templates import (
    DOCUMENT_CAPTION_MAX_LENGTH,
    INVOICE_TEXT_TEMPLATE,
    MEASUREMENT_AMENDMENTS_TEXT_TEMPLATE,
    MEASUREMENTS_TEXT_TEMPLATE,
    STAGE_COMPLETION_TEXT_TEMPLATE,
    DocumentCaptionError,
    document_caption,
    format_whatsapp_preamble,
)

SETTINGS_SERVICE = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "services"
    / "production_settings_service.py"
)


class WhatsAppMessageTemplateTests(unittest.TestCase):
    def test_settings_service_persists_templates_to_tab_singles_after_save(self) -> None:
        source = SETTINGS_SERVICE.read_text(encoding="utf-8")
        update = source.split("def update_production_settings", 1)[1].split(
            "def get_factory_settings_audit", 1
        )[0]
        self.assertIn("settings.save(ignore_permissions=True)", update)
        self.assertIn("_persist_whatsapp_message_singles(settings, payload)", update)
        self.assertLess(
            update.index("settings.save(ignore_permissions=True)"),
            update.index("_persist_whatsapp_message_singles(settings, payload)"),
        )
        self.assertIn("def _write_single_text(", source)
        self.assertIn("def _single_text(", source)
        values_fn = source.split("def _whatsapp_message_values", 1)[1].split(
            "def whatsapp_message_templates", 1
        )[0]
        self.assertIn("_single_text(fieldname)", values_fn)

    def test_default_copy_inserts_the_order_name(self) -> None:
        self.assertEqual(
            format_whatsapp_preamble(None, "26-00089"),
            "نرفق لك جدول القياسات الخاص بطلبك رقم 26-00089",
        )
        self.assertEqual(INVOICE_TEXT_TEMPLATE, MEASUREMENTS_TEXT_TEMPLATE)
        self.assertEqual(
            format_whatsapp_preamble(MEASUREMENT_AMENDMENTS_TEXT_TEMPLATE, "26-00089"),
            "نرفق لك تعديلات القياسات الخاصة بطلبك رقم 26-00089",
        )

    def test_empty_template_falls_back_to_default(self) -> None:
        self.assertEqual(
            format_whatsapp_preamble("   ", "DCO-1", "ملف {order_name}"),
            "ملف DCO-1",
        )

    def test_stage_completion_template_inserts_order_and_stage(self) -> None:
        self.assertEqual(
            format_whatsapp_preamble(
                STAGE_COMPLETION_TEXT_TEMPLATE,
                "26-00089",
                stage_label="CNC",
            ),
            "طلبك رقم 26-00089 اكتملت مرحلة CNC",
        )

    def test_document_caption_rejects_text_over_the_whatsapp_limit(self) -> None:
        self.assertEqual(document_caption("  جاهز  "), "جاهز")
        with self.assertRaises(DocumentCaptionError) as raised:
            document_caption("م" * (DOCUMENT_CAPTION_MAX_LENGTH + 1))
        self.assertEqual(raised.exception.code, "caption_too_long")

    def test_custom_template_keeps_extra_braces(self) -> None:
        self.assertEqual(
            format_whatsapp_preamble(
                "طلب {order_name} — {extra}",
                "26-00089",
            ),
            "طلب 26-00089 — {extra}",
        )


if __name__ == "__main__":
    unittest.main()
