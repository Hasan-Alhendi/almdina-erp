from __future__ import annotations

from pathlib import Path
import unittest

from almdina_erp.almdina_erp.infrastructure.printing.measurements_print_document import (
    customer_invoice_print_html,
    document_locale,
    measurements_print_html,
    order_print_payload,
)


ROOT = Path(__file__).resolve().parents[1]
PRINT_DOCUMENT = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "printing"
    / "measurements_print_document.py"
)
ADAPTER = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "whatsapp"
    / "frappe_adapters.py"
)
PRESENTER = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_presenter.js"
)


def _identity_translator(message: str, replacements=None) -> str:
    text = message
    if replacements:
        text = text.replace("{0}", str(replacements[0]))
    return text


_ARABIC_LABELS = {
    "Custom": "مخصص",
    "Add-ons": "إضافات",
    "Liner": "لاينر",
    "Back groove": "فرزة ظهر",
    "Order measurements table": "جدول قياسات الطلب",
    "Measurements table": "جدول القياسات",
    "Exceptional customization": "تخصيص استثنائي",
    "Length": "الطول",
    "Width": "العرض",
    "cm": "سم",
    "Default type": "النوع الافتراضي",
}


def _arabic_translator(message: str, replacements=None) -> str:
    text = _ARABIC_LABELS.get(message, message)
    if replacements:
        text = text.replace("{0}", str(replacements[0]))
    return text


def _sample_order() -> dict[str, object]:
    return {
        "name": "26-00089",
        "customer": "زبون <تجريبي>",
        "order_date": "2026-09-23",
        "board_description": "لوح أبيض",
        "board_length_cm": 244,
        "board_width_cm": 122.5,
        "edge_color": "أسود",
        "default_edge_type": "PVC 0.8",
        "order_cutting_machine": "CNC",
        "order_notes": "تسليم بعد الظهر",
        "pieces": [
            {
                "piece_type": "Special",
                "width_cm": 80,
                "length_cm": 210,
                "qty": 2,
                "notes": "مقبض",
                "edge_width_top": 1,
                "edge_width_top_type_override": "PVC 1mm",
                "extra_liner": 1,
                "special_shape_drawing_json": {
                    "schema": "almdina.special-shape-documentation",
                    "version": 1,
                    "canvas": {"widthMm": 800, "heightMm": 2100},
                    "elements": [
                        {
                            "type": "stroke",
                            "points": [{"xMm": 10, "yMm": 10}, {"xMm": 40, "yMm": 80}],
                            "style": {"color": "#1463e6"},
                        }
                    ],
                },
            }
        ],
    }


class MeasurementsPrintDocumentTests(unittest.TestCase):
    def test_html_matches_unified_measurements_print_markers(self) -> None:
        html = measurements_print_html(
            _sample_order(),
            identity={"print_factory_name": "مجمع المدينة المنورة التجاري"},
            customer_phone="0944123456",
            printed_on="2026-09-23 10:00:00",
            language="en",
            translator=_identity_translator,
        )

        self.assertIn("Order measurements table", html)
        self.assertIn("Measurements table", html)
        self.assertIn('lang="en"', html)
        self.assertIn('dir="ltr"', html)
        self.assertIn("direction:ltr", html)
        self.assertIn("26-00089", html)
        self.assertIn("shared-info-phone", html)
        self.assertIn("0944123456", html)
        self.assertIn("Cutting machine", html)
        self.assertIn("CNC", html)
        self.assertIn("Custom edge banding", html)
        self.assertIn("PVC 1mm", html)
        self.assertIn("Add-ons: Liner", html)
        self.assertIn("مقبض", html)
        self.assertIn("تسليم بعد الظهر", html)
        self.assertIn("dco-piece-sketch", html)
        self.assertIn('class="ltr"', html)
        self.assertIn("زبون &lt;تجريبي&gt;", html)
        self.assertNotIn("زبون <تجريبي>", html)
        self.assertNotIn("quote-details", html)
        self.assertNotIn("Customer invoice", html)
        self.assertNotIn("سعر الوحدة", html)
        self.assertNotIn("default_edge_type", html)
        self.assertNotIn("نوع القشاط", html)
        self.assertIn('class="shared-info-metric" dir="ltr">244</span>', html)
        self.assertIn('class="shared-info-metric" dir="ltr">122.5</span>', html)
        self.assertIn('class="shared-info-detail-value">PVC 0.8</span>', html)
        self.assertNotIn("244.000", html)
        self.assertNotIn("122.500", html)

    def test_selected_edge_without_override_is_not_custom(self) -> None:
        html = measurements_print_html(
            {
                "name": "26-00090",
                "default_edge_type": "Factory Band",
                "pieces": [
                    {
                        "piece_type": "Regular",
                        "width_cm": 40,
                        "length_cm": 80,
                        "qty": 1,
                        "edge_long_right": 1,
                        "edge_long_right_type_override": "",
                    }
                ],
            },
            language="en",
            translator=_identity_translator,
        )
        self.assertIn('class="custom-edge-empty"', html)
        self.assertNotIn('class="custom-edge-summary"', html)
        self.assertIn('class="shared-info-detail-value">Factory Band</span>', html)
        self.assertEqual(html.count("Factory Band"), 1)

    def test_board_metrics_and_default_edge_follow_stored_order_values(self) -> None:
        order = {
            "name": "26-00091",
            "board_description": "MDF أبيض عالي اللمعان سماكة 18 مم وجهين ميلامين مقاوم للرطوبة",
            "board_length_cm": 244.0,
            "board_width_cm": "122.500",
            "edge_color": "بيج",
            "default_edge_type": 'PVC <أبيض> & "مطبخ"',
            "full_board_length_mm": 3000,
            "full_board_width_mm": 1500,
            "usable_board_length_cm": 243,
            "usable_board_width_cm": 121,
            "pieces": [
                {
                    "piece_type": "Regular",
                    "width_cm": 33,
                    "length_cm": 44,
                    "qty": 1,
                    "edge_width_top": 1,
                    "edge_width_top_type_override": "ABS exception",
                }
            ],
        }

        def translating(message: str) -> str:
            if message == 'PVC <أبيض> & "مطبخ"':
                return "TRANSLATED EDGE"
            return message

        html = measurements_print_html(
            order,
            language="en",
            translator=translating,
        )
        self.assertIn('class="shared-info-metric" dir="ltr">244</span>', html)
        self.assertIn('class="shared-info-metric" dir="ltr">122.5</span>', html)
        self.assertNotIn("244.000", html)
        self.assertNotIn("122.500", html)
        self.assertNotIn("3000", html)
        self.assertNotIn("1500", html)
        self.assertNotIn(">243<", html)
        self.assertNotIn(">121<", html)
        self.assertIn("MDF أبيض عالي اللمعان سماكة 18 مم وجهين ميلامين مقاوم للرطوبة", html)
        self.assertIn('PVC &lt;أبيض&gt; &amp; &quot;مطبخ&quot;', html)
        self.assertNotIn("TRANSLATED EDGE", html)
        self.assertNotIn("<script>", html)
        self.assertIn("<b>ABS exception</b>", html)
        self.assertNotIn('class="shared-info-detail-value">ABS exception</span>', html)

    def test_absent_board_metrics_print_dashes_instead_of_zero(self) -> None:
        html = measurements_print_html(
            {
                "name": "OLD-1",
                "board_description": "لوح قديم",
                "edge_color": "بيج",
                "board_length_cm": None,
                "board_width_cm": " ",
                "default_edge_type": None,
                "full_board_length_mm": 2440,
                "pieces": [],
            },
            language="en",
            translator=_identity_translator,
        )
        self.assertEqual(html.count('class="shared-info-metric" dir="ltr">—</span>'), 2)
        self.assertIn('class="shared-info-detail-value">—</span>', html)
        self.assertNotIn('dir="ltr">0</span>', html)
        self.assertNotIn("2440", html)
        self.assertNotIn(">244<", html)
        self.assertNotIn(">122<", html)

        zero = measurements_print_html(
            {
                "name": "OLD-2",
                "board_length_cm": 0,
                "board_width_cm": 122,
                "pieces": [],
            },
            language="en",
            translator=_identity_translator,
        )
        self.assertIn('class="shared-info-metric" dir="ltr">0</span>', zero)
        self.assertIn('class="shared-info-metric" dir="ltr">122</span>', zero)

    def test_order_print_payload_carries_board_size_and_default_edge(self) -> None:
        payload = order_print_payload(
            {
                "name": "26-00092",
                "board_description": "لوح أبيض",
                "board_length_cm": 244,
                "board_width_cm": 122.5,
                "default_edge_type": "PVC 0.8",
                "full_board_length_mm": 2440,
                "full_board_width_mm": 1220,
                "usable_board_length_cm": 243,
                "pieces": [],
            }
        )
        self.assertEqual(payload["board_length_cm"], 244)
        self.assertEqual(payload["board_width_cm"], 122.5)
        self.assertEqual(payload["default_edge_type"], "PVC 0.8")
        self.assertNotIn("full_board_length_mm", payload)
        self.assertNotIn("full_board_width_mm", payload)
        self.assertNotIn("usable_board_length_cm", payload)

        printed = measurements_print_html(
            payload,
            language="en",
            translator=_identity_translator,
        )
        self.assertIn('dir="ltr">244</span>', printed)
        self.assertIn('dir="ltr">122.5</span>', printed)
        self.assertIn('class="shared-info-detail-value">PVC 0.8</span>', printed)

        missing = order_print_payload({"name": "26-00093", "pieces": []})
        self.assertIsNone(missing["board_length_cm"])
        self.assertIsNone(missing["board_width_cm"])
        self.assertIsNone(missing["default_edge_type"])
        blank = measurements_print_html(
            missing,
            language="en",
            translator=_identity_translator,
        )
        self.assertEqual(blank.count('class="shared-info-metric" dir="ltr">—</span>'), 2)
        self.assertIn('class="shared-info-detail-value">—</span>', blank)
        self.assertNotIn('dir="ltr">0</span>', blank)

    def test_payload_accepts_frappe_dict_attribute_access(self) -> None:
        class SoftDict(dict):
            def __getattr__(self, key):
                try:
                    return self[key]
                except KeyError:
                    return None

        payload = order_print_payload(
            SoftDict(
                name="26-00089",
                customer="زبون",
                pieces=[
                    SoftDict(
                        piece_type="Clipped Corner",
                        width_cm=80,
                        length_cm=210,
                        qty=1,
                        extra_liner=1,
                    )
                ],
            )
        )
        html = measurements_print_html(
            payload,
            language="en",
            translator=_identity_translator,
        )
        self.assertEqual(payload["name"], "26-00089")
        self.assertEqual(payload["pieces"][0]["extra_liner"], 1)
        self.assertIn("Add-ons: Liner", html)

    def test_builder_stays_frappe_free(self) -> None:
        source = PRINT_DOCUMENT.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)

    def test_corner_outlines_print_from_stored_cuts_and_travel_in_the_payload(self) -> None:
        order = _sample_order()
        pieces = order["pieces"]
        assert isinstance(pieces, list)
        pieces.extend([
            {
                "name": "ROW-L",
                "piece_type": "L-Shaped Corner",
                "width_cm": 100,
                "length_cm": 200,
                "qty": 1,
                "notes": "ملاحظة L",
                "extra_liner": 1,
                "rotated": 1,
                "clipped_corner_position": "Top Right",
                "clipped_corner_width_cm": 30,
                "clipped_corner_length_cm": 40,
            },
            {
                "name": "ROW-CLIP",
                "piece_type": "Clipped Corner",
                "width_cm": 50,
                "length_cm": 80,
                "qty": 1,
                "notes": "",
                "clipped_corner_position": "Bottom Left",
                "clipped_corner_width_cm": 10,
                "clipped_corner_length_cm": 15,
            },
            {
                "name": "ROW-MISSING",
                "piece_type": "L-Shaped Corner",
                "width_cm": 90,
                "length_cm": 140,
                "qty": 1,
                "notes": "بدون قص",
                "clipped_corner_position": "Top Left",
            },
        ])
        payload = order_print_payload(order)
        corner = payload["pieces"][1]
        self.assertEqual(corner["clipped_corner_position"], "Top Right")
        self.assertEqual(corner["clipped_corner_width_cm"], 30)
        self.assertEqual(corner["clipped_corner_length_cm"], 40)
        html = measurements_print_html(
            payload,
            language="ar",
            translator=_arabic_translator,
        )
        self.assertIn("70.0,40.0", html)
        self.assertIn("100.0,40.0", html)
        self.assertIn("10.0,80.0", html)
        self.assertIn("0.0,65.0", html)
        self.assertIn('direction="ltr"', html)
        self.assertIn('dir="rtl"', html)
        self.assertIn("notes-with-drawing", html)
        self.assertIn("row-with-drawing", html)
        self.assertIn("ملاحظة L", html)
        self.assertIn("بدون قص", html)
        self.assertIn("Door piece drawing 2", html)
        self.assertIn("Door piece drawing 3", html)
        self.assertEqual(html.count("<polygon "), 2)
        self.assertNotIn("90.0,140.0", html)
        self.assertIn("<path ", html)
        self.assertLess(html.index("<path "), html.index("70.0,40.0"))

    def test_whatsapp_adapter_uses_unified_html_not_print_format(self) -> None:
        adapter = ADAPTER.read_text(encoding="utf-8")
        presenter = PRESENTER.read_text(encoding="utf-8")
        self.assertIn("measurements_print_html", adapter)
        self.assertIn("order_print_payload", adapter)
        self.assertIn("html_to_pdf_bytes", adapter)
        self.assertIn("customer_invoice_print_html", adapter)
        self.assertIn("FrappeInvoicePdfAdapter", adapter)
        self.assertNotIn("get_print", adapter)
        self.assertNotIn("Door Cutting Measurements", adapter)
        self.assertIn('title: __("Order measurements table")', presenter)
        self.assertIn('__("Cutting machine")', presenter)
        self.assertIn("shared-info-phone", presenter)
        self.assertIn("translator=frappe._", adapter)
        self.assertIn('language=getattr(frappe.local, "lang", None) or "ar"', adapter)

    def test_missing_language_or_translator_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "print_language_required"):
            measurements_print_html(_sample_order(), translator=_identity_translator)
        with self.assertRaisesRegex(ValueError, "print_translator_required"):
            measurements_print_html(_sample_order(), language="ar")
        with self.assertRaisesRegex(ValueError, "print_translator_required"):
            customer_invoice_print_html(_sample_order(), language="en")

    def test_print_direction_follows_language_and_measurements_stay_ltr(self) -> None:
        arabic = measurements_print_html(
            _sample_order(),
            language="ar",
            translator=_arabic_translator,
        )
        self.assertIn('lang="ar"', arabic)
        self.assertIn('dir="rtl"', arabic)
        self.assertIn("جدول قياسات الطلب", arabic)
        self.assertIn("إضافات: لاينر", arabic)
        self.assertIn("مقبض", arabic)
        self.assertNotIn("<em>Custom</em>", arabic)
        self.assertIn('class="ltr"', arabic)
        self.assertIn("الطول:", arabic)
        self.assertIn("العرض:", arabic)
        self.assertIn(">سم</span>", arabic)
        self.assertIn("النوع الافتراضي:", arabic)
        self.assertIn('dir="ltr">244</span>', arabic)
        self.assertIn('dir="ltr">122.5</span>', arabic)
        self.assertIn("PVC 0.8", arabic)
        self.assertIn("لوح أبيض", arabic)

        def french(message: str) -> str:
            if message == "Order measurements table":
                return "Table des mesures"
            return message

        translated = measurements_print_html(
            _sample_order(),
            language="fr",
            translator=french,
        )
        self.assertIn('lang="fr"', translated)
        self.assertIn('dir="ltr"', translated)
        self.assertIn("direction:ltr", translated)
        self.assertIn("Table des mesures", translated)
        self.assertIn("80", translated)
        self.assertIn("210", translated)
        self.assertIn('class="ltr"', translated)

    def test_locale_keeps_official_codes_and_rtl_bases(self) -> None:
        self.assertEqual(document_locale("ar"), ("ar", "rtl"))
        self.assertEqual(document_locale("fa"), ("fa", "rtl"))
        self.assertEqual(document_locale("he"), ("he", "rtl"))
        self.assertEqual(document_locale("ps"), ("ps", "rtl"))
        self.assertEqual(document_locale("FA"), ("FA", "rtl"))
        self.assertEqual(document_locale("fr"), ("fr", "ltr"))
        self.assertEqual(document_locale("pt-BR"), ("pt-BR", "ltr"))
        self.assertEqual(document_locale("pt_BR"), ("pt-BR", "ltr"))
        self.assertEqual(document_locale("zh-TW"), ("zh-TW", "ltr"))
        portuguese = measurements_print_html(
            _sample_order(),
            language="pt-BR",
            translator=_identity_translator,
        )
        self.assertIn('lang="pt-BR"', portuguese)
        self.assertIn('dir="ltr"', portuguese)
        self.assertIn("مقبض", portuguese)
        self.assertIn("زبون &lt;تجريبي&gt;", portuguese)

    def test_third_language_translates_custom_and_keeps_user_text(self) -> None:
        order = _sample_order()
        order["pieces"][0]["extra_back_groove"] = 1
        order["pieces"][0]["edge_width_bottom"] = 1
        order["pieces"][0]["edge_width_bottom_type_override"] = "PVC 1mm"

        def third(message: str) -> str:
            return {
                "Custom": "Sur mesure",
                "Door piece drawing {0}": "Dessin {0}",
                "Add-ons": "Options",
                "Liner": "Doublure",
                "Back groove": "Rainure",
                "Top width edge": "Bord haut",
                "Bottom width edge": "Bord bas",
            }.get(message, message)

        html = measurements_print_html(order, language="fr", translator=third)
        self.assertIn('lang="fr"', html)
        self.assertIn('dir="ltr"', html)
        self.assertIn("direction:ltr", html)
        self.assertIn("<em>Sur mesure</em>", html)
        self.assertIn("Dessin 1", html)
        self.assertIn("Options: Doublure, Rainure", html)
        self.assertIn("Bord haut, Bord bas", html)
        self.assertIn("مقبض", html)
        self.assertIn("تسليم بعد الظهر", html)
        self.assertIn("PVC 1mm", html)
        self.assertIn('class="ltr"', html)
        self.assertNotIn("مخصص", html)
        self.assertNotIn("رسمة الدرفة", html)
        self.assertNotIn("،", html)

        arabic = measurements_print_html(
            order,
            language="ar",
            translator=_arabic_translator,
        )
        self.assertIn('lang="ar"', arabic)
        self.assertIn('dir="rtl"', arabic)
        self.assertIn("<em>مخصص</em>", arabic)
        self.assertIn("إضافات: لاينر، فرزة ظهر", arabic)
        self.assertIn("مقبض", arabic)
        self.assertIn("PVC 1mm", arabic)
        self.assertNotIn("<em>Custom</em>", arabic)


class CustomerInvoicePrintDocumentTests(unittest.TestCase):
    def test_html_appends_authorized_quote_to_measurements_document(self) -> None:
        html = customer_invoice_print_html(
            _sample_order(),
            {
                "kind": "customer_invoice",
                "lines": [
                    {
                        "type": "material",
                        "description": "ألواح MDF — لوح أبيض",
                        "quantity": 2,
                        "unit": "لوح",
                        "rate_usd": 12.5,
                        "amount_usd": 25,
                        "note": "ملاحظة السعر",
                    },
                    {
                        "type": "edge",
                        "description": "PVC 1mm",
                        "quantity": 1,
                        "unit": "m",
                        "rate_usd": 1,
                        "amount_usd": 1,
                        "note": "يتضمن أطرافًا مخصصة",
                    },
                    {
                        "type": "edge",
                        "description": "Default edge",
                        "quantity": 1,
                        "unit": "m",
                        "rate_usd": 1,
                        "amount_usd": 1,
                        "note": "من القشاط الافتراضي",
                    },
                ],
                "totals": [{"label": "الإجمالي النهائي", "value_usd": 25}],
            },
            identity={"print_factory_name": "مجمع المدينة المنورة التجاري"},
            customer_phone="0944123456",
            printed_on="2026-09-23 10:00:00",
            language="en",
            translator=_identity_translator,
        )
        self.assertIn("Customer invoice for order", html)
        self.assertIn("Order measurements table", html)
        self.assertIn("Measurements table", html)
        self.assertIn("quote-details", html)
        self.assertIn("Quotation details", html)
        self.assertIn("ألواح MDF — لوح أبيض", html)
        self.assertIn("ملاحظة السعر", html)
        self.assertIn("Exceptional customization", html)
        self.assertNotIn("يتضمن أطرافًا مخصصة", html)
        self.assertNotIn("من القشاط الافتراضي", html)
        self.assertIn("Unit price $", html)
        self.assertIn("25.00", html)
        self.assertIn("0944123456", html)
        self.assertIn('dir="ltr">244</span>', html)
        self.assertIn('dir="ltr">122.5</span>', html)
        self.assertIn('class="shared-info-detail-value">PVC 0.8</span>', html)
        self.assertIn("quote-details", html)
        self.assertNotIn("cost_breakdown", html)
        self.assertNotIn("special_prices", html)
        self.assertNotIn("زبون <تجريبي>", html)

    def test_invoice_builder_stays_frappe_free(self) -> None:
        source = PRINT_DOCUMENT.read_text(encoding="utf-8")
        self.assertIn("def customer_invoice_print_html", source)
        self.assertNotIn("import frappe", source)


if __name__ == "__main__":
    unittest.main()
