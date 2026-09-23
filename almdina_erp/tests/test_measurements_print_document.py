from __future__ import annotations

from pathlib import Path
import unittest

from almdina_erp.almdina_erp.infrastructure.printing.measurements_print_document import (
    customer_invoice_print_html,
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


def _sample_order() -> dict[str, object]:
    return {
        "name": "26-00089",
        "customer": "زبون <تجريبي>",
        "order_date": "2026-09-23",
        "board_description": "لوح أبيض",
        "edge_color": "أسود",
        "order_cutting_machine": "CNC",
        "order_notes": "تسليم بعد الظهر",
        "pieces": [
            {
                "piece_type": "Extra",
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
        )

        self.assertIn("جدول قياسات الطلب", html)
        self.assertIn("جدول القياسات", html)
        self.assertIn("26-00089", html)
        self.assertIn("shared-info-phone", html)
        self.assertIn("0944123456", html)
        self.assertIn("آلة القص", html)
        self.assertIn("CNC", html)
        self.assertIn("القشاط المخصص", html)
        self.assertIn("PVC 1mm", html)
        self.assertIn("مخصص", html)
        self.assertIn("إضافات: Liner", html)
        self.assertIn("مقبض", html)
        self.assertIn("تسليم بعد الظهر", html)
        self.assertIn("dco-piece-sketch", html)
        self.assertIn("زبون &lt;تجريبي&gt;", html)
        self.assertNotIn("زبون <تجريبي>", html)
        self.assertNotIn("quote-details", html)
        self.assertNotIn("فاتورة الزبون", html)
        self.assertNotIn("سعر الوحدة", html)
        self.assertNotIn("default_edge_type", html)
        self.assertNotIn("نوع القشاط", html)

    def test_selected_edge_without_override_is_not_custom(self) -> None:
        html = measurements_print_html(
            {
                "name": "26-00090",
                "pieces": [
                    {
                        "piece_type": "Regular",
                        "width_cm": 40,
                        "length_cm": 80,
                        "qty": 1,
                        "edge_long_right": 1,
                    }
                ],
            }
        )
        self.assertIn('class="custom-edge-empty"', html)
        self.assertNotIn('class="custom-edge-summary"', html)

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
                        piece_type="Extra",
                        width_cm=80,
                        length_cm=210,
                        qty=1,
                        extra_liner=1,
                    )
                ],
            )
        )
        html = measurements_print_html(payload)
        self.assertEqual(payload["name"], "26-00089")
        self.assertEqual(payload["pieces"][0]["extra_liner"], 1)
        self.assertIn("إضافات: Liner", html)

    def test_builder_stays_frappe_free(self) -> None:
        source = PRINT_DOCUMENT.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)

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
        self.assertIn('title: "جدول قياسات الطلب"', presenter)
        self.assertIn("<b>آلة القص</b>", presenter)
        self.assertIn("shared-info-phone", presenter)


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
                        "note": "",
                    }
                ],
                "totals": [{"label": "الإجمالي النهائي", "value_usd": 25}],
            },
            identity={"print_factory_name": "مجمع المدينة المنورة التجاري"},
            customer_phone="0944123456",
            printed_on="2026-09-23 10:00:00",
        )
        self.assertIn("فاتورة الزبون الطلب", html)
        self.assertIn("جدول قياسات الطلب", html)
        self.assertIn("جدول القياسات", html)
        self.assertIn("quote-details", html)
        self.assertIn("تفاصيل عرض السعر", html)
        self.assertIn("ألواح MDF — لوح أبيض", html)
        self.assertIn("سعر الوحدة $", html)
        self.assertIn("25.00", html)
        self.assertIn("0944123456", html)
        self.assertNotIn("cost_breakdown", html)
        self.assertNotIn("special_prices", html)
        self.assertNotIn("زبون <تجريبي>", html)

    def test_invoice_builder_stays_frappe_free(self) -> None:
        source = PRINT_DOCUMENT.read_text(encoding="utf-8")
        self.assertIn("def customer_invoice_print_html", source)
        self.assertNotIn("import frappe", source)


if __name__ == "__main__":
    unittest.main()
