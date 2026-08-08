from __future__ import annotations

import importlib.util
import runpy
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/services/shop_floor_commands.py"
)
HOOKS_PATH = REPOSITORY_ROOT / "almdina_erp/hooks.py"
REPOSITORY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe."
    "shop_floor_command_repository"
)


class AdapterHarness:
    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe._ = lambda message: message
        fake_frappe.PermissionError = PermissionError
        fake_frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)

        def throw(message: str, *args, **kwargs) -> None:
            raise RuntimeError(message)

        fake_frappe.throw = throw

        fake_repository_module = types.ModuleType(REPOSITORY_MODULE)

        class FakeRepository:
            pass

        fake_repository_module.FrappeShopFloorCommandRepository = FakeRepository

        replacements = {
            "frappe": fake_frappe,
            REPOSITORY_MODULE: fake_repository_module,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_shop_floor_commands_test",
                COMMAND_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load shop-floor command adapter")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            for name, old in previous.items():
                if old is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = old


class TestShopFloorCommandAdapter(unittest.TestCase):
    def test_hooks_route_mutating_shop_floor_apis_to_command_boundaries(self) -> None:
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

        guarded_dispatch = (
            "almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order"
        )
        self.assertEqual(
            overrides.get(
                "almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order"
            ),
            guarded_dispatch,
        )
        self.assertEqual(
            overrides.get(
                "almdina_erp.almdina_erp.services.shop_floor_commands.dispatch_order"
            ),
            guarded_dispatch,
        )

    def test_adapter_delegates_framework_errors_without_owning_rules(self) -> None:
        adapter = AdapterHarness().load()

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
