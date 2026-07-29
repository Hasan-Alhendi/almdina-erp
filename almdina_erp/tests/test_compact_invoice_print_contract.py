from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.py"
PRESENTER_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
)


class TestCompactInvoicePrintContract(unittest.TestCase):
    def test_one_presenter_owns_both_print_buttons_before_legacy_documents(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]

        presenter = "public/js/door_cutting_order_document_print_presenter.js"
        presenter_index = scripts.index(presenter)
        legacy_index = scripts.index(
            "public/js/door_cutting_order_multi_edge_documents_ux.js"
        )
        costing_index = scripts.index(
            "public/js/door_cutting_order_cost_invoice_ux.js"
        )

        self.assertGreater(presenter_index, costing_index)
        self.assertLess(presenter_index, legacy_index)
        self.assertNotIn(
            "public/js/door_cutting_order_measurement_print_presenter.js",
            scripts,
        )
        self.assertNotIn(
            "public/js/door_cutting_order_compact_invoice_print_presenter.js",
            scripts,
        )

    def test_rows_show_only_custom_edge_exceptions(self) -> None:
        source = PRESENTER_PATH.read_text(encoding="utf-8")

        self.assertIn("function customEdgeGroups", source)
        self.assertIn(".filter(detail => Boolean(detail.custom))", source)
        self.assertIn("function customEdgeDetailsHtml", source)
        self.assertIn('return "على الداير"', source)
        self.assertIn('if (!groups.length) return \'<span class="custom-edge-empty"', source)
        self.assertIn("القشاط المخصص", source)
        self.assertIn('if (note.includes("من القشاط الافتراضي")) return ""', source)
        self.assertNotIn("rate_usd_per_meter *", source)
        self.assertNotIn("width_cm *", source)

    def test_measurements_and_invoice_share_one_document_layout(self) -> None:
        source = PRESENTER_PATH.read_text(encoding="utf-8")

        self.assertIn("function sharedHeader", source)
        self.assertIn("function sharedInfo", source)
        self.assertIn("function measurementTable", source)
        self.assertIn("function documentHtml(frm, mode)", source)
        self.assertIn('mode === "invoice" ? invoiceSummary(frm) : ""', source)
        self.assertIn('mode === "invoice" ? invoiceLines(frm) : []', source)
        self.assertIn('event.target.closest(".dco-print-customer-invoice")', source)
        self.assertIn(
            'event.target.closest(".dco-print-measurements,.dco-entry-window-print")',
            source,
        )
        self.assertIn("event.stopImmediatePropagation()", source)
        self.assertIn("notesCellHtml", source)
        self.assertIn("shapePrintCss", source)

    def test_measurement_layout_targets_about_26_regular_rows_per_a4_page(self) -> None:
        source = PRESENTER_PATH.read_text(encoding="utf-8")

        self.assertIn('@page{size:A4 portrait;margin:${measurementOnly ? "5mm" : "6mm"}}', source)
        self.assertIn("grid-template-columns:repeat(6,minmax(0,1fr))", source)
        self.assertIn("table-layout:fixed", source)
        self.assertIn("display:table-header-group", source)
        self.assertIn("break-inside:avoid", source)
        self.assertIn('${measurementOnly ? "1px 2px" : "2px 3px"}', source)
        self.assertIn('${measurementOnly ? "6.5px" : "7.1px"}', source)


if __name__ == "__main__":
    unittest.main()
