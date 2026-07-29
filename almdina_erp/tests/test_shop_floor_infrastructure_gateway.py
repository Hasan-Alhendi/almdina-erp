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
INFRA_ROOT = ROOT / "almdina_erp" / "infrastructure" / "frappe"
GATEWAY_PATH = INFRA_ROOT / "shop_floor_gateway.py"
AUTHORIZATION_PATH = INFRA_ROOT / "shop_floor_authorization.py"
ORDER_TRACKING_PATH = INFRA_ROOT / "order_tracking_repository.py"
STAGE_REPOSITORY_PATH = INFRA_ROOT / "production_stage_repository.py"
EVENT_REPOSITORY_PATH = INFRA_ROOT / "production_event_repository.py"
STOCK_GATEWAY_PATH = INFRA_ROOT / "stock_execution_gateway.py"
REMNANT_GATEWAY_PATH = INFRA_ROOT / "remnant_execution_gateway.py"
COMMAND_REPOSITORY_PATH = INFRA_ROOT / "shop_floor_command_repository.py"
QUERY_REPOSITORY_PATH = INFRA_ROOT / "shop_floor_query_repository.py"
APPLICATION_PATH = ROOT / "almdina_erp" / "application" / "shop_floor" / "commands.py"
COMMAND_ADAPTER_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"
QUERY_ADAPTER_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_query_service.py"


class InfrastructureHarness:
    def __init__(self) -> None:
        self.set_calls: list[tuple[Any, ...]] = []
        self.events: list[tuple[Any, ...]] = []
        self.stage_inserts: list[dict[str, Any]] = []

    def load(self, path: Path, module_name: str):
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
            doc = SimpleNamespace()
            if doctype == "Production Stage Event":
                def insert(ignore_permissions: bool = False) -> None:
                    self.events.append(
                        (
                            doc.production_stage,
                            doc.event_type,
                            json.loads(doc.details_json),
                            ignore_permissions,
                        )
                    )

                doc.insert = insert
                return doc
            if doctype == "Production Stage":
                def insert(ignore_permissions: bool = False) -> None:
                    doc.name = "PST-NEW"
                    self.stage_inserts.append(
                        {
                            "order": doc.door_cutting_order,
                            "stage_type": doc.stage_type,
                            "assignee": doc.assigned_to,
                            "sequence": doc.sequence,
                            "status": doc.status,
                            "ignore_permissions": ignore_permissions,
                        }
                    )

                doc.insert = insert
                return doc
            return doc

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
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Could not load {path.name}")
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
    def test_order_tracking_repository_maps_stage_state(self) -> None:
        harness = InfrastructureHarness()
        repository = harness.load(ORDER_TRACKING_PATH, "_order_tracking_test")
        stage = SimpleNamespace(
            name="PST-1",
            stage_type="Drawing",
            assigned_to="drawing@example.com",
            status="Pending",
        )

        repository.set_order_tracking("DCO-1", path="Drawing", stage=stage)

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

    def test_event_and_piece_quantity_are_focused_adapters(self) -> None:
        harness = InfrastructureHarness()
        events = harness.load(EVENT_REPOSITORY_PATH, "_production_event_test")
        tracking = harness.load(ORDER_TRACKING_PATH, "_order_tracking_qty_test")
        stage = SimpleNamespace(
            name="PST-2",
            door_cutting_order="DCO-1",
            stage_type="Drawing",
        )

        events.log_event(stage, "Start", {"shop_floor": True})

        self.assertEqual(
            harness.events,
            [("PST-2", "Start", {"shop_floor": True}, True)],
        )
        self.assertEqual(tracking.required_piece_qty("DCO-1"), 7)

    def test_stage_creation_has_no_hidden_event_side_effect(self) -> None:
        harness = InfrastructureHarness()
        stages = harness.load(STAGE_REPOSITORY_PATH, "_production_stage_test")

        stage = stages.create_stage("DCO-1", "Drawing", "worker@example.com", 10)

        self.assertEqual(stage.name, "PST-NEW")
        self.assertEqual(len(harness.stage_inserts), 1)
        self.assertEqual(harness.events, [])

    def test_infrastructure_is_split_by_responsibility(self) -> None:
        application_source = APPLICATION_PATH.read_text(encoding="utf-8")
        command_adapter_source = COMMAND_ADAPTER_PATH.read_text(encoding="utf-8")
        query_adapter_source = QUERY_ADAPTER_PATH.read_text(encoding="utf-8")
        command_repository_source = COMMAND_REPOSITORY_PATH.read_text(encoding="utf-8")
        query_repository_source = QUERY_REPOSITORY_PATH.read_text(encoding="utf-8")
        gateway_source = GATEWAY_PATH.read_text(encoding="utf-8")

        self.assertNotIn("import frappe", application_source)
        self.assertNotIn("from frappe", application_source)
        self.assertNotIn("shop_floor_gateway", application_source)
        self.assertNotIn("shop_floor_gateway", command_adapter_source)
        self.assertNotIn("shop_floor_gateway", command_repository_source)
        self.assertNotIn("shop_floor_gateway", query_repository_source)
        self.assertNotIn("shop_floor_gateway", query_adapter_source)

        for module_name in (
            "shop_floor_authorization",
            "order_tracking_repository",
            "production_stage_repository",
            "production_event_repository",
        ):
            self.assertIn(module_name, command_repository_source)
        self.assertNotIn("stock_execution_gateway", command_repository_source)
        self.assertNotIn("remnant_execution_gateway", command_repository_source)

        self.assertNotIn("import frappe", gateway_source)
        self.assertNotIn("frappe.db", gateway_source)
        self.assertNotIn("frappe.get_doc", gateway_source)
        self.assertNotIn("frappe.get_all", gateway_source)
        self.assertNotIn("frappe.new_doc", gateway_source)
        self.assertIn("Backward-compatible facade", gateway_source)

        for path in (
            AUTHORIZATION_PATH,
            ORDER_TRACKING_PATH,
            STAGE_REPOSITORY_PATH,
            EVENT_REPOSITORY_PATH,
            STOCK_GATEWAY_PATH,
            REMNANT_GATEWAY_PATH,
        ):
            self.assertTrue(path.exists(), path)

    def test_legacy_gateway_preserves_created_event_only_for_legacy_callers(self) -> None:
        gateway_source = GATEWAY_PATH.read_text(encoding="utf-8")
        create_source = gateway_source.split("def create_stage", 1)[1].split(
            "def close_open_pause", 1
        )[0]
        self.assertIn("production_stage_repository.create_stage", create_source)
        self.assertIn("production_event_repository.log_event", create_source)

        command_repository_source = COMMAND_REPOSITORY_PATH.read_text(encoding="utf-8")
        create_repository_source = command_repository_source.split(
            "def create_stage", 1
        )[1].split("def track_order_to_stage", 1)[0]
        self.assertIn("production_stage_repository.create_stage", create_repository_source)
        self.assertNotIn("production_event_repository.log_event", create_repository_source)

    def test_legacy_return_to_draft_is_a_revision_adapter_only(self) -> None:
        source = COMMAND_ADAPTER_PATH.read_text(encoding="utf-8")
        function_source = source.split("def return_order_to_draft", 1)[1]
        self.assertIn("create_order_revision", function_source)
        self.assertNotIn('"approved_plan": None', function_source)
        self.assertNotIn('"status": "Draft"', function_source)


if __name__ == "__main__":
    unittest.main()
