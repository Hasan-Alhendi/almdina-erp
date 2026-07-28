from __future__ import annotations

import importlib.util
import json
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


class GatewayHarness:
    def __init__(self) -> None:
        self.set_calls: list[tuple[Any, ...]] = []
        self.events: list[tuple[Any, ...]] = []

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe._ = lambda message: message
        fake_frappe.PermissionError = RuntimeError
        fake_frappe.session = SimpleNamespace(user="worker@example.com")
        fake_frappe.db = SimpleNamespace(
            set_value=lambda *args, **kwargs: self.set_calls.append((args, kwargs)),
            get_value=lambda *args, **kwargs: None,
            exists=lambda *args, **kwargs: False,
            sql=lambda *args, **kwargs: [],
        )
        fake_frappe.get_roles = lambda user=None: []
        fake_frappe.get_doc = lambda *args, **kwargs: None

        def get_all(doctype: str, *args: Any, **kwargs: Any) -> list[Any]:
            if doctype == "Door Cutting Order Detail":
                return [SimpleNamespace(qty=3), SimpleNamespace(qty=4)]
            return []

        fake_frappe.get_all = get_all
        fake_frappe.as_json = lambda value: json.dumps(value, sort_keys=True)

        def new_doc(doctype: str) -> Any:
            if doctype != "Production Stage Event":
                return SimpleNamespace()
            event = SimpleNamespace()

            def insert(ignore_permissions: bool = False) -> None:
                self.events.append(
                    (
                        event.production_stage,
                        event.event_type,
                        json.loads(event.details_json),
                        ignore_permissions,
                    )
                )

            event.insert = insert
            return event

        fake_frappe.new_doc = new_doc

        def throw(message: str, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(message)

        fake_frappe.throw = throw

        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)
        fake_utils.now_datetime = lambda: "2026-01-01 00:00:00"
        fake_utils.time_diff_in_seconds = lambda end, start: 0

        replacements = {
            "frappe": fake_frappe,
            "frappe.utils": fake_utils,
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

    def test_gateway_owns_event_and_piece_quantity_persistence(self) -> None:
        harness = GatewayHarness()
        gateway = harness.load()
        stage = SimpleNamespace(
            name="PST-2",
            door_cutting_order="DCO-1",
            stage_type="Drawing",
        )

        gateway.log_event(stage, "Start", {"shop_floor": True})

        self.assertEqual(
            harness.events,
            [("PST-2", "Start", {"shop_floor": True}, True)],
        )
        self.assertEqual(gateway.required_piece_qty("DCO-1"), 7)

    def test_commands_no_longer_depend_on_legacy_service(self) -> None:
        source = COMMAND_PATH.read_text(encoding="utf-8")
        self.assertNotIn("shop_floor_service as legacy", source)
        self.assertNotIn("services import shop_floor_service", source)
        self.assertIn("shop_floor_gateway as gateway", source)

        gateway_source = GATEWAY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("services.production_service", gateway_source)
        self.assertNotIn("services.cutting_plan_service", gateway_source)

    def test_legacy_return_to_draft_is_a_revision_adapter_only(self) -> None:
        source = COMMAND_PATH.read_text(encoding="utf-8")
        function_source = source.split("def return_order_to_draft", 1)[1]
        self.assertIn("create_order_revision", function_source)
        self.assertNotIn('"approved_plan": None', function_source)
        self.assertNotIn('"status": "Draft"', function_source)


if __name__ == "__main__":
    unittest.main()
