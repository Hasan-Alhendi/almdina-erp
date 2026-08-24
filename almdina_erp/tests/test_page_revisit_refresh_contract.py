from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "frontend_assets.py"
HELPER = ROOT / "public" / "js" / "page_revisit_refresh.js"
PAGES = ROOT / "almdina_erp" / "page"
PAGE_LOCAL_CONTROLLERS = {
    "shop_floor_inbox": ROOT / "public" / "js" / "shop_floor_inbox" / "controller.js",
    "factory_permissions": ROOT / "public" / "js" / "factory_permissions" / "controller.js",
    "factory_workforce": ROOT / "public" / "js" / "factory_workforce" / "controller.js",
    "factory_production_settings": ROOT / "public" / "js" / "factory_production_settings" / "controller.js",
}

# Frappe renders a desk page once and only fires "show" on later visits. Every
# data-driven page must reload then, otherwise the operator keeps seeing the
# snapshot of their first visit until they reload the browser. Structurally
# extracted pages may delegate this lifecycle responsibility to their loaded
# page-local controller instead of keeping it in the bootstrap file.
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

    def test_helper_separates_mount_from_active_visit_lifetime(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn("function bindActivationLifecycle(wrapper, callbacks = {})", source)
        self.assertIn("function refreshOnRevisit(wrapper, reload)", source)
        self.assertIn('`show${EVENT_NAMESPACE}`', source)
        self.assertIn('`hide${EVENT_NAMESPACE}`', source)
        self.assertIn("isCurrentPage(wrapper)", source)
        self.assertIn("hasVisited(wrapper)", source)
        self.assertNotIn("wrapper.on_page_show =", source)

    def test_every_data_driven_page_reloads_when_revisited(self) -> None:
        for page in DATA_DRIVEN_PAGES:
            page_source = (PAGES / page / f"{page}.js").read_text(encoding="utf-8")
            controller_path = PAGE_LOCAL_CONTROLLERS.get(page)
            if controller_path is None:
                self.assertIn("AlmdinaPageRevisit.refreshOnRevisit(", page_source, page)
                continue

            controller_source = controller_path.read_text(encoding="utf-8")
            controller_asset = f'/assets/almdina_erp/js/{controller_path.parent.name}/controller.js'
            self.assertIn(controller_asset, page_source, page)
            if page in {
                "factory_permissions",
                "factory_workforce",
                "factory_production_settings",
            }:
                self.assertIn("bindActivationLifecycle(wrapper", controller_source, page)
                self.assertIn("onDeactivate", controller_source, page)
            else:
                self.assertIn("AlmdinaPageRevisit.refreshOnRevisit(", controller_source, page)

            if page == "factory_permissions":
                for marker in (
                    "onActivate: activatePage",
                    "function activatePage()",
                    "state.saving",
                    "reconcileAfterSave",
                    "isDirty()",
                ):
                    self.assertIn(marker, controller_source, page)
            elif page in {"factory_workforce", "factory_production_settings"}:
                self.assertIn(
                    "onActivate: load",
                    controller_source,
                    page,
                )
            elif page == "shop_floor_inbox":
                self.assertIn(
                    "AlmdinaPageRevisit.refreshOnRevisit(wrapper, refresh)",
                    controller_source,
                    page,
                )

    def test_inbox_opens_the_canonical_order_form_instead_of_loading_a_panel(self) -> None:
        page_source = (PAGES / "shop_floor_inbox" / "shop_floor_inbox.js").read_text(
            encoding="utf-8"
        )
        controller_source = PAGE_LOCAL_CONTROLLERS["shop_floor_inbox"].read_text(
            encoding="utf-8"
        )
        combined = f"{page_source}\n{controller_source}"

        self.assertIn(
            'frappe.set_route("Form", "Door Cutting Order", context.order)',
            controller_source,
        )
        self.assertNotIn("function drawingPlanModule()", combined)
        self.assertNotIn("renderInboxPanel", combined)
        self.assertNotIn("get_order_shop_floor_detail", combined)


if __name__ == "__main__":
    unittest.main()
