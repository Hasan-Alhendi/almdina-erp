from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"


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

    def test_workspace_assets_load_before_existing_plan_and_cost_presenters(self) -> None:
        manifest = (ROOT / "frontend_assets.py").read_text(encoding="utf-8")
        store = "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"
        plan_api = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js"
        plan_state = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"
        cost_api = "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js"
        cost_state = "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"
        plan_renderer = "public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js"
        cost_presenter = "public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js"

        for asset in (store, plan_api, plan_state, cost_api, cost_state):
            self.assertEqual(manifest.count(asset), 1)
        self.assertLess(manifest.index(store), manifest.index(plan_api))
        self.assertLess(manifest.index(plan_api), manifest.index(plan_state))
        self.assertLess(manifest.index(plan_state), manifest.index(plan_renderer))
        self.assertLess(manifest.index(cost_api), manifest.index(cost_state))
        self.assertLess(manifest.index(cost_state), manifest.index(cost_presenter))

    def test_api_adapters_are_transport_only(self) -> None:
        sources = [
            (
                PUBLIC
                / "cutting_plan"
                / "door_cutting_order_plan_workspace_api.js"
            ).read_text(encoding="utf-8"),
            (
                PUBLIC
                / "costing"
                / "door_cutting_order_cost_workspace_api.js"
            ).read_text(encoding="utf-8"),
        ]
        for source in sources:
            self.assertIn("frappe.call", source)
            self.assertNotIn("querySelector", source)
            self.assertNotIn("MutationObserver", source)
            self.assertNotIn("fields_dict", source)
            self.assertNotIn("frm.doc", source)


if __name__ == "__main__":
    unittest.main()
