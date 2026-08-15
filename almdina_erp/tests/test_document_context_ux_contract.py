from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
DOCUMENT_CONTEXT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_document_context.js"
)
DEFAULTS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_defaults.js"
)
DRAWING_PLAN = ROOT / "public" / "js" / "door_cutting_order_drawing_plan_ux.js"
PRODUCTION_ACTIONS = ROOT / "public" / "js" / "shop_floor_order_ux.js"
PERMISSION_REFRESH = (
    ROOT / "public" / "js" / "door_cutting_order_permission_refresh_ux.js"
)
TOOLBAR_STABILITY = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_toolbar_stability_ux.js"
)
DOCUMENT_PRINT = (
    ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
)


class TestDocumentContextUxContract(unittest.TestCase):
    def test_document_context_loads_before_every_active_order_feature(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        context = '"public/js/door_cutting_order/core/door_cutting_order_document_context.js"'

        self.assertIn(context, hooks)
        for feature in (
            '"public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js"',
            '"public/js/door_cutting_order_document_print_presenter.js"',
            '"public/js/door_cutting_order_drawing_plan_ux.js"',
            '"public/js/shop_floor_order_ux.js"',
            '"public/js/door_cutting_order/core/order_lifecycle.js"',
            '"public/js/input_stability.js"',
        ):
            self.assertLess(hooks.index(context), hooks.index(feature))

        # The context owns the surface-readiness registry that the permission
        # bundle registers into.
        self.assertLess(
            hooks.index(context),
            hooks.index('"public/js/permission_context.js"'),
        )

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
        self.assertIn("ensureStageContext(frm)", source)

    def test_stage_context_is_loaded_before_stage_gated_surfaces_render(self) -> None:
        plan = (ROOT / "public" / "js" / "door_cutting_order_plan_ux.js").read_text(
            encoding="utf-8"
        )
        controls = (
            ROOT / "public" / "js" / "door_cutting_order_plan_controls_ux.js"
        ).read_text(encoding="utf-8")

        self.assertIn("ensureStageContext(frm).then", plan)
        self.assertIn("almdina:stage-context-ready", plan)
        self.assertIn("function canOperatePlanEngine(frm)", plan)
        self.assertIn("function canUseDocumentPlanActions(frm)", plan)
        # Upload / export / print stay available on an active stage; the gate is
        # the capability plus the stage's operational role, never the stage alone.
        self.assertIn(
            "return Boolean(frm && frm.doc) && canMutateCurrentStage(frm);",
            plan,
        )
        self.assertIn(
            "canUseDocumentPlanActions(frm) && hasUploadCapability(frm)",
            plan,
        )
        self.assertIn("frm.doc.current_production_stage) return true;", plan)
        self.assertIn("ensureStageContext(frm).then", controls)
        self.assertIn("isStageContextPending", controls)
        self.assertIn("canMutateCurrentStage(frm)", controls)
        self.assertIn(
            "Only the packing-algorithm fields open here",
            controls,
        )
        self.assertIn("function applyOptimizerFieldAccess(frm)", controls)
        self.assertNotIn("function canEditOptimizerSettings(frm)", plan)

    def test_cutting_algorithm_surface_never_waits_for_an_order_edit_session(self) -> None:
        context = DOCUMENT_CONTEXT.read_text(encoding="utf-8")
        plan = (ROOT / "public" / "js" / "door_cutting_order_plan_ux.js").read_text(
            encoding="utf-8"
        )
        controls = (
            ROOT / "public" / "js" / "door_cutting_order_plan_controls_ux.js"
        ).read_text(encoding="utf-8")
        drawing = DRAWING_PLAN.read_text(encoding="utf-8")

        self.assertIn("function canTuneCuttingAlgorithm(frm)", context)
        self.assertIn("function canPreviewCuttingAlgorithm(frm)", context)
        for module in (plan, controls, drawing):
            self.assertIn("canTuneCuttingAlgorithm", module)
            # The order edit session belongs to the document, not to the plan
            # engine, so a role holding only the algorithm grant still works.
            self.assertNotIn("frappe.almdina.orderCanEdit", module)

    def test_algorithm_preview_stays_open_at_every_stage_without_persisting(self) -> None:
        drawing = DRAWING_PLAN.read_text(encoding="utf-8")

        self.assertIn("simulate_optimizer_plan", drawing)
        self.assertIn("function canPreviewDrawingOptimizer(frm", drawing)
        self.assertIn("function canCommitDrawingPlan(frm)", drawing)
        # Preview never writes, so it must not reload or dirty the document.
        preview = drawing.split("function previewCurrentOrder(frm, packingMode)", 1)[
            1
        ].split("function recalcCurrentOrder", 1)[0]
        self.assertNotIn("reload_doc", preview)
        self.assertNotIn("frm.doc.packing_mode =", preview)
        self.assertIn("معاينة", preview)

    def test_finished_route_is_not_treated_as_pre_production(self) -> None:
        source = DOCUMENT_CONTEXT.read_text(encoding="utf-8")
        self.assertIn('return !String(frm.doc.production_path || "").trim();', source)
        self.assertIn("غادر مراحل الإنتاج النشطة", source)

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
        self.assertIn("frm.__almdina_stage_context_ready = false", source)
        self.assertIn("ensureStageContext", source)
        self.assertIn("almdina:stage-context-ready", source)
        self.assertIn("holdsStageOperationalRole", source)

    def test_defaults_ignore_responses_captured_for_another_order(self) -> None:
        source = DEFAULTS.read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count("const identity = context.capture(frm)"), 2)
        self.assertGreaterEqual(
            source.count("if (!context.isCurrent(frm, identity)) return"),
            2,
        )
        self.assertIn("frm.doc.default_edge_type !== requestedType", source)

    def test_production_actions_wait_for_central_permission_refresh_without_detaching_groups(self) -> None:
        production = PRODUCTION_ACTIONS.read_text(encoding="utf-8")
        permission_refresh = PERMISSION_REFRESH.read_text(encoding="utf-8")
        toolbar = TOOLBAR_STABILITY.read_text(encoding="utf-8")

        self.assertIn("recoverProductionActions", production)
        self.assertIn("capabilitiesResolved", production)
        self.assertIn("PermissionRefreshUX is the sole owner of the permission request", production)
        self.assertNotIn('typeof permissions.refresh === "function"', production)
        self.assertIn("function refreshPermissions(frm)", permission_refresh)
        self.assertIn('typeof permissions.refresh === "function"', permission_refresh)
        self.assertIn("production.reconcileProductionActions(frm)", permission_refresh)
        self.assertIn("Promise.resolve(frappe.call({", production)
        self.assertNotIn("removeEmptyGroups", toolbar)
        self.assertIn('ASYNC_ACTION_GROUPS = new Set(["صالة الإنتاج"])', toolbar)

    def test_drawing_stage_and_recalculation_are_document_scoped(self) -> None:
        source = DRAWING_PLAN.read_text(encoding="utf-8")

        self.assertIn("if (window.AlmdinaDrawingPlanUX) return", source)
        self.assertIn("context.ensureStageContext(frm)", source)
        self.assertIn("scheduleDrawingPanel(frm)", source)
        self.assertIn("almdina:stage-context-ready", source)
        self.assertIn("const orderName = frm.doc.name", source)
        self.assertIn("if (!context.isCurrent(frm, identity)) return r.message", source)
        self.assertIn("if (!context.isCurrent(frm, identity)) return", source)
        self.assertIn("if (!stageTypeIsCurrent || !context.isCurrent(frm, identity)) return", source)

    def test_asynchronous_stage_context_is_kept_for_its_own_document(self) -> None:
        source = DOCUMENT_CONTEXT.read_text(encoding="utf-8")

        # Rendering still requires the active form, but storing a reply must not:
        # dropping it forced the user to refresh the page again.
        self.assertIn("function isSameDocument(frm, token)", source)
        self.assertIn("if (!isSameDocument(frm, token)) return false;", source)
        self.assertNotIn("if (!isCurrent(frm, token)) return false;", source)

    def test_unrendered_surfaces_are_retried_without_a_page_reload(self) -> None:
        source = DOCUMENT_CONTEXT.read_text(encoding="utf-8")

        self.assertIn("function registerSurface(name, probe)", source)
        self.assertIn("function settleSurfaces(frm, attempt)", source)
        self.assertIn("function scheduleSettle(frm, attempt = 0)", source)
        self.assertIn("SETTLE_DELAYS", source)
        self.assertIn('"__almdinaSurfaceSettleTimer"', source)

        for owner, probe in (
            ("door_cutting_order_plan_surface_bootstrap.js", '"cutting-plan"'),
            ("door_cutting_order_permission_refresh_ux.js", '"order-permission-surfaces"'),
            ("shop_floor_order_ux.js", '"production-actions"'),
            ("permission_context.js", '"order-protected-modules"'),
        ):
            owner_source = (ROOT / "public" / "js" / owner).read_text(encoding="utf-8")
            self.assertIn("registerSurface(", owner_source, owner)
            self.assertIn(probe, owner_source, owner)

    def test_protected_order_modules_load_on_every_visit(self) -> None:
        source = (ROOT / "public" / "js" / "permission_context.js").read_text(
            encoding="utf-8"
        )

        # A one-shot poll left later navigations without the protected modules.
        self.assertIn('frappe.router.on("change"', source)
        self.assertIn("function ensureOrderModules()", source)
        self.assertIn("function orderModulesLoaded()", source)

    def test_customer_documents_wait_for_the_current_order_only(self) -> None:
        source = DOCUMENT_PRINT.read_text(encoding="utf-8")

        self.assertIn("function documentContext()", source)
        self.assertIn("function captureIdentity(frm)", source)
        self.assertIn("function isCurrent(frm, identity)", source)
        self.assertIn("const documentIdentity = captureIdentity(frm)", source)
        self.assertGreaterEqual(
            source.count("if (!isCurrent(frm, documentIdentity)) return false"),
            2,
        )
        self.assertIn("await Promise.all([", source)
        self.assertIn("ensureProfiles(frm)", source)
        self.assertIn("resolvePrintIdentity()", source)
        self.assertIn("activeIdentity = captureIdentity(frm)", source)
        self.assertIn("const frm = activeFrm", source)
        self.assertIn("const identity = activeIdentity", source)
        self.assertIn("if (!frm || !isCurrent(frm, identity)) return", source)


if __name__ == "__main__":
    unittest.main()
