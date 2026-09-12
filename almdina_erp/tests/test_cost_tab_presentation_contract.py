from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_PATH = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
REGISTRY_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)
LAYOUT_UX_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_page_layout_ux.js"
)


class CostTabPresentationContractTest(unittest.TestCase):
    def test_board_and_cutting_rates_use_two_native_columns(self) -> None:
        meta = json.loads(DOCTYPE_PATH.read_text(encoding="utf-8"))
        field_order = meta["field_order"]
        self.assertLess(field_order.index("board_rate_usd"), field_order.index("cost_settings_column"))
        self.assertLess(field_order.index("cost_settings_column"), field_order.index("cutting_cost_per_board_usd"))

        fields = {field["fieldname"]: field for field in meta["fields"]}
        self.assertEqual(fields["cost_settings_column"]["fieldtype"], "Column Break")

    def test_cost_content_starts_new_full_width_section_after_rate_columns(self) -> None:
        meta = json.loads(DOCTYPE_PATH.read_text(encoding="utf-8"))
        field_order = meta["field_order"]
        fields = {field["fieldname"]: field for field in meta["fields"]}

        cutting_index = field_order.index("cutting_cost_per_board_usd")
        section_index = field_order.index("cost_content_section")
        invoice_index = field_order.index("order_cost_invoice_html")

        self.assertLess(cutting_index, section_index)
        self.assertLess(section_index, invoice_index)
        self.assertEqual(fields["cost_content_section"]["fieldtype"], "Section Break")

    def test_cost_layout_layer_loads_before_workspace_rendering(self) -> None:
        source = REGISTRY_PATH.read_text(encoding="utf-8")
        presenter = source.index("door_cutting_order_cost_presenter.js")
        addon_summary = source.index("door_cutting_order_customer_invoice_addon_summary.js")
        layout = source.index("door_cutting_order_cost_page_layout_ux.js")
        adapter = source.index("door_cutting_order_cost_workspace_presenter_adapter.js")

        self.assertLess(presenter, addon_summary)
        self.assertLess(addon_summary, layout)
        self.assertLess(layout, adapter)

    def test_layout_contract_keeps_invoice_action_compact_and_measurements_collapsible(self) -> None:
        source = LAYOUT_UX_PATH.read_text(encoding="utf-8")

        self.assertIn("dco-cost-invoice-actions", source)
        self.assertIn("dco-secure-print-internal-cost-report", source)
        self.assertIn("display:none!important", source)
        self.assertIn("dco-cost-measurements-toggle", source)
        self.assertIn("__almdina_cost_measurements_expanded = false", source)
        self.assertIn("aria-expanded", source)
        self.assertIn("actions = $('<div class=\"dco-cost-actions\"></div>')", source)


if __name__ == "__main__":
    unittest.main()
