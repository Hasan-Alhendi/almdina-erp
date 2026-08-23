from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_PATH = ROOT / "almdina_erp" / "services" / "order_approval_service.py"
DISPATCH_PATH = ROOT / "almdina_erp" / "services" / "order_dispatch_service.py"
CUTTING_MODULE = "almdina_erp.almdina_erp.services.cutting_plan_service"
ACTIVATION_MODULE = "almdina_erp.almdina_erp.services.order_revision_activation"
COMMANDS_MODULE = "almdina_erp.almdina_erp.services.shop_floor_commands"
LIFECYCLE_MODULE = (
    "almdina_erp.almdina_erp.services.order_lifecycle_permission_service"
)


def _load(path: Path, module_name: str, replacements: dict[str, types.ModuleType]):
    previous = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class TestOrderRevisionActivationAdapters(unittest.TestCase):
    def fake_frappe(self, order: Any, calls: list[Any]) -> types.ModuleType:
        frappe = types.ModuleType("frappe")
        frappe._ = lambda message: message
        frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        frappe.db = SimpleNamespace(
            sql=lambda query, values=None, **kwargs: calls.append(("db_lock", values)) or [],
        )
        frappe.get_doc = lambda doctype, name: order

        def throw(message: str, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(message)

        frappe.throw = throw
        return frappe

    def test_approval_locks_chain_then_checks_capability_and_activates_revision(self) -> None:
        calls: list[Any] = []
        order = SimpleNamespace(
            name="DCO-REV-2",
            status="Pending Review",
            check_permission=lambda permission: calls.append(("permission", permission)),
        )
        fake_frappe = self.fake_frappe(order, calls)

        cutting = types.ModuleType(CUTTING_MODULE)

        def lock_order(candidate):
            calls.append(("approve_plan", candidate.name))
            return {"name": candidate.name, "cutting_plan": "PLAN-REV-2"}

        cutting._lock_order_for_production = lock_order

        lifecycle = types.ModuleType(LIFECYCLE_MODULE)
        lifecycle.require_lifecycle_action = lambda candidate, action: calls.append(
            ("lifecycle_guard", candidate.name, action)
        )

        activation = types.ModuleType(ACTIVATION_MODULE)
        activation.load_locked_revision_order = lambda name: calls.append(
            ("chain_lock", name)
        ) or order
        activation.prepare_revision_activation = lambda candidate: calls.append(
            ("prepare", candidate.name)
        ) or "context"

        def finalize(candidate, context, *, new_plan_name):
            calls.append(("finalize", candidate.name, context, new_plan_name))
            return {"replaced_revision": "DCO-REV-1"}

        activation.finalize_revision_activation = finalize

        service = _load(
            APPROVAL_PATH,
            "_test_order_approval_service",
            {
                "frappe": fake_frappe,
                CUTTING_MODULE: cutting,
                ACTIVATION_MODULE: activation,
                LIFECYCLE_MODULE: lifecycle,
            },
        )
        result = service.approve_order(order.name)

        self.assertEqual(result["revision_activation"]["replaced_revision"], "DCO-REV-1")
        guard_call = next(call for call in calls if call[0] == "lifecycle_guard")
        self.assertLess(calls.index(("chain_lock", order.name)), calls.index(guard_call))
        self.assertLess(calls.index(guard_call), calls.index(("prepare", order.name)))
        self.assertLess(calls.index(("prepare", order.name)), calls.index(("approve_plan", order.name)))
        self.assertLess(
            calls.index(("approve_plan", order.name)),
            calls.index(("finalize", order.name, "context", "PLAN-REV-2")),
        )

    def test_dispatch_locks_chain_and_validates_revision_before_stage_creation(self) -> None:
        calls: list[Any] = []
        order = SimpleNamespace(
            name="DCO-CURRENT",
            status="Approved",
            revision_state="Current",
            check_permission=lambda permission: calls.append(("permission", permission)),
        )
        fake_frappe = self.fake_frappe(order, calls)

        commands = types.ModuleType(COMMANDS_MODULE)
        commands.assert_order_ready_for_dispatch = lambda candidate: calls.append(
            ("ready", candidate.name)
        )
        commands.dispatch_order = lambda name, path, assignee: calls.append(
            ("dispatch", name, path, assignee)
        ) or {"name": name, "production_path": path}

        cutting = types.ModuleType(CUTTING_MODULE)
        cutting.require_any_role = lambda *roles: calls.append(("roles", roles))

        activation = types.ModuleType(ACTIVATION_MODULE)
        activation.load_locked_revision_order = lambda name: calls.append(
            ("chain_lock", name)
        ) or order
        activation.assert_order_revision_dispatchable = lambda candidate: calls.append(
            ("revision_guard", candidate.name)
        )

        service = _load(
            DISPATCH_PATH,
            "_test_order_dispatch_service",
            {
                "frappe": fake_frappe,
                COMMANDS_MODULE: commands,
                CUTTING_MODULE: cutting,
                ACTIVATION_MODULE: activation,
            },
        )
        result = service.dispatch_order(order.name, "Drawing", "worker@example.com")

        self.assertEqual(result["production_path"], "Drawing")
        self.assertLess(
            calls.index(("chain_lock", order.name)),
            calls.index(("revision_guard", order.name)),
        )
        self.assertLess(
            calls.index(("revision_guard", order.name)),
            calls.index(("dispatch", order.name, "Drawing", "worker@example.com")),
        )


if __name__ == "__main__":
    unittest.main()
