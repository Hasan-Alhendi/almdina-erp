from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js"
MODULE_ROOT = ROOT / "public" / "js" / "shop_floor_inbox"
API = MODULE_ROOT / "api.js"
STATE = MODULE_ROOT / "state.js"
VIEW_MODEL = MODULE_ROOT / "view_model.js"
RENDERER = MODULE_ROOT / "renderer.js"
INTERACTIONS = MODULE_ROOT / "interactions.js"
DIALOGS = MODULE_ROOT / "dialogs.js"
CONTROLLER = MODULE_ROOT / "controller.js"
CSS = ROOT / "public" / "css" / "shop_floor_responsive.css"


class ShopFloorInboxFrontendArchitectureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.api = API.read_text(encoding="utf-8")
        cls.state = STATE.read_text(encoding="utf-8")
        cls.view_model = VIEW_MODEL.read_text(encoding="utf-8")
        cls.renderer = RENDERER.read_text(encoding="utf-8")
        cls.interactions = INTERACTIONS.read_text(encoding="utf-8")
        cls.dialogs = DIALOGS.read_text(encoding="utf-8")
        cls.controller = CONTROLLER.read_text(encoding="utf-8")
        cls.css = CSS.read_text(encoding="utf-8")

    def test_page_is_thin_composition_root(self) -> None:
        self.assertLessEqual(len(self.page.splitlines()), 100)
        for asset in (
            "api.js",
            "state.js",
            "view_model.js",
            "renderer.js",
            "interactions.js",
            "dialogs.js",
            "controller.js",
        ):
            self.assertIn(f"/assets/almdina_erp/js/shop_floor_inbox/{asset}", self.page)
        self.assertIn("shop_floor_quick_actions.js", self.page)
        self.assertIn("shop_floor_responsive.css", self.page)
        self.assertIn("make_app_page", self.page)
        self.assertIn("ensureCore", self.page)
        self.assertIn("bindActivationLifecycle", self.page)
        self.assertLess(self.page.index("make_app_page"), self.page.index("ensureCore"))
        self.assertNotIn("frappe.call(", self.page)
        self.assertNotIn("shop_floor_query_service", self.page)
        self.assertNotIn("shop_floor_commands", self.page)

    def test_api_is_only_page_transport_owner(self) -> None:
        for endpoint in (
            "get_shop_floor_context",
            "get_my_inbox",
            "get_my_archive",
            "get_handoff_context",
            "handoff_to_next",
        ):
            self.assertIn(endpoint, self.api)
            for other in (
                self.page,
                self.state,
                self.view_model,
                self.renderer,
                self.interactions,
                self.dialogs,
                self.controller,
            ):
                self.assertNotIn(endpoint, other)
        self.assertIn("Frontend.rpc", self.api)
        for forbidden in ("document.", "$(", ".html(", "frappe.call("):
            self.assertNotIn(forbidden, self.api)

    def test_state_owns_mutable_page_state_and_freshness(self) -> None:
        for marker in (
            'mode: "board"',
            "sessionContext: null",
            "boardRows: []",
            "archiveRows: []",
            "routeFilter:",
            "search:",
            "createLatestRequestGate",
            "createLifecycleScope",
            "beginListRequest",
            "snapshot()",
        ):
            self.assertIn(marker, self.state)
        for forbidden in ("frappe.", "document.", "$(", ".html("):
            self.assertNotIn(forbidden, self.state)

    def test_view_model_is_pure_and_server_scoped(self) -> None:
        for marker in (
            "function showsPersonalHistory(",
            "actor_holds_current_stage_role === true",
            "function mergeVisibleList(",
            "function boardRoutes(",
            "function terminalRows(",
            "function board(",
            "function account(",
            "can_start_stage === true",
            "can_handoff_stage === true",
        ):
            self.assertIn(marker, self.view_model)
        for forbidden in ("frappe.", "document.", "$(", ".html(", "System Manager", "Administrator"):
            self.assertNotIn(forbidden, self.view_model)

    def test_renderer_owns_existing_shop_floor_markup(self) -> None:
        for marker in (
            "almdina-sf-tabs",
            "almdina-sf-board-toolbar",
            "almdina-sf-kanban-column",
            "shop-floor-order-card",
            "almdina-sf-account-card",
            "طلبات المسندة",
            "الطلبات المنتهية",
        ):
            self.assertIn(marker, self.renderer)
        for forbidden in ("frappe.call(", "shop_floor_query_service", "shop_floor_commands"):
            self.assertNotIn(forbidden, self.renderer)

    def test_interactions_own_delegated_lifecycle_events(self) -> None:
        for marker in (
            '.almdinaShopFloorInbox',
            '".almdina-sf-tab"',
            '".sf-quick-action"',
            '"#almdina-sf-board-search"',
            '".almdina-sf-kanban-column"',
            "lifecycle.track",
        ):
            self.assertIn(marker, self.interactions)
        self.assertNotIn("frappe.call(", self.interactions)
        self.assertNotIn("shop_floor_query_service", self.interactions)

    def test_dialogs_own_handoff_and_logout_prompts(self) -> None:
        for marker in ("frappe.confirm", "frappe.prompt", "frappe.msgprint", "frappe.show_alert"):
            self.assertIn(marker, self.dialogs)
        self.assertNotIn("frappe.call(", self.dialogs)
        self.assertNotIn("shop_floor_commands", self.dialogs)

    def test_controller_only_orchestrates(self) -> None:
        self.assertLessEqual(len(self.controller.splitlines()), 230)
        for dependency in (
            "AlmdinaShopFloorInboxApi",
            "AlmdinaShopFloorInboxState",
            "AlmdinaShopFloorInboxViewModel",
            "AlmdinaShopFloorInboxRenderer",
            "AlmdinaShopFloorInboxInteractions",
            "AlmdinaShopFloorInboxDialogs",
        ):
            self.assertIn(dependency, self.controller)
        self.assertIn("isCurrentListRequest", self.controller)
        self.assertIn("Promise.all([Api.getInbox(), Api.getArchive()])", self.controller)
        self.assertNotIn("frappe.call(", self.controller)
        self.assertNotIn(".html(", self.controller)
        self.assertNotIn("shop_floor_query_service", self.controller)

    def test_structural_phase_keeps_existing_stylesheet_owner(self) -> None:
        self.assertIn(".almdina-sf-shell", self.css)
        self.assertIn(".almdina-sf-kanban", self.css)
        self.assertNotIn("<style", self.renderer)
        self.assertNotIn("<style", self.controller)


if __name__ == "__main__":
    unittest.main()
