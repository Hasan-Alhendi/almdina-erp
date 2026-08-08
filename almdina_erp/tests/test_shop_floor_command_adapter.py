from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "almdina_erp" / "services" / "shop_floor_commands.py"


class AdapterHarness:
    def __init__(self) -> None:
        self.frappe = types.ModuleType("frappe")
        self.frappe._ = lambda value: value
        self.frappe.PermissionError = type("PermissionError", (Exception,), {})
        self.frappe.throw = Mock(side_effect=lambda message, *args, **kwargs: (_ for _ in ()).throw(RuntimeError(message)))
        self.frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn) if not (args and callable(args[0])) else args[0]

    def load(self):
        sys.modules["frappe"] = self.frappe
        module_name = "almdina_erp.almdina_erp.services.shop_floor_commands_test_adapter"
        spec = importlib.util.spec_from_file_location(module_name, ADAPTER_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module


class TestShopFloorCommandAdapter(unittest.TestCase):
    def tearDown(self) -> None:
        sys.modules.pop("frappe", None)

    def test_hooks_route_mutating_shop_floor_apis_to_command_boundaries(self) -> None:
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        for method in (
            "dispatch_order",
            "start_my_stage",
            "handoff_to_next",
            "reassign_worker",
            "mark_delivered",
            "revert_department",
        ):
            self.assertIn(f"shop_floor_commands.{method}", hooks)

    def test_adapter_delegates_framework_errors_without_owning_rules(self) -> None:
        adapter = AdapterHarness().load()

        def denied(repository):
            raise adapter.commands.ShopFloorPermissionDenied("ممنوع")

        with self.assertRaisesRegex(RuntimeError, "ممنوع"):
            adapter._execute(denied)

        def fail(repository):
            raise adapter.commands.ShopFloorCommandError("business error")

        with self.assertRaisesRegex(RuntimeError, "business error"):
            adapter._execute(fail)

    def test_dispatch_compatibility_validator_preserves_behavior(self) -> None:
        adapter = AdapterHarness().load()
        calls: list[str] = []
        valid = SimpleNamespace(
            name="DCO-VALID",
            production_path=None,
            current_production_stage=None,
            status="Approved",
            cutting_plan_json="{}",
            plan_needs_recalculation=0,
            approved_plan=None,
            drawing_dxf_status=None,
            ensure_special_shapes_documented=lambda: calls.append("validated"),
        )
        adapter.assert_order_ready_for_dispatch(valid)
        self.assertEqual(calls, ["validated"])

        invalid = SimpleNamespace(
            name="DCO-HOLD",
            production_path=None,
            current_production_stage=None,
            status="On Hold",
            cutting_plan_json="{}",
            plan_needs_recalculation=0,
            approved_plan=None,
            drawing_dxf_status=None,
            ensure_special_shapes_documented=lambda: None,
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "حالة الطلب الحالية لا تسمح بإرساله إلى الإنتاج",
        ):
            adapter.assert_order_ready_for_dispatch(invalid)

    def test_private_compatibility_helpers_delegate_to_application(self) -> None:
        adapter = AdapterHarness().load()
        self.assertEqual(adapter._transition("Pending", "start", "error"), "In Progress")
        self.assertEqual(adapter._next_stage("Drawing", "Drawing"), "CNC")
        with self.assertRaisesRegex(
            adapter.commands.ShopFloorCommandError,
            "error",
        ):
            adapter._transition("Completed", "start", "error")


if __name__ == "__main__":
    unittest.main()
