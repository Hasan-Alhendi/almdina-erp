from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_PATH = ROOT / "almdina_erp" / "application" / "shop_floor" / "commands.py"
ADAPTER_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"
INFRA_ROOT = ROOT / "almdina_erp" / "infrastructure" / "frappe"
REPOSITORY_PATH = INFRA_ROOT / "shop_floor_command_repository.py"
STAGE_REPOSITORY_PATH = INFRA_ROOT / "production_stage_repository.py"
ORDER_REPOSITORY_PATH = INFRA_ROOT / "order_tracking_repository.py"
EVENT_REPOSITORY_PATH = INFRA_ROOT / "production_event_repository.py"
AUTHORIZATION_PATH = INFRA_ROOT / "shop_floor_authorization.py"
HOOKS_PATH = ROOT / "hooks.py"


class TestShopFloorCommandArchitecture(unittest.TestCase):
    def test_application_commands_do_not_import_frappe_or_services(self) -> None:
        source = APPLICATION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".services", source)
        self.assertNotIn(".infrastructure", source)
        self.assertIn("class ShopFloorCommandPort", source)

    def test_command_repository_composes_focused_frappe_adapters(self) -> None:
        source = REPOSITORY_PATH.read_text(encoding="utf-8")
        self.assertIn("class FrappeShopFloorCommandRepository", source)
        self.assertNotIn("import frappe", source)
        self.assertNotIn("shop_floor_gateway", source)
        self.assertNotIn("stage.save(ignore_permissions=True)", source)
        for module_name in (
            "shop_floor_authorization",
            "production_stage_repository",
            "order_tracking_repository",
            "production_event_repository",
        ):
            self.assertIn(module_name, source)
        self.assertNotIn("stock_execution_gateway", source)
        self.assertNotIn("remnant_execution_gateway", source)

    def test_frappe_writes_live_in_focused_infrastructure_modules(self) -> None:
        stage_source = STAGE_REPOSITORY_PATH.read_text(encoding="utf-8")
        order_source = ORDER_REPOSITORY_PATH.read_text(encoding="utf-8")
        event_source = EVENT_REPOSITORY_PATH.read_text(encoding="utf-8")
        authorization_source = AUTHORIZATION_PATH.read_text(encoding="utf-8")
        self.assertIn("import frappe", stage_source)
        self.assertIn("stage.save(ignore_permissions=True)", stage_source)
        self.assertIn("frappe.db.set_value", order_source)
        self.assertIn('frappe.new_doc("Production Stage Event")', event_source)
        self.assertIn("frappe.get_roles", authorization_source)

    def test_api_adapter_is_thin_and_delegates_to_application(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 140)
        self.assertIn("application.shop_floor import commands", source)
        self.assertIn("FrappeShopFloorCommandRepository", source)
        self.assertNotIn("transition_stage", source)
        self.assertNotIn("next_stage_type", source)
        self.assertNotIn("stage.save(", source)
        self.assertNotIn("frappe.db", source)
        self.assertNotIn("shop_floor_gateway", source)

    def test_hooks_keep_public_api_compatibility(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        overrides = hooks["override_whitelisted_methods"]
        for method in (
            "get_handoff_workers",
            "start_my_stage",
            "handoff_to_next",
            "mark_delivered",
            "revert_department",
        ):
            old = f"almdina_erp.almdina_erp.services.shop_floor_service.{method}"
            new = f"almdina_erp.almdina_erp.services.shop_floor_commands.{method}"
            self.assertEqual(overrides.get(old), new)

    def test_legacy_return_to_draft_remains_revision_only(self) -> None:
        source = ADAPTER_PATH.read_text(encoding="utf-8")
        function_source = source.split("def return_order_to_draft", 1)[1]
        self.assertIn("return_order_to_draft", function_source)
        self.assertIn("create_controlled_return", function_source)
        self.assertNotIn('"approved_plan": None', function_source)
        self.assertNotIn('"status": "Draft"', function_source)


if __name__ == "__main__":
    unittest.main()
