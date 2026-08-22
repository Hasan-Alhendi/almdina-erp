from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
APP = ROOT / "almdina_erp"


class TestWorkspaceFreshnessArchitecture(unittest.TestCase):
    def test_store_owns_generic_freshness_without_frappe_or_form_policy(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_workspace_store.js"
        ).read_text(encoding="utf-8")
        self.assertIn('freshness: "unknown"', source)
        self.assertIn('state.freshness = "stale"', source)
        self.assertIn("staleReason", source)
        self.assertIn("invalidatedAt", source)
        self.assertIn("function invalidate", source)
        self.assertIn("function isFresh", source)
        self.assertNotIn("frappe.", source)
        self.assertNotIn("frm.doc", source)
        self.assertNotIn("special_shape", source)

    def test_coordinator_is_reusable_and_contains_no_dco_business_rules(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_workspace_sync_coordinator.js"
        ).read_text(encoding="utf-8")
        for contract in (
            "function register",
            "function invalidate",
            "async function refresh",
            "async function reconcile",
            "function syncDocumentModified",
            '"almdina:workspace-freshness-changed"',
        ):
            self.assertIn(contract, source)
        for forbidden in (
            "special_shape_price_status",
            "piece_type",
            "width_cm",
            "length_cm",
            "qty",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("frappe.call", source)

    def test_dco_policy_owns_dependency_rules_not_transport_or_rendering(self) -> None:
        source = (
            PUBLIC
            / "order_entry"
            / "door_cutting_order_mutation_impact_policy.js"
        ).read_text(encoding="utf-8")
        self.assertIn("SPECIAL_PRICE_BASIS_FIELDS", source)
        for fieldname in ("width_cm", "length_cm", "qty", "piece_type"):
            self.assertIn(f'"{fieldname}"', source)
        self.assertIn("AlmdinaWorkspaceSyncCoordinator", source)
        self.assertIn('recordImpact(frm, ["plan", "cost"]', source)
        self.assertIn("special_price_basis_changed", source)
        self.assertIn("plan_recalculation_required", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("innerHTML", source)

    def test_plan_and_cost_state_register_with_shared_coordinator(self) -> None:
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
        for name, source in (("plan", plan), ("cost", cost)):
            self.assertIn("function invalidate", source)
            self.assertIn('current.freshness !== "stale"', source)
            self.assertIn("AlmdinaWorkspaceSyncCoordinator", source)
            self.assertIn(f'coordinator.register("{name}"', source)

    def test_cost_document_version_is_part_of_canonical_read_contract(self) -> None:
        backend = (
            APP / "services" / "cost_permission_service.py"
        ).read_text(encoding="utf-8")
        state = (
            PUBLIC
            / "costing"
            / "door_cutting_order_cost_workspace_state.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"order_modified": _document_version(order)', backend)
        self.assertIn("payload && payload.order_modified", state)
        self.assertIn("coordinator.syncDocumentModified", state)
        self.assertNotIn("frm.reload_doc", state)

    def test_preview_cost_is_in_memory_and_gated_by_view_costs(self) -> None:
        backend = (
            APP / "services" / "cutting_plan_preview_service.py"
        ).read_text(encoding="utf-8")
        presenter = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_preview_presenter.js"
        ).read_text(encoding="utf-8")
        self.assertIn("frappe.copy_doc(source_plan)", backend)
        self.assertIn("cutting_plan_capability_allowed", backend)
        self.assertIn("Capability.VIEW_COSTS", backend)
        self.assertIn("if include_cost:", backend)
        self.assertIn("apply_plan_costs(", backend)
        self.assertIn('summary["cost"] = _preview_cost_summary(plan)', backend)
        self.assertIn('"total_cost_usd": flt(plan.total_cost_usd)', backend)
        self.assertIn("const cost = summary && summary.cost", presenter)
        self.assertIn("if (cost)", presenter)
        self.assertIn("تكلفة الخطة المتوقعة", presenter)
        self.assertIn("هذه الخطة وتكلفتها المعروضة للمعاينة فقط", presenter)

    def test_committed_preview_reconciles_plan_then_cost(self) -> None:
        source = (
            PUBLIC
            / "cutting_plan"
            / "door_cutting_order_plan_preview_edit_ux.js"
        ).read_text(encoding="utf-8")
        self.assertIn("AlmdinaWorkspaceSyncCoordinator", source)
        self.assertIn('coordinator.invalidate(frm, ["plan", "cost"], "plan_changed")', source)
        self.assertIn('await coordinator.refresh(frm, ["plan", "cost"]', source)
        self.assertIn("تم حفظ خطة المعاينة وتحديث التكلفة المرتبطة بها", source)

    def test_freshness_ux_never_owns_persistence(self) -> None:
        source = (
            PUBLIC / "core" / "door_cutting_order_workspace_freshness_ux.js"
        ).read_text(encoding="utf-8")
        self.assertIn("بانتظار التحديث", source)
        self.assertIn("السعر السابق", source)
        self.assertIn("هناك معاينة خطة غير محفوظة", source)
        self.assertIn("data-almdina-cost-freshness", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("frm.save", source)
        self.assertNotIn("frm.set_value", source)

    def test_asset_order_keeps_generic_core_before_feature_policy_and_late_ux(self) -> None:
        manifest = (ROOT / "frontend_assets.py").read_text(encoding="utf-8")
        store = "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js"
        coordinator = "public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js"
        plan_state = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"
        cost_state = "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js"
        policy = "public/js/door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js"
        presenter = "public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js"
        visual = "public/js/door_cutting_order/core/door_cutting_order_plan_cost_workspace_visual_ux.js"
        freshness_ux = "public/js/door_cutting_order/core/door_cutting_order_workspace_freshness_ux.js"

        for asset in (
            store,
            coordinator,
            plan_state,
            cost_state,
            policy,
            freshness_ux,
        ):
            self.assertEqual(manifest.count(asset), 1)
        self.assertLess(manifest.index(store), manifest.index(coordinator))
        self.assertLess(manifest.index(coordinator), manifest.index(plan_state))
        self.assertLess(manifest.index(coordinator), manifest.index(cost_state))
        self.assertLess(manifest.index(cost_state), manifest.index(policy))
        self.assertLess(manifest.index(policy), manifest.index(presenter))
        self.assertLess(manifest.index(visual), manifest.index(freshness_ux))


if __name__ == "__main__":
    unittest.main()
