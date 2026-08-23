from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PAGES = ROOT / "almdina_erp" / "page"
PUBLIC = ROOT / "public" / "js"
FOUNDATION = PUBLIC / "frontend_foundation.js"
LIFECYCLE = PUBLIC / "page_revisit_refresh.js"
SHOP_CONTROLLER = PUBLIC / "shop_floor_inbox" / "controller.js"
SHOP_STATE = PUBLIC / "shop_floor_inbox" / "state.js"
SHOP_RENDERER = PUBLIC / "shop_floor_inbox" / "renderer.js"
MASTER_PAGE = PAGES / "factory_master_data" / "factory_master_data.js"
DOOR_DRAWING = PAGES / "door_drawing" / "door_drawing.js"
DCO_CONTEXT = PUBLIC / "door_cutting_order" / "core" / "door_cutting_order_document_context.js"
DCO_LIST = PUBLIC / "door_cutting_order" / "list_view" / "door_cutting_order_list.js"
DCO_ACTION_SURFACES = (
    PUBLIC / "door_cutting_order" / "production" / "shop_floor_order_ux.js",
    PUBLIC / "door_cutting_order" / "core" / "door_cutting_order_revision_ux.js",
    PUBLIC / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_controls_ux.js",
    PUBLIC / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_context_actions_ux.js",
    PUBLIC / "door_cutting_order" / "cutting_plan" / "secure_dxf_export.js",
    PUBLIC / "door_cutting_order" / "cutting_plan" / "secure_dxf_upload.js",
    PUBLIC / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js",
    PUBLIC / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_multi_edge_ux.js",
)
REPLACEMENT = PUBLIC / "replacement_piece.js"
CONTRACT = REPO / "docs" / "reference" / "15_FRONTEND_LIFECYCLE_CLOSURE.md"
ADR = REPO / "docs" / "adr" / "ADR-002-FRONTEND-ACTIVATION-LIFECYCLE.md"


class ProjectFrontendLifecycleContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page_files = sorted(PAGES.glob("*/*.js"))
        cls.page_sources = {path.parent.name: path.read_text(encoding="utf-8") for path in cls.page_files}
        cls.contract = CONTRACT.read_text(encoding="utf-8")
        cls.adr = ADR.read_text(encoding="utf-8")

    def test_all_custom_frappe_pages_are_in_the_canonical_inventory(self) -> None:
        expected = {
            "door_drawing",
            "factory_approval_queue",
            "factory_master_data",
            "factory_performance_benchmark",
            "factory_permissions",
            "factory_plan_archive",
            "factory_production_settings",
            "factory_stock_settings",
            "factory_system_preflight",
            "factory_workforce",
            "shop_floor_inbox",
        }
        self.assertEqual(set(self.page_sources), expected)
        for page in expected:
            self.assertIn(page.replace("_", "-"), self.contract)

    def test_every_page_family_reaches_the_shared_activation_contract(self) -> None:
        for page, source in self.page_sources.items():
            with self.subTest(page=page):
                self.assertIn("bindActivationLifecycle", source)
                self.assertNotIn("refreshOnRevisit", source)

        lifecycle = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn("active visit", lifecycle)
        self.assertIn("isCurrentPage", lifecycle)
        self.assertIn("onDeactivate", lifecycle)
        self.assertIn("$wrapper.off(EVENT_NAMESPACE)", lifecycle)

    def test_shared_assets_load_before_page_features(self) -> None:
        manifest = runpy.run_path(str(ROOT / "frontend_assets.py"))
        assets = manifest["app_include_js"]
        foundation = "/assets/almdina_erp/js/frontend_foundation.js"
        lifecycle = "/assets/almdina_erp/js/page_revisit_refresh.js"
        self.assertLess(assets.index(foundation), assets.index(lifecycle))

        for page in ("factory_permissions", "factory_workforce", "factory_production_settings", "shop_floor_inbox"):
            source = self.page_sources[page]
            self.assertLess(source.index("make_app_page"), source.index("ensureCore"))

    def test_shop_floor_separates_mount_from_active_visit(self) -> None:
        controller = SHOP_CONTROLLER.read_text(encoding="utf-8")
        state = SHOP_STATE.read_text(encoding="utf-8")
        renderer = SHOP_RENDERER.read_text(encoding="utf-8")
        page = self.page_sources["shop_floor_inbox"]

        self.assertIn("onActivate: refresh", controller)
        self.assertIn("onDeactivate: deactivate", controller)
        self.assertIn("activation.isActive()", controller)
        self.assertIn("trackActionDialog", controller)
        self.assertIn("deactivate()", state)
        self.assertIn("current.sessionContext = null", state)
        self.assertIn("const page = wrapper.page", renderer)
        self.assertNotIn("frappe.ui.make_app_page", renderer)
        self.assertIn("نجهّز صالة الإنتاج", page)

    def test_master_data_preserves_dirty_state_and_invalidates_reads(self) -> None:
        source = MASTER_PAGE.read_text(encoding="utf-8")
        self.assertIn("this.state.editor && this.state.editor.dirty", source)
        self.assertIn("deactivate()", source)
        self.assertIn("this.state.requestId += 1", source)
        self.assertIn("!this.isActive()", source)
        self.assertIn("onDeactivate: () => workflowPage.deactivate()", source)
        self.assertIn("this.modalOwner.closeAll()", source)

    def test_drawing_route_open_is_activation_generation_guarded(self) -> None:
        source = DOOR_DRAWING.read_text(encoding="utf-8")
        self.assertIn("owner.generation() !== generation", source)
        self.assertIn("__almdinaDocumentationShowRequest", source)
        self.assertIn("active.suspend()", source)
        self.assertIn("onDeactivate: () => deactivate(wrapper)", source)
        self.assertNotIn("hide.aldDocumentation", source)

    def test_form_and_list_async_commits_require_the_active_surface(self) -> None:
        dco_list = DCO_LIST.read_text(encoding="utf-8")
        replacement = REPLACEMENT.read_text(encoding="utf-8")
        dco_context = DCO_CONTEXT.read_text(encoding="utf-8")

        self.assertIn("function listIsActive", dco_list)
        self.assertIn("installActivationLifecycle", dco_list)
        self.assertIn("onDeactivate: () => deactivateList(listview)", dco_list)
        self.assertIn("_dcoActionDialogs", dco_list)
        self.assertIn("function formIsCurrent", replacement)
        self.assertIn("window.cur_frm === frm", replacement)
        self.assertIn("modalOwner.closeAll()", replacement)
        self.assertIn("__almdinaReplacementNeedsReload", replacement)
        self.assertIn("generation", dco_context)
        self.assertIn("function isCurrent", dco_context)
        for path in DCO_ACTION_SURFACES:
            with self.subTest(action_surface=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("isCurrent", source)

    def test_hidden_bootstrap_failures_and_owned_dialogs_are_visit_scoped(self) -> None:
        foundation = FOUNDATION.read_text(encoding="utf-8")
        self.assertIn("function createDialogOwner()", foundation)
        self.assertIn("closeAll", foundation)

        for page in ("factory_permissions", "factory_workforce", "factory_production_settings", "shop_floor_inbox"):
            source = self.page_sources[page]
            with self.subTest(page=page):
                self.assertIn("__almdinaFrontendBootstrapRetry", source)
                self.assertIn("frappe.container.page !== wrapper", source)

        for page in ("factory_approval_queue", "factory_master_data", "factory_plan_archive", "factory_stock_settings"):
            source = self.page_sources[page]
            with self.subTest(page=page):
                self.assertIn("modalOwner", source)
                self.assertIn("closeAll()", source)

    def test_query_report_javascript_has_no_custom_async_lifecycle(self) -> None:
        for path in (ROOT / "almdina_erp" / "report").glob("*/*.js"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(report=path.parent.name):
                self.assertNotIn("frappe.call", source)
                self.assertNotIn("MutationObserver", source)
                self.assertNotIn("setTimeout", source)

    def test_decision_is_explicitly_structural_and_scope_neutral(self) -> None:
        for marker in (
            "Accepted",
            "Frappe v16",
            "dirty state",
            "Special Shape Documentation",
        ):
            self.assertIn(marker, self.adr)
        for marker in (
            "UI redesign",
            "business/authorization/workflow/schema changes",
            "product-scope expansion",
            "Definition of Done",
        ):
            self.assertIn(marker, self.contract)


if __name__ == "__main__":
    unittest.main()
