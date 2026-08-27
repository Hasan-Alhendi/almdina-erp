from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
ASSETS = ROOT / "frontend_assets.py"


class TestDcoPerformanceContract(unittest.TestCase):
    def test_plan_and_cost_reads_are_tab_activated_not_form_eager(self) -> None:
        plan = (
            PUBLIC / "cutting_plan" / "door_cutting_order_plan_workspace_state.js"
        ).read_text(encoding="utf-8")
        cost = (
            PUBLIC / "costing" / "door_cutting_order_cost_workspace_state.js"
        ).read_text(encoding="utf-8")
        coordinator = (
            PUBLIC / "core" / "door_cutting_order_workspace_sync_coordinator.js"
        ).read_text(encoding="utf-8")
        lifecycle = (
            PUBLIC / "core" / "door_cutting_order_workspace_activation_lifecycle.js"
        ).read_text(encoding="utf-8")

        self.assertIn('activationField: "results_tab"', plan)
        self.assertIn('activationField: "cost_tab"', cost)
        self.assertNotIn('frappe.ui.form.on("Door Cutting Order"', plan)
        self.assertNotIn('frappe.ui.form.on("Door Cutting Order"', cost)
        self.assertNotIn('addEventListener("almdina:permissions-updated"', plan)
        self.assertNotIn('addEventListener("almdina:permissions-updated"', cost)

        self.assertIn("function activateCurrent(frm, options = {})", coordinator)
        self.assertIn("activeResourceNames(frm)", coordinator)
        self.assertIn("activationFields", coordinator)
        self.assertIn('new CustomEvent("almdina:workspace-activated"', coordinator)
        self.assertIn("options.activeOnly === true", coordinator)
        self.assertNotIn("frappe.", coordinator)
        self.assertNotIn("registerCleanup", coordinator)

        self.assertIn("frappe.ui.form.on(DOCTYPE", lifecycle)
        self.assertIn('addEventListener("almdina:permissions-updated"', lifecycle)
        self.assertIn("registerCleanup(frm, ACTIVATION_CLEANUP_KEY", lifecycle)
        self.assertIn("owner.activateCurrent(frm, options)", lifecycle)

    def test_activation_adapter_loads_after_both_workspace_states(self) -> None:
        source = ASSETS.read_text(encoding="utf-8")
        plan_state = source.index("door_cutting_order_plan_workspace_state.js")
        cost_state = source.index("door_cutting_order_cost_workspace_state.js")
        lifecycle = source.index("door_cutting_order_workspace_activation_lifecycle.js")
        mutation_policy = source.index("door_cutting_order_mutation_impact_policy.js")

        self.assertLess(plan_state, lifecycle)
        self.assertLess(cost_state, lifecycle)
        self.assertLess(lifecycle, mutation_policy)

    def test_hidden_plan_surface_is_not_a_readiness_blocker(self) -> None:
        source = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_surface_bootstrap.js"
        ).read_text(encoding="utf-8")

        self.assertIn("function workspaceActive(frm)", source)
        self.assertIn("if (!workspaceActive(frm)) return true;", source)
        self.assertIn("if (!workspaceActive(frm)) return;", source)
        self.assertIn('addEventListener("almdina:workspace-activated"', source)
        self.assertIn('names.includes("plan")', source)
        self.assertIn(
            "if (!isOrderForm(frm) || !canViewPlan(frm) || !workspaceActive(frm)) return true;",
            source,
        )

    def test_order_save_keeps_hidden_derived_workspaces_lazy(self) -> None:
        source = (
            PUBLIC
            / "order_entry"
            / "door_cutting_order_mutation_impact_policy.js"
        ).read_text(encoding="utf-8")

        self.assertIn("activeOnly: true", source)
        self.assertIn("coordinator.refresh(frm, impact.resources", source)

    def test_plan_revision_scan_does_not_pull_every_geometry_snapshot(self) -> None:
        source = (
            APP / "services" / "cutting_plan_workspace_query_service.py"
        ).read_text(encoding="utf-8")

        fields_block = source.split("_PLAN_FIELDS = (", 1)[1].split(")\n\n", 1)[0]
        self.assertNotIn('"snapshot_json"', fields_block)
        self.assertIn("def _selected_snapshot_json", source)
        self.assertIn('fields=["name", "snapshot_json"]', source)
        self.assertIn(
            "snapshot_json = _selected_snapshot_json([system, uploaded, approved])",
            source,
        )


if __name__ == "__main__":
    unittest.main()
