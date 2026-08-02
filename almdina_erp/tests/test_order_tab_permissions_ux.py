from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAB_PERMISSIONS = ROOT / "public" / "js" / "door_cutting_order_tab_permissions_ux.js"
PERMISSION_CONTEXT = ROOT / "public" / "js" / "permission_context.js"
HOOKS = ROOT / "hooks.py"


class TestOrderTabPermissionsUX(unittest.TestCase):
    def test_plan_and_cost_tabs_follow_capabilities_and_saved_state(self) -> None:
        source = TAB_PERMISSIONS.read_text(encoding="utf-8")

        self.assertIn('results_tab: "view_cutting_plan"', source)
        self.assertIn('cost_tab: "view_costs"', source)
        self.assertIn("const saved = !frm.is_new()", source)
        self.assertIn('frm.set_df_property(fieldname, "hidden"', source)
        self.assertIn('window.addEventListener("almdina:permissions-updated"', source)
        self.assertIn('activateOrderTab(frm)', source)

    def test_tab_policy_is_capability_driven_without_role_names(self) -> None:
        source = TAB_PERMISSIONS.read_text(encoding="utf-8")

        self.assertNotIn("frappe.user_roles", source)
        self.assertNotIn("Production Manager", source)
        self.assertNotIn("Accounts Management", source)
        self.assertNotIn("System Manager", source)

    def test_permission_context_waits_for_source_registered_protected_modules(self) -> None:
        source = PERMISSION_CONTEXT.read_text(encoding="utf-8")
        hooks = HOOKS.read_text(encoding="utf-8")
        global_name = 'global: "AlmdinaOrderTabPermissionsUX"'

        self.assertIn(global_name, source)
        self.assertIn("Waiting for their globals", source)
        self.assertNotIn("frappe.require(module.path)", source)
        self.assertIn('"public/js/door_cutting_order_tab_permissions_ux.js"', hooks)


if __name__ == "__main__":
    unittest.main()
