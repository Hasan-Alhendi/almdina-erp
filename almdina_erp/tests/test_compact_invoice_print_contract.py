from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.py"
PRESENTER_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
)
THEME_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_theme.js"
)
SHAPE_PRINT_PATH = ROOT / "public" / "js" / "door_cutting_order_shape_print.js"
COST_DOCUMENTS_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_multi_edge_documents_ux.js"
)


class TestCompactInvoicePrintContract(unittest.TestCase):
    def test_one_presenter_owns_both_print_buttons_with_separate_theme(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]

        shape = scripts.index("public/js/door_cutting_order_shape_print.js")
        theme = scripts.index(
            "public/js/door_cutting_order_document_print_theme.js"
        )
        presenter = scripts.index(
            "public/js/door_cutting_order_document_print_presenter.js"
        )
        documents = scripts.index(
            "public/js/door_cutting_order_multi_edge_documents_ux.js"
        )

        self.assertLess(shape, theme)
        self.assertLess(theme, presenter)
        self.assertLess(presenter, documents)
        self.assertNotIn(
            "public/js/door_cutting_order_cost_invoice_ux.js",
            scripts,
        )
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
        self.assertIn(
            'if (!groups.length) return \'<span class="custom-edge-empty"',
            source,
        )
        self.assertIn("القشاط المخصص", source)
        self.assertIn(
            'if (note.includes("من القشاط الافتراضي")) return ""',
            source,
        )
        self.assertNotIn("rate_usd_per_meter *", source)
        self.assertNotIn("width_cm *", source)

    def test_measurements_and_invoice_share_one_document_layout(self) -> None:
        source = PRESENTER_PATH.read_text(encoding="utf-8")

        self.assertIn("function sharedHeader", source)
        self.assertIn("function sharedInfo", source)
        self.assertIn("function measurementTable", source)
        self.assertIn("function documentHtml(frm, mode, printIdentity = null)", source)
        self.assertIn("function factoryIdentityHtml", source)
        self.assertIn("AlmdinaFactoryPrintIdentity", source)
        self.assertIn('mode === "invoice" ? invoiceSummary(frm) : ""', source)
        self.assertIn('mode === "invoice" ? invoiceLines(frm) : []', source)
        self.assertIn(
            'event.target.closest(".dco-print-customer-invoice")', source
        )
        self.assertIn(
            'event.target.closest(".dco-print-measurements,.dco-entry-window-print")',
            source,
        )
        self.assertIn("event.stopImmediatePropagation()", source)
        self.assertIn("notesCellHtml", source)
        self.assertIn("shapePrintCss", source)
        self.assertIn("AlmdinaOrderDocumentPrintTheme", source)

    def test_print_theme_uses_readable_pt_scale_without_wasting_a4_space(self) -> None:
        source = THEME_PATH.read_text(encoding="utf-8")

        self.assertIn('@page{size:A4 portrait;margin:${pageMargin}}', source)
        self.assertIn(
            'const bodySize = measurements ? "8.1pt" : "8.5pt"', source
        )
        self.assertIn(
            'const tableSize = measurements ? "7.65pt" : "8.05pt"', source
        )
        self.assertIn(
            'const rowPadding = measurements ? "1.05mm 1.1mm"', source
        )
        self.assertIn(
            "grid-template-columns:repeat(6,minmax(0,1fr))", source
        )
        self.assertIn("table-layout:fixed", source)
        self.assertIn("display:table-header-group", source)
        self.assertIn("break-inside:avoid", source)
        self.assertIn(
            'const sketchHeight = measurements ? "27mm" : "31mm"', source
        )
        self.assertNotIn("body{font-size:7.4px", source)

    def test_printed_drawing_notes_respect_font_size_and_have_no_box(self) -> None:
        source = SHAPE_PRINT_PATH.read_text(encoding="utf-8")

        self.assertIn("Math.max(24, Math.min(38, parsed))", source)
        self.assertIn("element.font_size || element.fontSize || 24", source)
        self.assertIn('data-dco-readable-note="1"', source)
        self.assertIn('paint-order="stroke"', source)
        self.assertIn('stroke="#fff"', source)
        self.assertNotIn('fill="#fff8c9"', source)
        self.assertIn("window.AlmdinaShapePrint = Object.freeze", source)

    def test_cost_screen_table_is_compact_responsive_and_custom_only(self) -> None:
        source = COST_DOCUMENTS_PATH.read_text(encoding="utf-8")

        self.assertIn("function customEdgeGroups", source)
        self.assertIn(".filter(detail => Boolean(detail.custom))", source)
        self.assertIn("القشاط المخصص", source)
        self.assertIn("dco-custom-edge-chip", source)
        self.assertIn("dco-cost-table--enhanced", source)
        self.assertIn("@media(max-width:760px)", source)
        self.assertIn("data-label", source)
        self.assertIn("سطر مستقل لكل نوع قشاط وسعره", source)
        self.assertNotIn("bindPrintInterception", source)
        self.assertNotIn("printMeasurementsHtml", source)
        self.assertNotIn("printInvoiceHtml", source)


if __name__ == "__main__":
    unittest.main()
