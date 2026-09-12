from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRINTING = ROOT / "public" / "js" / "door_cutting_order" / "printing"
PRESENTER = PRINTING / "door_cutting_order_document_print_presenter.js"
THEME = PRINTING / "door_cutting_order_document_print_theme.js"


class TestDcoDocumentPrintHeader(unittest.TestCase):
    def setUp(self) -> None:
        self.presenter = PRESENTER.read_text(encoding="utf-8")
        self.theme = THEME.read_text(encoding="utf-8")

    def _function_block(self, source: str, function_name: str, next_function: str) -> str:
        pattern = rf"function {re.escape(function_name)}\b.*?(?=\n    function {re.escape(next_function)}\b)"
        match = re.search(pattern, source, flags=re.DOTALL)
        self.assertIsNotNone(match, f"Could not locate {function_name}()")
        return match.group(0)

    def test_customer_phone_comes_from_customer_master_and_is_non_blocking(self) -> None:
        resolver = self._function_block(
            self.presenter,
            "resolveCustomerPhone",
            "ensureProfiles",
        )

        self.assertIn('frappe.db.get_value("Customer", customer, "mobile_no")', resolver)
        self.assertIn('catch (error)', resolver)
        self.assertIn('return "";', resolver)
        self.assertNotIn("order_notes", resolver)

    def test_print_preparation_resolves_phone_for_measurements_and_invoice(self) -> None:
        measurements = self._function_block(
            self.presenter,
            "printMeasurements",
            "printAuthorizedInvoice",
        )
        invoice = self._function_block(
            self.presenter,
            "printAuthorizedInvoice",
            "requestAuthorizedInvoice",
        )

        for block in (measurements, invoice):
            self.assertIn("resolveCustomerPhone(frm)", block)
            self.assertIn("customerPhone", block)
            self.assertIn("Promise.all", block)

    def test_document_header_separates_title_order_reference_and_date(self) -> None:
        shared_header = self._function_block(self.presenter, "sharedHeader", "sharedInfo")

        self.assertIn('title: "جدول قياسات الطلب"', shared_header)
        self.assertIn("reference,", shared_header)
        self.assertIn("date,", shared_header)
        self.assertNotIn("meta:", shared_header)

        self.assertIn('class="dco-unified-print-reference"', self.theme)
        self.assertIn('class="dco-unified-print-date"', self.theme)
        self.assertIn(".dco-unified-print-reference{", self.theme)
        self.assertIn(".dco-unified-print-date{", self.theme)

    def test_shared_summary_has_only_customer_board_edge_color_and_door_count(self) -> None:
        shared_info = self._function_block(self.presenter, "sharedInfo", "measurementTableWithPayload")

        self.assertIn('<b>الزبون</b>', shared_info)
        self.assertIn('class="shared-info-phone"', shared_info)
        self.assertIn('<b>اللوح</b>', shared_info)
        self.assertIn('<b>لون القشاط</b>', shared_info)
        self.assertIn('<b>عدد الدرف</b>', shared_info)
        self.assertNotIn('<b>رقم الطلب</b>', shared_info)
        self.assertNotIn('<b>نوع القشاط</b>', shared_info)
        self.assertNotIn("default_edge_type", shared_info)

    def test_customer_phone_has_an_explicit_empty_state(self) -> None:
        shared_info = self._function_block(self.presenter, "sharedInfo", "measurementTableWithPayload")

        self.assertIn('const phone = String(customerPhone || "").trim();', shared_info)
        self.assertIn('${esc(phone || "—")}', shared_info)

    def test_summary_layout_is_four_columns_with_customer_card_emphasis(self) -> None:
        self.assertIn(
            ".shared-info{grid-template-columns:minmax(0,1.65fr) minmax(0,1.2fr) minmax(0,1fr) minmax(0,.72fr)}",
            self.theme,
        )
        self.assertIn(".shared-info-primary{", self.theme)
        self.assertIn(".shared-info-phone{", self.theme)
        self.assertIn(".shared-info-phone-value{", self.theme)
        self.assertNotIn(
            ".shared-info{grid-template-columns:repeat(6,minmax(0,1fr))}",
            self.theme,
        )

    def test_existing_document_html_callers_remain_backward_compatible(self) -> None:
        signature = re.search(
            r"function documentHtml\(\s*frm,\s*mode = \"measurements\",\s*printIdentity = null,\s*quotePayload = null,\s*customerPhone = \"\"\s*\)",
            self.presenter,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(signature)


if __name__ == "__main__":
    unittest.main()
