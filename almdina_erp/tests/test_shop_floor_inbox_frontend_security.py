from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js"
MODULE_ROOT = ROOT / "public" / "js" / "shop_floor_inbox"
MODULES = tuple(MODULE_ROOT / name for name in (
    "api.js",
    "state.js",
    "view_model.js",
    "renderer.js",
    "interactions.js",
    "dialogs.js",
    "controller.js",
))


class ShopFloorInboxFrontendSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.sources = {path.name: path.read_text(encoding="utf-8") for path in MODULES}

    def test_browser_surface_has_no_fixed_role_authorization(self) -> None:
        combined = "\n".join([self.page, *self.sources.values()])
        for fixed_role in (
            "System Manager",
            "Administrator",
            "Order Entry",
            "CNC Worker",
            "Edge Banding Worker",
        ):
            self.assertNotIn(fixed_role, combined)
        self.assertNotIn("frappe.user.has_role", combined)
        self.assertNotIn("frappe.user_roles", combined)

    def test_server_flags_remain_authoritative_for_worker_scope_and_actions(self) -> None:
        view_model = self.sources["view_model.js"]
        self.assertIn("actor_holds_current_stage_role === true", view_model)
        self.assertIn("can_start_stage === true", view_model)
        self.assertIn("can_handoff_stage === true", view_model)
        self.assertIn("personal_inbox", view_model)

    def test_transport_methods_are_not_duplicated_across_layers(self) -> None:
        api = self.sources["api.js"]
        for endpoint in (
            "get_shop_floor_context",
            "get_my_inbox",
            "get_my_archive",
            "get_handoff_context",
            "handoff_to_next",
        ):
            self.assertIn(endpoint, api)
            for name, source in self.sources.items():
                if name != "api.js":
                    self.assertNotIn(endpoint, source)
        for name, source in self.sources.items():
            self.assertNotIn("frappe.call(", source, msg=name)

    def test_client_cannot_invent_handoff_target(self) -> None:
        interactions = self.sources["interactions.js"]
        self.assertIn('target !== (context.next || "__ready__")', interactions)
        self.assertIn("actions.handoff(context)", interactions)
        self.assertNotIn("operational_role ===", interactions)
        self.assertNotIn("department_label ===", interactions)


if __name__ == "__main__":
    unittest.main()
