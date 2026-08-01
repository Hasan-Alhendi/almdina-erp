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
        self.assertEqual(payload["totals"][0]["value_usd"], 78.0)
        self.assertEqual(
            [line["type"] for line in payload["lines"]],
            ["material", "cutting", "edge", "special"],
        )

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

    def test_non_finite_or_invalid_values_fail_closed_to_zero(self) -> None:
        order = {**self.order, "actual_cost_usd": float("nan")}
        payload = build_internal_cost_report_document(order, self.pieces)
        summary = {item["label"]: item["value"] for item in payload["summary"]}
        self.assertEqual(summary["التكلفة الفعلية/المتوقعة ($)"], 54.0)


if __name__ == "__main__":
    unittest.main()
