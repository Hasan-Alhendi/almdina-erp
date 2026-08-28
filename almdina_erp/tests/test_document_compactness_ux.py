from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.py"
REGISTRY_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)
POLICY_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_compactness_ux.js"
)


class TestDocumentCompactnessUX(unittest.TestCase):
    def test_policy_loads_after_print_presenter_and_before_lazy_cost_documents(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        scripts = hooks["doctype_js"]["Door Cutting Order"]
        registry = REGISTRY_PATH.read_text(encoding="utf-8")

        theme = scripts.index(
            "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js"
        )
        presenter = scripts.index(
            "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js"
        )
        compactness = scripts.index(
            "public/js/door_cutting_order/printing/door_cutting_order_document_compactness_ux.js"
        )

        self.assertLess(theme, presenter)
        self.assertLess(presenter, compactness)
        self.assertNotIn(
            "public/js/door_cutting_order/costing/door_cutting_order_multi_edge_documents_ux.js",
            scripts,
        )
        self.assertIn("door_cutting_order_multi_edge_documents_ux.js", registry)

    def test_customer_header_hides_duplicate_financial_strip(self) -> None:
        source = POLICY_PATH.read_text(encoding="utf-8")

        self.assertIn(".financial-info{display:none!important}", source)
        for label in (
            "عدد الألواح",
            "سعر اللوح",
            "أجور القص",
            "إجمالي القشاط",
        ):
            self.assertNotIn(label, source)

    def test_custom_edges_are_plain_text_without_cards(self) -> None:
        source = POLICY_PATH.read_text(encoding="utf-8")

        self.assertIn(".custom-edge-line", source)
        self.assertIn("border:0", source)
        self.assertIn("background:transparent", source)
        self.assertIn(".custom-edge-line em{display:none!important}", source)
        self.assertIn(".dco-custom-edge-chip", source)
        self.assertIn("box-shadow:none!important", source)
        self.assertIn(".dco-custom-edge-chip em{display:none!important}", source)
        self.assertIn(".dco-edge-default-note{display:none!important}", source)

    def test_policy_contains_no_cost_or_dimension_calculations(self) -> None:
        source = POLICY_PATH.read_text(encoding="utf-8")

        for token in (
            "rate_usd_per_meter *",
            "width_cm *",
            "length_cm *",
            "edge_cost_usd =",
            "required_boards *",
        ):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
