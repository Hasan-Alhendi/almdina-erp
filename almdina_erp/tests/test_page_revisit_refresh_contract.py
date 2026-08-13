from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
HELPER = ROOT / "public" / "js" / "page_revisit_refresh.js"
PAGES = ROOT / "almdina_erp" / "page"

# Frappe renders a desk page once and only fires "show" on later visits. Every
# data-driven page must reload then, otherwise the operator keeps seeing the
# snapshot of their first visit until they reload the browser.
DATA_DRIVEN_PAGES = (
    "shop_floor_inbox",
    "factory_workforce",
    "factory_permissions",
    "factory_master_data",
    "factory_approval_queue",
    "factory_plan_archive",
    "factory_production_settings",
    "factory_stock_settings",
)


class TestPageRevisitRefreshContract(unittest.TestCase):
    def test_helper_is_loaded_for_every_desk_session(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")

        self.assertIn('"/assets/almdina_erp/js/page_revisit_refresh.js"', hooks)

    def test_helper_skips_the_show_event_of_the_initial_load(self) -> None:
        source = HELPER.read_text(encoding="utf-8")

        self.assertIn("function refreshOnRevisit(wrapper, reload)", source)
        self.assertIn("wrapper.on_page_show = function ()", source)
        self.assertIn("initialShowConsumed", source)

    def test_every_data_driven_page_reloads_when_revisited(self) -> None:
        for page in DATA_DRIVEN_PAGES:
            source = (PAGES / page / f"{page}.js").read_text(encoding="utf-8")
            self.assertIn("AlmdinaPageRevisit.refreshOnRevisit(", source, page)

    def test_inbox_opens_the_canonical_order_form_instead_of_loading_a_panel(self) -> None:
        source = (PAGES / "shop_floor_inbox" / "shop_floor_inbox.js").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'frappe.set_route("Form", "Door Cutting Order", context.order)',
            source,
        )
        self.assertNotIn("function drawingPlanModule()", source)
        self.assertNotIn("renderInboxPanel", source)
        self.assertNotIn("get_order_shop_floor_detail", source)


if __name__ == "__main__":
    unittest.main()
