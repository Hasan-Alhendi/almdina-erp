from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAB_PERMISSIONS = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_tab_permissions_ux.js"
COST_PERMISSIONS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_permissions_ux.js"
)
PERMISSION_CONTEXT = ROOT / "public" / "js" / "permission_context.js"
PLAN_BOOTSTRAP = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_surface_bootstrap.js"
)
MANIFEST = ROOT / "frontend_assets.py"


class TestOrderTabPermissionsUX(unittest.TestCase):
    def test_plan_and_cost_tabs_follow_capabilities_on_new_and_saved_orders(self) -> None:
        source = TAB_PERMISSIONS.read_text(encoding="utf-8")

        self.assertIn('results_tab: "view_cutting_plan"', source)
        self.assertIn('cost_tab: "view_costs"', source)
        self.assertNotIn("const saved = !frm.is_new()", source)
        self.assertIn('results_tab: can(frm, TAB_RULES.results_tab)', source)
        self.assertIn('can(frm, "print_customer_invoice")', source)
        self.assertIn("setRenderedVisibility(frm, fieldname, visible)", source)
        self.assertIn("applyRenderedVisibility(frm, visibility)", source)
        self.assertIn('window.addEventListener("almdina:permissions-updated"', source)
        self.assertIn('activateOrderTab(frm)', source)

    def test_tab_visibility_never_rebuilds_the_frappe_form_layout(self) -> None:
        tabs = TAB_PERMISSIONS.read_text(encoding="utf-8")
        costs = COST_PERMISSIONS.read_text(encoding="utf-8")

        self.assertNotIn('frm.set_df_property(fieldname, "hidden"', tabs)
        self.assertNotIn('frm.set_df_property("cost_tab", "hidden"', costs)
        self.assertIn("Do not call frm.set_df_property", tabs)
        self.assertIn("Never mutate", costs)
        self.assertIn("AlmdinaOrderTabPermissionsUX", costs)
        self.assertIn("tabs.apply(frm)", costs)

    def test_tab_policy_is_capability_driven_without_role_names(self) -> None:
        source = TAB_PERMISSIONS.read_text(encoding="utf-8")

        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("Production Manager", source)
        self.assertNotIn("Accounts Management", source)
        self.assertNotIn("System Manager", source)

    def test_compatibility_modules_still_wait_for_source_registered_globals(self) -> None:
        source = PERMISSION_CONTEXT.read_text(encoding="utf-8")
        manifest = MANIFEST.read_text(encoding="utf-8")

        self.assertIn('global: "AlmdinaOrderTabPermissionsUX"', source)
        self.assertIn("function waitForGlobal", source)
        self.assertIn("return waitForGlobal(module.global)", source)
        self.assertIn('"public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js"', manifest)

    def test_cutting_plan_surface_loads_independently_from_cost_chain(self) -> None:
        source = PERMISSION_CONTEXT.read_text(encoding="utf-8")
        bootstrap = PLAN_BOOTSTRAP.read_text(encoding="utf-8")

        self.assertIn('global: "AlmdinaCuttingPlanSurfaceBootstrap"', source)
        self.assertIn(
            'asset: "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_plan_surface_bootstrap.js"',
            source,
        )
        self.assertIn("loadPlanSurfaceModule();", source)
        self.assertLess(
            source.index("loadPlanSurfaceModule();"),
            source.index("modulesPromise = ORDER_MODULES.reduce"),
        )
        self.assertIn('api.canDocument(frm, "view_cutting_plan")', bootstrap)
        self.assertNotIn('"view_costs"', bootstrap)
        self.assertIn("await frappe.require(module.asset)", bootstrap)
        self.assertIn("presenter.refresh(frm)", bootstrap)
        self.assertIn("tabs.afterRender(frm)", bootstrap)


if __name__ == "__main__":
    unittest.main()
