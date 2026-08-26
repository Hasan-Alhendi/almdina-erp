from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
    build_internal_cost_report_document,
)


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "application"
    / "costing"
    / "financial_documents.py"
)


class TestFinancialDocumentApplication(unittest.TestCase):
    def setUp(self) -> None:
        self.order = {
            "name": "DCO-TEST-0001",
            "customer": "زبون تجريبي",
            "order_date": "2026-08-01",
            "board_description": "MDF أبيض 18 مم",
            "edge_color": "أبيض",
            "revision": 2,
            "required_boards": 2,
            "board_rate_usd": 20,
            "cutting_cost_per_board_usd": 3,
            "mdf_cost_usd": 40,
            "cutting_cost_usd": 6,
            "edge_cost_usd": 5,
            "total_cost_usd": 51,
            "customer_quote_total_usd": 80,
            "customer_quote_status": "Approved",
            "material_variance_cost_usd": 2,
            "internal_loss_cost_usd": 1,
            "actual_cost_usd": 54,
            "total_area_m2": 4.2,
            "total_edge_meters": 12,
            "waste_area_m2": 0.7,
            "waste_percent": 14.5,
            "packing_method": "MaxRects",
        }
        self.pieces = [
            {
                "piece_no": 1,
                "piece_type": "Regular",
                "width_cm": 50,
                "length_cm": 100,
                "qty": 2,
                "edge_type": "2cm عادي",
                "edge_meters": 6,
                "edge_rate_usd": 0.5,
                "edge_cost_usd": 3,
            },
            {
                "piece_no": 2,
                "piece_type": "Special",
                "width_cm": 40,
                "length_cm": 80,
                "qty": 1,
                "edge_type": "2cm عادي",
                "edge_meters": 4,
                "edge_rate_usd": 0.5,
                "edge_cost_usd": 2,
                "special_shape_estimated_unit_price_usd": 24,
                "special_shape_custom_unit_price_usd": 29,
                "special_shape_final_unit_price_usd": 29,
                "special_shape_price_status": "Approved",
                "special_shape_price_approved_by": "accounts@example.com",
            },
            {
                "piece_no": 3,
                "piece_type": "Clipped Corner",
                "width_cm": 60,
                "length_cm": 90,
                "qty": 1,
                "edge_type": "2cm عادي",
                "edge_meters": 3,
                "edge_rate_usd": 0.5,
                "edge_cost_usd": 1.5,
                "clipped_corner_edge_price_usd": 7.5,
                "clipped_corner_edge_price_status": "Priced",
            },
        ]

    def test_application_layer_has_no_frappe_dependency(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("erpnext", source)

    def test_customer_invoice_excludes_internal_management_sections(self) -> None:
        payload = build_customer_invoice_document(self.order, self.pieces)
        self.assertEqual(payload["kind"], "customer_invoice")
        self.assertNotIn("cost_breakdown", payload)
        self.assertNotIn("operations", payload)
        self.assertNotIn("special_prices", payload)
        self.assertNotIn("classification", payload)
        self.assertEqual(payload["totals"][0]["value_usd"], 85.5)
        self.assertEqual(
            [line["type"] for line in payload["lines"]],
            ["material", "cutting", "edge", "special", "cut_corner"],
        )
        descriptions = [line["description"] for line in payload["lines"]]
        self.assertIn("درفة خاصة رقم 2", descriptions)
        self.assertIn("درفة زاوية مقصوصة 3", descriptions)
        cut_corner = next(line for line in payload["lines"] if line["type"] == "cut_corner")
        self.assertEqual(cut_corner["amount_usd"], 7.5)

    def test_customer_summary_uses_door_count_not_board_count(self) -> None:
        payload = build_customer_invoice_document(self.order, self.pieces)
        summary = {item["label"]: item["value"] for item in payload["summary"]}
        self.assertEqual(summary["عدد الدرف"], 4)
        self.assertNotIn("عدد الألواح", summary)
        self.assertTrue(all("edge_meters" not in row for row in payload["measurements"]))

    def test_extra_addons_are_itemized_from_the_historical_price_snapshot(self) -> None:
        pieces = [
            {
                "piece_no": 4,
                "piece_type": "Extra",
                "width_cm": 50,
                "length_cm": 90,
                "qty": 2,
                "notes": "تنفيذ إضافي",
                "extra_double": 1,
                "extra_double_unit_price_usd": 4,
                "extra_double_total_usd": 8,
                "extra_liner": 1,
                "extra_liner_unit_price_usd": 2.5,
                "extra_liner_total_usd": 5,
            }
        ]

        payload = build_customer_invoice_document(
            {
                **self.order,
                "required_boards": 0,
                "mdf_cost_usd": 0,
                "cutting_cost_usd": 0,
                "edge_cost_usd": 0,
                "total_cost_usd": 0,
            },
            pieces,
        )

        self.assertEqual(
            [line["description"] for line in payload["lines"]],
            ["إضافة Double — درفة رقم 1", "إضافة Liner — درفة رقم 1"],
        )
        self.assertEqual([line["rate_usd"] for line in payload["lines"]], [4.0, 2.5])
        self.assertEqual(payload["totals"][0]["value_usd"], 13.0)
        self.assertEqual(payload["measurements"][0]["piece_type"], "إضافية")
        self.assertIn("إضافات: Double، Liner", payload["measurements"][0]["notes"])

    def test_internal_report_calculates_margin_and_special_price_variance(self) -> None:
        payload = build_internal_cost_report_document(self.order, self.pieces)
        self.assertEqual(payload["kind"], "internal_cost_report")
        self.assertIn("داخلي", payload["classification"])
        summary = {item["label"]: item["value"] for item in payload["summary"]}
        self.assertEqual(summary["التكلفة الفعلية/المتوقعة ($)"], 54.0)
        self.assertEqual(summary["عرض الزبون ($)"], 80.0)
        self.assertEqual(summary["هامش الربح ($)"], 26.0)
        self.assertEqual(summary["هامش الربح (%)"], 32.5)
        self.assertEqual(payload["special_prices"][0]["variance_total_usd"], 5.0)
        operations = {item["label"]: item["value"] for item in payload["operations"]}
        self.assertEqual(operations["عدد الألواح"], 2)
        self.assertEqual(operations["إجمالي القشاط (م)"], 12.0)

    def test_non_finite_or_invalid_values_fail_closed_to_zero(self) -> None:
        order = {**self.order, "actual_cost_usd": float("nan")}
        payload = build_internal_cost_report_document(order, self.pieces)
        summary = {item["label"]: item["value"] for item in payload["summary"]}
        self.assertEqual(summary["التكلفة الفعلية/المتوقعة ($)"], 54.0)


if __name__ == "__main__":
    unittest.main()
