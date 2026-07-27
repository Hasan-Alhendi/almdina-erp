from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "services"
    / "order_edit_policy.py"
)


class FakeDatabase:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.stage_types: dict[str, str] = {}

    def get_value(self, *args: Any) -> str | None:
        self.calls.append(args)
        if len(args) >= 2:
            return self.stage_types.get(str(args[1]))
        return None


class AdapterHarness:
    def __init__(self, roles: set[str] | None = None) -> None:
        self.roles = set(roles or ())
        self.role_calls: list[str | None] = []
        self.db = FakeDatabase()

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = self.db
        fake_frappe._ = lambda message: message

        def get_roles(user: str | None = None) -> list[str]:
            self.role_calls.append(user)
            return sorted(self.roles)

        def throw(message: str) -> None:
            raise RuntimeError(message)

        fake_frappe.get_roles = get_roles
        fake_frappe.throw = throw

        previous = sys.modules.get("frappe")
        sys.modules["frappe"] = fake_frappe
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_order_edit_policy_adapter_test",
                SERVICE_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load order edit policy adapter")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if previous is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = previous


class TestOrderEditPolicyAdapter(unittest.TestCase):
    def test_draft_and_locked_statuses_do_not_fetch_roles(self) -> None:
        harness = AdapterHarness(roles={"System Manager"})
        policy = harness.load()

        self.assertTrue(policy.user_can_edit_order("Draft"))
        self.assertFalse(policy.user_can_edit_order("Delivered"))
        self.assertEqual(harness.role_calls, [])

    def test_production_status_delegates_role_resolution_to_frappe(self) -> None:
        allowed = AdapterHarness(roles={"Order Entry"})
        allowed_policy = allowed.load()
        self.assertTrue(allowed_policy.user_can_edit_order("Cutting In Progress", "worker@example.com"))
        self.assertEqual(allowed.role_calls, ["worker@example.com"])

        denied = AdapterHarness(roles={"Cutting Operator"})
        denied_policy = denied.load()
        self.assertFalse(denied_policy.user_can_edit_order("Cutting In Progress"))
        self.assertEqual(denied.role_calls, [None])

    def test_drawing_recalculation_short_circuits_before_database_lookup(self) -> None:
        no_role = AdapterHarness(roles={"Order Entry"})
        no_role_policy = no_role.load()
        order = {
            "status": "Production In Progress",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": None,
        }
        self.assertFalse(no_role_policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(no_role.db.calls, [])

        approved = AdapterHarness(roles={"عامل رسم"})
        approved_policy = approved.load()
        self.assertFalse(
            approved_policy.user_can_recalculate_drawing_system_plan(
                {**order, "approved_plan": "PLAN-0001"}
            )
        )
        self.assertEqual(approved.db.calls, [])

    def test_drawing_stage_fallback_reads_only_the_current_stage_type(self) -> None:
        harness = AdapterHarness(roles={"عامل رسم"})
        harness.db.stage_types["STAGE-DRAWING"] = "Drawing"
        policy = harness.load()
        order = {
            "status": "Production In Progress",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": None,
        }

        self.assertTrue(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(
            harness.db.calls,
            [("Production Stage", "STAGE-DRAWING", "stage_type")],
        )

    def test_explicit_at_drawing_status_avoids_database_lookup(self) -> None:
        harness = AdapterHarness(roles={"عامل رسم"})
        policy = harness.load()
        order = {
            "status": "At Drawing",
            "production_path": "Drawing",
            "current_production_stage": "STAGE-DRAWING",
            "approved_plan": None,
        }

        self.assertTrue(policy.user_can_recalculate_drawing_system_plan(order))
        self.assertEqual(harness.db.calls, [])


if __name__ == "__main__":
    unittest.main()
