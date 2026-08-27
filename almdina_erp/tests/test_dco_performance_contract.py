from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
ASSETS = ROOT / "frontend_assets.py"
PERMISSION_CONTEXT = ROOT / "public" / "js" / "permission_context.js"


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
        self.assertIn("await registry.ensureForTab(fieldname);", lifecycle)
        self.assertLess(
            lifecycle.index("await registry.ensureForTab(fieldname);"),
            lifecycle.index("return owner.activateCurrent(frm, options);"),
        )
        self.assertIn("activationStillCurrent", lifecycle)

    def test_heavy_plan_and_cost_ui_are_not_in_dco_critical_manifest(self) -> None:
        source = ASSETS.read_text(encoding="utf-8")
        app_include, doctype_section = source.split("doctype_js =", 1)
        dco = doctype_section.split('"Door Cutting Order": [', 1)[1].split(
            '],\n    "Edge Banding Type"', 1
        )[0]

        # Lightweight application state remains deterministic and eager.
        for asset in (
            "door_cutting_order_plan_workspace_api.js",
            "door_cutting_order_plan_workspace_state.js",
            "door_cutting_order_cost_workspace_api.js",
            "door_cutting_order_cost_workspace_state.js",
            "door_cutting_order_workspace_asset_registry.js",
            "door_cutting_order_workspace_asset_status_ux.js",
            "door_cutting_order_workspace_activation_lifecycle.js",
        ):
            self.assertIn(asset, dco)

        # Heavy presentation/actions must not regress into first-open execution.
        for asset in (
            "door_cutting_order_cutting_plan_renderer.js",
            "door_cutting_order_plan_controls_ux.js",
            "door_cutting_order_plan_content_ux.js",
            "door_cutting_order_plan_workspace_presenter_adapter.js",
            "door_cutting_order_plan_surface_bootstrap.js",
            "door_cutting_order_plan_edit_session_ux.js",
            "secure_dxf_upload.js",
            "secure_dxf_export.js",
            "door_cutting_order_cost_presenter.js",
            "door_cutting_order_cost_workspace_presenter_adapter.js",
            "door_cutting_order_cost_permissions_ux.js",
            "door_cutting_order_financial_documents_ux.js",
            "door_cutting_order_customer_invoice_toolbar_ux.js",
            "door_cutting_order_cost_edit_session_ux.js",
        ):
            self.assertNotIn(asset, dco)

        self.assertNotIn("secure_dxf_export.js", app_include)
        self.assertNotIn("door_cutting_order_drawing_plan_ux.js", app_include)

    def test_workspace_asset_registry_owns_batched_feature_loading(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_workspace_asset_registry.js"
        ).read_text(encoding="utf-8")

        self.assertIn('activationField: "results_tab"', source)
        self.assertIn('activationField: "cost_tab"', source)
        self.assertIn("frontend.requireAssets(assets)", source)
        self.assertIn("const pending = new Map()", source)
        self.assertIn('emit(name, "loading")', source)
        self.assertIn('emit(name, "loaded")', source)
        self.assertIn('emit(name, "failed", error)', source)
        self.assertIn("door_cutting_order_plan_surface_bootstrap.js", source)
        self.assertIn("door_cutting_order_cost_presenter.js", source)

    def test_permission_recovery_does_not_pull_lazy_features(self) -> None:
        source = PERMISSION_CONTEXT.read_text(encoding="utf-8")

        self.assertIn("ORDER_CORE_GLOBALS", source)
        self.assertIn('"AlmdinaOrderPermissionRefreshUX"', source)
        self.assertIn('"AlmdinaOrderTabPermissionsUX"', source)
        self.assertNotIn("AlmdinaOrderCostUX", source)
        self.assertNotIn("AlmdinaCustomerInvoiceToolbarUX", source)
        self.assertNotIn("PLAN_SURFACE_MODULE", source)
        self.assertNotIn("waitForGlobal", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("frappe.require", source)

    def test_hidden_lazy_surfaces_are_not_permission_readiness_failures(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_permission_refresh_ux.js"
        ).read_text(encoding="utf-8")

        self.assertIn("const activeTab = currentTabFieldname(frm);", source)
        self.assertIn('activeTab === "cost_tab"', source)
        self.assertIn('activeTab === "results_tab"', source)
        self.assertIn("Hidden Plan", source)

    def test_activation_adapter_loads_after_workspace_state_and_asset_registry(self) -> None:
        source = ASSETS.read_text(encoding="utf-8")
        plan_state = source.index("door_cutting_order_plan_workspace_state.js")
        cost_state = source.index("door_cutting_order_cost_workspace_state.js")
        registry = source.index("door_cutting_order_workspace_asset_registry.js")
        status = source.index("door_cutting_order_workspace_asset_status_ux.js")
        lifecycle = source.index("door_cutting_order_workspace_activation_lifecycle.js")
        mutation_policy = source.index("door_cutting_order_mutation_impact_policy.js")

        self.assertLess(plan_state, registry)
        self.assertLess(cost_state, registry)
        self.assertLess(registry, status)
        self.assertLess(status, lifecycle)
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
