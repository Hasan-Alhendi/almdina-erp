from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
DOCUMENT_CONTEXT = ROOT / "public" / "js" / "door_cutting_order_document_context.js"
DEFAULTS = ROOT / "public" / "js" / "door_cutting_order_defaults.js"
DRAWING_PLAN = ROOT / "public" / "js" / "door_cutting_order_drawing_plan_ux.js"
PRODUCTION_ACTIONS = ROOT / "public" / "js" / "shop_floor_order_ux.js"
TOOLBAR_STABILITY = (
    ROOT / "public" / "js" / "door_cutting_order_toolbar_stability_ux.js"
)
DOCUMENT_PRINT = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
)


class TestDocumentContextUxContract(unittest.TestCase):
    def test_document_context_loads_before_every_active_order_feature(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        context = '"public/js/door_cutting_order_document_context.js"'

        self.assertIn(context, hooks)
        for feature in (
            '"public/js/door_cutting_order_defaults.js"',
            '"public/js/door_cutting_order_document_print_presenter.js"',
            '"public/js/door_cutting_order_drawing_plan_ux.js"',
            '"public/js/shop_floor_order_ux.js"',
            '"public/js/order_lifecycle.js"',
            '"public/js/input_stability.js"',
        ):
            self.assertLess(hooks.index(context), hooks.index(feature))

        for retired in (
            '"public/js/door_cutting_order_workflow.js"',
            '"public/js/door_cutting_order_cost_invoice_ux.js"',
            '"public/js/production_stage.js"',
        ):
            self.assertNotIn(retired, hooks)

    def test_identity_transition_clears_every_document_owned_html_region(self) -> None:
        source = DOCUMENT_CONTEXT.read_text(encoding="utf-8")

        for fieldname in (
            "operator_status_strip",
            "pieces_fast_entry",
            "order_cost_invoice_html",
            "plan_control_actions",
            "plan_controls_intro",
            "cutting_plan_html",
        ):
            self.assertIn(f'"{fieldname}"', source)

        self.assertIn("frm._almdinaDocumentContextIdentity === identity", source)
        self.assertIn("_almdinaDocumentContextGeneration", source)
        self.assertIn("return activeForm === frm", source)
        self.assertIn("clearDocumentHtml(frm)", source)
        self.assertIn("resetDocumentState(frm)", source)
        self.assertIn("before_load(frm) { synchronize(frm); }", source)
        self.assertIn("refresh(frm) { synchronize(frm); }", source)

    def test_identity_transition_invalidates_document_scoped_state(self) -> None:
        source = DOCUMENT_CONTEXT.read_text(encoding="utf-8")

        self.assertIn('"_dco_calc_timer"', source)
        self.assertIn("window.clearTimeout(timer)", source)
        self.assertIn("frm._dco_calc_version =", source)
        self.assertIn("frm._dco_selected_piece_rows = new Set()", source)
        self.assertIn("frm._dco_edge_color_map = {}", source)
        self.assertIn("frm._dco_piece_type_restore_token = null", source)
        self.assertIn("frm.__almdina_active_plan_tab = null", source)
        self.assertIn("frm.__almdina_approved_plan_loading = null", source)
        self.assertIn("frm.__almdina_approved_plan_context = null", source)
        self.assertIn("frm.__almdina_stage_type = null", source)
        self.assertIn("frm.__almdina_actor_holds_stage_role = false", source)
        self.assertIn("frm.__almdinaCostSnapshotPromise = null", source)
        self.assertIn("frm.__almdinaPermissionRefreshPromise = null", source)
        self.assertIn("frm.__almdinaProductionActionsPromise = null", source)
        self.assertIn("frm.__almdinaProductionRecoveryPromise = null", source)
        self.assertIn("delete frm._almdina_factory_defaults_loaded", source)

    def test_defaults_ignore_responses_captured_for_another_order(self) -> None:
        source = DEFAULTS.read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count("const identity = context.capture(frm)"), 2)
        self.assertGreaterEqual(
            source.count("if (!context.isCurrent(frm, identity)) return"),
            2,
        )
        self.assertIn("frm.doc.default_edge_type !== requestedType", source)

    def test_production_actions_wait_for_permissions_without_detaching_groups(self) -> None:
        production = PRODUCTION_ACTIONS.read_text(encoding="utf-8")
        toolbar = TOOLBAR_STABILITY.read_text(encoding="utf-8")

        self.assertIn("recoverProductionActions", production)
        self.assertIn('typeof permissions.refresh === "function"', production)
        self.assertIn("Promise.resolve(frappe.call({", production)
        self.assertNotIn("removeEmptyGroups", toolbar)
        self.assertIn('ASYNC_ACTION_GROUPS = new Set(["صالة الإنتاج"])', toolbar)

    def test_drawing_stage_and_recalculation_are_document_scoped(self) -> None:
        source = DRAWING_PLAN.read_text(encoding="utf-8")

        self.assertIn("if (window.AlmdinaDrawingPlanUX) return", source)
        self.assertIn("const requestedStage = frm.doc.current_production_stage", source)
        self.assertIn("!context.isCurrent(frm, identity)", source)
        self.assertIn("frm.doc.current_production_stage !== requestedStage", source)
        self.assertIn("const orderName = frm.doc.name", source)
        self.assertIn("if (!context.isCurrent(frm, identity)) return r.message", source)
        self.assertGreaterEqual(
            source.count("if (!context.isCurrent(frm, identity)) return"),
            2,
        )
        self.assertIn("if (!stageTypeIsCurrent || !context.isCurrent(frm, identity)) return", source)

    def test_customer_documents_wait_for_the_current_order_only(self) -> None:
        source = DOCUMENT_PRINT.read_text(encoding="utf-8")

        self.assertIn("function documentContext()", source)
        self.assertIn("function captureIdentity(frm)", source)
        self.assertIn("function isCurrent(frm, identity)", source)
        self.assertIn("const identity = captureIdentity(frm)", source)
        self.assertGreaterEqual(
            source.count("if (!isCurrent(frm, identity)) return false"),
            2,
        )
        self.assertIn("await ensureProfiles(frm)", source)
        self.assertIn("activeIdentity = captureIdentity(frm)", source)
        self.assertIn("const frm = activeFrm", source)
        self.assertIn("const identity = activeIdentity", source)
        self.assertIn("if (!frm || !isCurrent(frm, identity)) return", source)


if __name__ == "__main__":
    unittest.main()
