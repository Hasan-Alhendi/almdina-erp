from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.py"
PRESENTER_PATH = (
    ROOT / "public" / "js" / "door_cutting_order_compact_invoice_print_presenter.js"
)


class TestCompactInvoicePrintContract(unittest.TestCase):
    def test_compact_presenter_owns_invoice_print_before_legacy_documents(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]

        compact_index = scripts.index(
            "public/js/door_cutting_order_compact_invoice_print_presenter.js"
        )
        legacy_index = scripts.index(
            "public/js/door_cutting_order_multi_edge_documents_ux.js"
        )
        costing_index = scripts.index(
            "public/js/door_cutting_order_cost_invoice_ux.js"
        )

        self.assertGreater(compact_index, costing_index)
        self.assertLess(compact_index, legacy_index)

    def test_print_groups_default_edges_and_expands_only_custom_exceptions(self) -> None:
        source = PRESENTER_PATH.read_text(encoding="utf-8")

        self.assertIn("function groupedEdgeDetails", source)
        self.assertIn("function compactEdgeDetailsHtml", source)
        self.assertIn('return "على الداير"', source)
        self.assertIn('group.custom ? "<em>مخصص</em>" : ""', source)
        self.assertIn("window.AlmdinaMultiEdgeDocuments", source)
        self.assertIn("documents.invoiceLines(frm)", source)
        self.assertIn("documents.invoiceTotal(frm)", source)

    def test_print_layout_is_compact_a4_portrait(self) -> None:
        source = PRESENTER_PATH.read_text(encoding="utf-8")

        self.assertIn("@page{size:A4 portrait;margin:6mm}", source)
        self.assertIn("grid-template-columns:repeat(6,minmax(0,1fr))", source)
        self.assertIn("table-layout:fixed", source)
        self.assertIn("break-inside:avoid", source)
        self.assertIn('event.target.closest(".dco-print-customer-invoice")', source)
        self.assertIn("event.stopImmediatePropagation()", source)


if __name__ == "__main__":
    unittest.main()
