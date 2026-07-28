from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "shop_floor_gateway.py"
)
COMMAND_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"
CUTTING_MODULE = "almdina_erp.almdina_erp.services.cutting_plan_service"
PRODUCTION_MODULE = "almdina_erp.almdina_erp.services.production_service"


class GatewayHarness:
    def __init__(self) -> None:
        self.set_calls: list[tuple[Any, ...]] = []
        self.events: list[tuple[Any, ...]] = []

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe._ = lambda message: message
        fake_frappe.session = SimpleNamespace(user="worker@example.com")
        fake_frappe.db = SimpleNamespace(
            set_value=lambda *args, **kwargs: self.set_calls.append((args, kwargs)),
            get_value=lambda *args, **kwargs: None,
            exists=lambda *args, **kwargs: False,
            sql=lambda *args, **kwargs: [],
        )
        fake_frappe.get_roles = lambda user=None: []
        fake_frappe.get_doc = lambda *args, **kwargs: None
        fake_frappe.get_all = lambda *args, **kwargs: []
        fake_frappe.new_doc = lambda *args, **kwargs: None

        def throw(message: str, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(message)

        fake_frappe.throw = throw

        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)

        fake_cutting = types.ModuleType(CUTTING_MODULE)
        fake_cutting.require_any_role = lambda *roles: None

        fake_production = types.ModuleType(PRODUCTION_MODULE)
        fake_production._close_open_pause = lambda stage, actor: None
        fake_production._required_piece_qty = lambda order_name: 7
        fake_production._log_event = (
            lambda stage, event_type, details=None: self.events.append(
                (stage.name, event_type, details or {})
            )
        )

        replacements = {
            "frappe": fake_frappe,
            "frappe.utils": fake_utils,
            CUTTING_MODULE: fake_cutting,
            PRODUCTION_MODULE: fake_production,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_shop_floor_gateway_test",
                GATEWAY_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load shop-floor gateway")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            for name, old in previous.items():
                if old is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = old


class TestShopFloorInfrastructureGateway(unittest.TestCase):
    def test_gateway_maps_stage_state_to_order_tracking(self) -> None:
        harness = GatewayHarness()
        gateway = harness.load()
        stage = SimpleNamespace(
            name="PST-1",
            stage_type="Drawing",
            assigned_to="drawing@example.com",
            status="Pending",
        )

        gateway.set_order_tracking("DCO-1", path="Drawing", stage=stage)

        self.assertEqual(len(harness.set_calls), 1)
        args, kwargs = harness.set_calls[0]
        self.assertEqual(args[0:2], ("Door Cutting Order", "DCO-1"))
        self.assertEqual(
            args[2],
            {
                "production_path": "Drawing",
                "current_production_stage": "PST-1",
                "current_department": "رسم",
                "current_assignee": "drawing@example.com",
                "department_status": "بحاجة للعمل",
                "status": "At Drawing",
            },
        )
        self.assertTrue(kwargs["update_modified"])

    def test_gateway_delegates_event_and_piece_quantity_operations(self) -> None:
        harness = GatewayHarness()
        gateway = harness.load()
        stage = SimpleNamespace(name="PST-2")

        gateway.log_event(stage, "Start", {"shop_floor": True})

        self.assertEqual(
            harness.events,
            [("PST-2", "Start", {"shop_floor": True})],
        )
        self.assertEqual(gateway.required_piece_qty("DCO-1"), 7)

    def test_commands_no_longer_depend_on_legacy_service(self) -> None:
        source = COMMAND_PATH.read_text(encoding="utf-8")
        self.assertNotIn("shop_floor_service as legacy", source)
        self.assertNotIn("services import shop_floor_service", source)
        self.assertIn("shop_floor_gateway as gateway", source)

    def test_legacy_return_to_draft_is_a_revision_adapter_only(self) -> None:
        source = COMMAND_PATH.read_text(encoding="utf-8")
        function_source = source.split("def return_order_to_draft", 1)[1]
        self.assertIn("create_order_revision", function_source)
        self.assertNotIn('"approved_plan": None', function_source)
        self.assertNotIn('"status": "Draft"', function_source)


if __name__ == "__main__":
    unittest.main()
