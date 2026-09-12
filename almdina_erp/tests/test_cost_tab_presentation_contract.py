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
COMPACT_PRICING_UX_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_compact_pricing_ux.js"
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

    def test_cost_layout_layers_load_before_workspace_rendering(self) -> None:
        source = REGISTRY_PATH.read_text(encoding="utf-8")
        presenter = source.index("door_cutting_order_cost_presenter.js")
        addon_summary = source.index("door_cutting_order_customer_invoice_addon_summary.js")
        layout = source.index("door_cutting_order_cost_page_layout_ux.js")
        compact_pricing = source.index("door_cutting_order_compact_pricing_ux.js")
        adapter = source.index("door_cutting_order_cost_workspace_presenter_adapter.js")

        self.assertLess(presenter, addon_summary)
        self.assertLess(addon_summary, layout)
        self.assertLess(layout, compact_pricing)
        self.assertLess(compact_pricing, adapter)
        self.assertIn('"AlmdinaCompactPricingUX"', source)

    def test_layout_contract_keeps_invoice_action_compact_and_measurements_collapsible(self) -> None:
        source = LAYOUT_UX_PATH.read_text(encoding="utf-8")

        self.assertIn("dco-cost-invoice-actions", source)
        self.assertIn("dco-secure-print-internal-cost-report", source)
        self.assertIn("display:none!important", source)
        self.assertIn("dco-cost-measurements-toggle", source)
        self.assertIn("__almdina_cost_measurements_expanded = false", source)
        self.assertIn("aria-expanded", source)
        self.assertIn("actions = $('<div class=\"dco-cost-actions\"></div>')", source)

    def test_measurement_header_keeps_rtl_title_and_toggle_from_collapsing(self) -> None:
        source = LAYOUT_UX_PATH.read_text(encoding="utf-8")

        self.assertIn('STYLE_ID = "dco-cost-page-layout-ux-v3"', source)
        self.assertIn("min-width:max-content;flex:0 0 auto;white-space:nowrap", source)
        self.assertIn("h4{margin:0;white-space:nowrap;flex:0 0 auto", source)
        self.assertIn("text-overflow:ellipsis;white-space:nowrap", source)
        self.assertIn("flex:0 0 26px!important", source)
        self.assertIn('content:"⌄"!important', source)
        self.assertIn("content:none!important", source)

    def test_measurement_toggle_contains_no_accessibility_text_node(self) -> None:
        source = LAYOUT_UX_PATH.read_text(encoding="utf-8")

        self.assertIn('<button type="button" class="dco-cost-measurements-toggle"></button>', source)
        self.assertIn('.attr("aria-labelledby", headingId)', source)
        self.assertIn('.empty()', source)
        self.assertIn('.removeAttr("aria-label title role tabindex")', source)
        self.assertNotIn("dco-cost-measurements-toggle-label", source)
        self.assertNotIn("dco-cost-measurements-toggle-icon", source)
        self.assertNotIn('.on("keydown.almdinaCostMeasurements"', source)

    def test_layout_module_can_upgrade_a_stale_spa_instance(self) -> None:
        source = LAYOUT_UX_PATH.read_text(encoding="utf-8")

        self.assertIn("const MODULE_VERSION = 3", source)
        self.assertIn("Number(existingApi.version || 0) >= MODULE_VERSION", source)
        self.assertIn('"dco-cost-page-layout-ux-v1"', source)
        self.assertIn('"dco-cost-page-layout-ux-v2"', source)
        self.assertIn("version: MODULE_VERSION", source)

    def test_custom_door_pricing_is_compact_and_attention_first(self) -> None:
        source = COMPACT_PRICING_UX_PATH.read_text(encoding="utf-8")

        self.assertIn("dco-compact-pricing-section", source)
        self.assertIn(".dco-special-price-id + .dco-special-price-cell{display:none!important}", source)
        self.assertIn("dco-inline-price-input", source)
        self.assertIn("cards.sort((left, right)", source)
        self.assertIn("غير مسعّرة من", source)
        self.assertIn("✓ مسعّر", source)
        self.assertNotIn("replaceWith", source)
        self.assertNotIn(".html(", source)


if __name__ == "__main__":
    unittest.main()
