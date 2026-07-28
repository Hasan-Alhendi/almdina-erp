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
LEGACY_MODULE = "almdina_erp.almdina_erp.services.shop_floor_service"


class AdapterHarness:
    def __init__(self) -> None:
        self.db = SimpleNamespace()
        self.db.get_value = lambda *args, **kwargs: None
        self.db.set_value = lambda *args, **kwargs: None
        self.db.exists = lambda *args, **kwargs: False
        self.session = SimpleNamespace(user="worker@example.com")

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = self.db
        fake_frappe.session = self.session
        fake_frappe._ = lambda message: message
        fake_frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)

        def throw(message: str, *args, **kwargs) -> None:
            raise RuntimeError(message)

        fake_frappe.throw = throw
        fake_frappe.get_doc = lambda *args, **kwargs: None
        fake_frappe.get_all = lambda *args, **kwargs: []

        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)
        fake_utils.now_datetime = lambda: "2026-01-01 00:00:00"
        fake_utils.time_diff_in_seconds = lambda end, start: 0

        fake_legacy = types.ModuleType(LEGACY_MODULE)
        fake_legacy.DISPATCH_ROLES = ("Order Entry", "Production Manager")
        fake_legacy.ADMIN_ROLES = ("Order Entry", "Production Manager", "System Manager")
        fake_legacy.STAGE_ROLE = {
            "Sharyoun": "عامل شريون",
            "Drawing": "عامل رسم",
            "CNC": "عامل CNC",
            "Sanding": "عامل تقشيط",
        }
        fake_legacy.require_any_role = lambda *roles: None

        replacements = {
            "frappe": fake_frappe,
            "frappe.utils": fake_utils,
            LEGACY_MODULE: fake_legacy,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_shop_floor_commands_test",
                COMMAND_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load shop floor command adapter")
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
        direct_commands = (
            "get_handoff_workers",
            "start_my_stage",
            "handoff_to_next",
            "mark_delivered",
            "revert_department",
        )
        for method in direct_commands:
            old = f"almdina_erp.almdina_erp.services.shop_floor_service.{method}"
            new = f"almdina_erp.almdina_erp.services.shop_floor_commands.{method}"
            self.assertEqual(overrides.get(old), new)

        guarded_dispatch = "almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order"
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

        revision_target = "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision"
        self.assertEqual(
            overrides.get("almdina_erp.almdina_erp.services.shop_floor_service.return_order_to_draft"),
            revision_target,
        )
        self.assertEqual(
            overrides.get("almdina_erp.almdina_erp.services.shop_floor_commands.return_order_to_draft"),
            revision_target,
        )

    def test_command_adapter_does_not_redeclare_lifecycle_tables(self) -> None:
        source = COMMAND_PATH.read_text(encoding="utf-8")
        self.assertIn("domain.orders.lifecycle import", source)
        self.assertNotIn("PATH_SEQUENCE", source)
        self.assertNotIn("STAGE_ORDER_STATUS", source)
        self.assertNotIn("def _next_stage_type", source)
        self.assertNotIn("def _sequence_for_stage", source)

    def test_dispatch_policy_preserves_valid_order_behavior(self) -> None:
        commands = AdapterHarness().load()
        calls: list[str] = []
        order = SimpleNamespace(
            name="DCO-TEST",
            production_path=None,
            current_production_stage=None,
            status="Approved",
            cutting_plan_json="{}",
            plan_needs_recalculation=0,
            ensure_special_shapes_documented=lambda: calls.append("validated"),
        )

        commands.assert_order_ready_for_dispatch(order)
        self.assertEqual(calls, ["validated"])

    def test_dispatch_policy_rejects_dispatched_and_invalid_statuses(self) -> None:
        commands = AdapterHarness().load()
        dispatched = SimpleNamespace(
            name="DCO-DISPATCHED",
            production_path="Drawing",
            current_production_stage="PST-1",
            status="At Drawing",
            cutting_plan_json="{}",
            plan_needs_recalculation=0,
            ensure_special_shapes_documented=lambda: None,
        )
        with self.assertRaisesRegex(RuntimeError, "already dispatched"):
            commands.assert_order_ready_for_dispatch(dispatched)

        invalid = SimpleNamespace(
            name="DCO-HOLD",
            production_path=None,
            current_production_stage=None,
            status="On Hold",
            cutting_plan_json="{}",
            plan_needs_recalculation=0,
            ensure_special_shapes_documented=lambda: None,
        )
        with self.assertRaisesRegex(RuntimeError, "Only draft or rejected"):
            commands.assert_order_ready_for_dispatch(invalid)

    def test_stage_transitions_and_paths_are_domain_driven(self) -> None:
        commands = AdapterHarness().load()
        self.assertEqual(commands._transition("Pending", "start", "error"), "In Progress")
        self.assertEqual(commands._transition("Paused", "finish", "error"), "Completed")
        self.assertEqual(commands._next_stage("Drawing", "Drawing"), "CNC")
        self.assertEqual(commands._next_stage("Drawing", "Sanding"), None)
        with self.assertRaisesRegex(RuntimeError, "error"):
            commands._transition("Completed", "start", "error")


if __name__ == "__main__":
    unittest.main()
