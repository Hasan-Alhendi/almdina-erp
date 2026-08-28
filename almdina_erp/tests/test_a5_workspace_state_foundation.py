from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
ASSET_REGISTRY = (
    PUBLIC / "core" / "door_cutting_order_workspace_asset_registry.js"
)


class TestA5WorkspaceStateFoundation(unittest.TestCase):
    def test_store_is_framework_neutral_and_owns_edit_baseline(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_workspace_store.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("frappe.", source)
        self.assertNotIn("frm.doc", source)
        self.assertIn("baseline", source)
        self.assertIn("draft", source)
        self.assertIn("dirty", source)
        self.assertIn("requestId", source)
        self.assertIn("resolveLoad", source)

    def test_plan_and_cost_state_are_not_backed_by_form_business_fields(self) -> None:
        plan = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_workspace_state.js"
        ).read_text(encoding="utf-8")
        cost = (
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_workspace_state.js"
        ).read_text(encoding="utf-8")

        for source in (plan, cost):
            self.assertIn("AlmdinaWorkspaceStore", source)
            self.assertIn("currentIdentity", source)
            self.assertIn("requestId", source)
            self.assertIn("resolveLoad(currentIdentity, requestId", source)

        for legacy_field in (
            "frm.doc.packing_mode",
            "frm.doc.kerf_mm",
            "frm.doc.trim_margin_mm",
            "frm.doc.board_rate_usd",
            "frm.doc.cutting_cost_per_board_usd",
            "frm.doc.cutting_plan_json",
        ):
            self.assertNotIn(legacy_field, plan + cost)

    def test_workspace_loaders_install_single_flight_before_observable_loading(self) -> None:
        paths = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_workspace_state.js",
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_workspace_state.js",
        )

        for path in paths:
            source = path.read_text(encoding="utf-8")
            barrier = source.index("frm[LOAD_PROMISE_KEY] = promise;")
            begin_load = source.index("store.beginLoad(currentIdentity)", barrier)
            loading_dispatch = source.index(
                "dispatch(frm, store.snapshot());",
                begin_load,
            )
            transport_start = source.index("transport = api.load(orderName);", loading_dispatch)
            self.assertLess(barrier, begin_load, path.name)
            self.assertLess(begin_load, loading_dispatch, path.name)
            self.assertLess(loading_dispatch, transport_start, path.name)
            self.assertIn("const pending = frm[LOAD_PROMISE_KEY];", source)
            self.assertIn("await pending;", source)
            self.assertIn("return load(frm, { force: true });", source)
            self.assertIn("function createFlight(frm)", source)

    def test_plan_query_is_capability_scoped_and_contains_no_money(self) -> None:
        path = APP / "services" / "cutting_plan_workspace_query_service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "get_plan_workspace_snapshot"
        )
        calls = [
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
        ]
        self.assertIn("_authorized_order", calls)
        self.assertIn("get_all", calls)
        self.assertLess(calls.index("_authorized_order"), calls.index("get_all"))
        self.assertIn("Capability.VIEW_CUTTING_PLAN", source)
        self.assertIn("Capability.VIEW_SYSTEM_CUTTING_PLAN", source)
        self.assertIn("Capability.VIEW_UPLOADED_CUTTING_PLAN", source)
        self.assertIn("Capability.VIEW_APPROVED_CUTTING_PLAN", source)
        for financial_field in (
            '"board_rate_usd"',
            '"cutting_cost_per_board_usd"',
            '"mdf_cost_usd"',
            '"cutting_cost_usd"',
            '"edge_cost_usd"',
            '"total_cost_usd"',
        ):
            self.assertNotIn(financial_field, source)

    def test_workspace_bootstrap_precedes_lazy_plan_and_cost_presenters(self) -> None:
        manifest = (ROOT / "frontend_assets.py").read_text(encoding="utf-8")
        registry = ASSET_REGISTRY.read_text(encoding="utf-8")
        store = "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"
        editor = "public/js/door_cutting_order/core/door_cutting_order_workspace_field_editor.js"
        plan_api = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js"
        plan_state = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"
        cost_api = "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js"
        cost_state = "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"
        asset_owner = "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"
        plan_renderer = "door_cutting_order_cutting_plan_renderer.js"
        cost_presenter = "door_cutting_order_cost_presenter.js"

        for asset in (store, editor, plan_api, plan_state, cost_api, cost_state, asset_owner):
            self.assertEqual(manifest.count(asset), 1)
        self.assertLess(manifest.index(store), manifest.index(editor))
        self.assertLess(manifest.index(editor), manifest.index(plan_api))
        self.assertLess(manifest.index(plan_api), manifest.index(plan_state))
        self.assertLess(manifest.index(plan_state), manifest.index(asset_owner))
        self.assertLess(manifest.index(cost_api), manifest.index(cost_state))
        self.assertLess(manifest.index(cost_state), manifest.index(asset_owner))

        # Presenters/renderers are no longer initial DocType assets. Their order is
        # protected inside the feature registry that loads them on tab activation.
        self.assertNotIn(plan_renderer, manifest)
        self.assertNotIn(cost_presenter, manifest)
        self.assertIn(plan_renderer, registry)
        self.assertIn(cost_presenter, registry)

    def test_api_adapters_are_transport_only(self) -> None:
        plan_api = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_workspace_api.js"
        ).read_text(encoding="utf-8")
        cost_api = (
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_workspace_api.js"
        ).read_text(encoding="utf-8")
        for source in (plan_api, cost_api):
            self.assertIn("frappe.call", source)
            self.assertNotIn("querySelector", source)
            self.assertNotIn("MutationObserver", source)
            self.assertNotIn("fields_dict", source)
            self.assertNotIn("frm.doc", source)
        self.assertIn("RECALCULATE_METHOD", plan_api)
        self.assertIn("PREVIEW_METHOD", plan_api)
        self.assertIn("COMMIT_PREVIEW_METHOD", plan_api)
        self.assertIn("APPROVE_METHOD", plan_api)
        self.assertIn("recalculate,", plan_api)
        self.assertIn("preview,", plan_api)
        self.assertIn("commitPreview,", plan_api)
        self.assertIn("approve,", plan_api)

    def test_a52_edit_sessions_save_workspace_drafts_not_dco_fields(self) -> None:
        plan = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_edit_session_ux.js"
        ).read_text(encoding="utf-8")
        cost = (
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_edit_session_ux.js"
        ).read_text(encoding="utf-8")

        self.assertIn("AlmdinaPlanWorkspaceAPI", plan)
        self.assertIn("AlmdinaCostWorkspaceAPI", cost)
        self.assertIn("store.beginEdit", plan)
        self.assertIn("store.beginEdit", cost)
        self.assertIn("store.patchDraft", plan)
        self.assertIn("store.patchDraft", cost)
        self.assertIn("state.draft", plan)
        self.assertIn("state.draft", cost)
        self.assertNotIn("frm.reload_doc", plan + cost)
        self.assertNotIn("frappe.call", plan + cost)
        for legacy_read in (
            "frm.doc.packing_mode",
            "frm.doc.cutting_machine_type",
            "frm.doc.kerf_mm",
            "frm.doc.trim_margin_mm",
            "frm.doc.optimization_time_limit_sec",
            "frm.doc.board_rate_usd",
            "frm.doc.cutting_cost_per_board_usd",
        ):
            self.assertNotIn(legacy_read, plan + cost)

    def test_a52_plan_commands_use_workspace_state_and_transport_adapter(self) -> None:
        source = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_controls_ux.js"
        ).read_text(encoding="utf-8")
        self.assertIn("AlmdinaPlanWorkspaceState", source)
        self.assertIn("AlmdinaPlanWorkspaceAPI", source)
        self.assertIn("AlmdinaPlanPreviewSession", source)
        self.assertIn("activeSettings", source)
        self.assertIn("previews.preview(frm, settings)", source)
        self.assertNotIn("transport.recalculate(frm.doc.name, settings)", source)
        self.assertIn("transport.approve(frm.doc.name, source)", source)
        self.assertIn("refreshWorkspaceOwners", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("frm.reload_doc", source)
        self.assertNotIn('frm.set_value("packing_mode"', source)
        self.assertNotIn("RECALCULATE_METHOD", source)
        self.assertNotIn("PREVIEW_METHOD", source)
        self.assertNotIn("COMMIT_PREVIEW_METHOD", source)
        self.assertNotIn("APPROVE_METHOD", source)

    def test_a52_presenter_adapters_are_store_first_and_transport_free(self) -> None:
        plan = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_workspace_presenter_adapter.js"
        ).read_text(encoding="utf-8")
        cost = (
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_workspace_presenter_adapter.js"
        ).read_text(encoding="utf-8")

        self.assertIn("AlmdinaPlanWorkspaceState", plan)
        self.assertIn("AlmdinaCostWorkspaceState", cost)
        self.assertIn("getPlanForTab", plan)
        self.assertIn("payload.order", cost)
        self.assertIn("legacySummaryProjection", plan)
        self.assertIn("production_dxf", plan)
        self.assertNotIn("frappe.call", plan + cost)
        self.assertNotIn("get_approved_cutting_plan_snapshot", plan)
        self.assertNotIn("ignore_permissions", plan + cost)

    def test_a52_pending_renderers_do_not_start_workspace_reads(self) -> None:
        plan = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_workspace_presenter_adapter.js"
        ).read_text(encoding="utf-8")
        cost = (
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_workspace_presenter_adapter.js"
        ).read_text(encoding="utf-8")

        plan_pending = plan[
            plan.index("function renderPending(frm)"):
            plan.index("function ready(frm)")
        ]
        cost_pending = cost[
            cost.index("function renderPending(frm)"):
            cost.index("function install()")
        ]
        self.assertNotIn("ensureLoad(frm)", plan_pending)
        self.assertNotIn(".load(", plan_pending)
        self.assertNotIn("ensureLoad", cost)
        self.assertNotIn(".load(", cost_pending)

    def test_a52_legacy_plan_tabs_are_visual_only(self) -> None:
        source = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_tabs_ux.js"
        ).read_text(encoding="utf-8")
        self.assertIn("window.AlmdinaPlanTabsUX", source)
        self.assertIn("renderDualTabs", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("get_approved_cutting_plan_snapshot", source)
        self.assertNotIn('frappe.ui.form.on("Door Cutting Order"', source)
        self.assertIn("pure visual owner", source)

    def test_a52_presenter_adapter_order_preserves_existing_visual_owners(self) -> None:
        registry = ASSET_REGISTRY.read_text(encoding="utf-8")
        cost_presenter = "door_cutting_order_cost_presenter.js"
        cost_adapter = "door_cutting_order_cost_workspace_presenter_adapter.js"
        cost_permissions = "door_cutting_order_cost_permissions_ux.js"
        plan_tabs = "door_cutting_order_plan_tabs_ux.js"
        plan_adapter = "door_cutting_order_plan_workspace_presenter_adapter.js"
        plan_bootstrap = "door_cutting_order_plan_surface_bootstrap.js"

        for asset in (
            cost_presenter,
            cost_adapter,
            cost_permissions,
            plan_tabs,
            plan_adapter,
            plan_bootstrap,
        ):
            self.assertEqual(registry.count(asset), 1)
        self.assertLess(registry.index(cost_presenter), registry.index(cost_adapter))
        self.assertLess(registry.index(cost_adapter), registry.index(cost_permissions))
        self.assertLess(registry.index(plan_tabs), registry.index(plan_adapter))
        self.assertLess(registry.index(plan_adapter), registry.index(plan_bootstrap))

    def test_a52_detached_editor_does_not_use_frappe_model_mutation(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_workspace_field_editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("AlmdinaWorkspaceFieldEditor", source)
        self.assertIn("onPatch", source)
        self.assertIn('.control-input-wrapper', source)
        self.assertIn('.control-input, .control-value', source)
        self.assertNotIn("frappe.model.set_value", source)
        self.assertNotIn("frm.set_value", source)
        self.assertNotIn("frm.save", source)
        self.assertNotIn("frappe.call", source)


if __name__ == "__main__":
    unittest.main()
