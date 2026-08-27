from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.py"
PRESENTER_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_presenter.js"
)
THEME_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_theme.js"
)
PLAN_RENDERER_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_cutting_plan_renderer.js"
)
FINANCIAL_DOCUMENTS_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_financial_documents_ux.js"
)
SHAPE_PRINT_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_shape_print.js"
)
COST_DOCUMENTS_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_multi_edge_documents_ux.js"
)


class TestCompactInvoicePrintContract(unittest.TestCase):
    def test_one_presenter_owns_both_customer_prints_with_shared_theme(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]

        shape = scripts.index(
            "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js"
        )
        theme = scripts.index(
            "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js"
        )
        presenter = scripts.index(
            "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js"
        )
        documents = scripts.index(
            "public/js/door_cutting_order/costing/door_cutting_order_multi_edge_documents_ux.js"
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

    def test_invoice_is_exact_measurement_document_plus_quote_at_the_end(self) -> None:
        presenter = PRESENTER_PATH.read_text(encoding="utf-8")
        financial = FINANCIAL_DOCUMENTS_PATH.read_text(encoding="utf-8")

        self.assertIn("function sharedHeader", presenter)
        self.assertIn("function sharedInfo", presenter)
        self.assertIn("function measurementTable", presenter)
        self.assertIn("function orderNotesHtml", presenter)
        self.assertIn("function measurementDocumentBody", presenter)
        self.assertIn("function quoteDetailsHtml", presenter)
        self.assertIn("function printAuthorizedInvoice", presenter)
        self.assertIn('theme.css("measurements", shapePrintCss())', presenter)
        self.assertIn(
            "${invoice ? measurementDocumentBodyWithPayload(frm, quotePayload) : measurementDocumentBody(frm)}",
            presenter,
        )
        self.assertIn('${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}', presenter)
        self.assertLess(
            presenter.index(
                "${invoice ? measurementDocumentBodyWithPayload(frm, quotePayload) : measurementDocumentBody(frm)}"
            ),
            presenter.index('${invoice ? quoteDetailsHtml(quotePayload || {}) : ""}'),
        )
        self.assertNotIn("function invoiceSummary", presenter)
        self.assertNotIn("function invoiceLines(frm)", presenter)
        self.assertNotIn("function invoiceTotal(frm", presenter)

        self.assertIn("presenter.printAuthorizedInvoice(frm, payload)", financial)
        self.assertNotIn("function measurementsHtml", financial)
        self.assertNotIn("function invoiceLinesHtml", financial)
        self.assertIn(
            'throw new Error("Customer invoice layout belongs to AlmdinaOrderDocumentPrint")',
            financial,
        )

    def test_factory_header_has_one_markup_and_style_owner(self) -> None:
        theme = THEME_PATH.read_text(encoding="utf-8")
        presenter = PRESENTER_PATH.read_text(encoding="utf-8")
        financial = FINANCIAL_DOCUMENTS_PATH.read_text(encoding="utf-8")
        renderer = PLAN_RENDERER_PATH.read_text(encoding="utf-8")

        self.assertIn("function headerHtml", theme)
        self.assertIn("function headerCss", theme)
        self.assertIn('class="dco-unified-print-header"', theme)
        self.assertIn("dco-unified-print-factory-name", theme)
        self.assertIn("dco-unified-print-factory-description", theme)
        self.assertIn("dco-unified-print-factory-address", theme)
        self.assertIn("dco-unified-print-factory-contacts", theme)
        self.assertIn("headerHtml,", theme)
        self.assertIn("headerCss,", theme)

        self.assertIn("theme.headerHtml(printIdentity", presenter)
        self.assertIn("theme.headerHtml(printIdentity", financial)
        self.assertIn("return theme.headerHtml(identity, { title, meta })", renderer)
        self.assertIn("return theme.headerCss()", renderer)
        self.assertIn("AlmdinaFactoryPrintIdentity", financial)
        self.assertIn("AlmdinaFactoryPrintIdentity", renderer)

        for consumer in (presenter, financial, renderer):
            self.assertNotIn("function factoryIdentityHtml", consumer)
            self.assertNotIn("function printFactoryIdentityHtml", consumer)
            self.assertNotIn("dco-print-factory-name", consumer)
            self.assertNotIn("print_factory_description ||", consumer)
            self.assertNotIn("print_factory_address ||", consumer)

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
        self.assertIn("${headerCss()}", source)
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
