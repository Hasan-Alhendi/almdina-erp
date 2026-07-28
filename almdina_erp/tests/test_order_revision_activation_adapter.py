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

        def throw(message: str, *args, **kwargs) -> None:
            raise RuntimeError(message)

        frappe.throw = throw
        return frappe

    def test_approval_prepares_and_finalizes_revision_in_one_command(self) -> None:
        calls: list[Any] = []
        order = SimpleNamespace(name="DCO-REV-2", status="Pending Review")
        fake_frappe = self.fake_frappe(order, calls)

        cutting = types.ModuleType(CUTTING_MODULE)
        cutting.require_any_role = lambda *roles: calls.append(("roles", roles))

        def lock_order(candidate):
            calls.append(("approve_plan", candidate.name))
            return {"name": candidate.name, "cutting_plan": "PLAN-REV-2"}

        cutting._lock_order_for_production = lock_order

        activation = types.ModuleType(ACTIVATION_MODULE)
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
            },
        )
        result = service.approve_order(order.name)

        self.assertEqual(result["revision_activation"]["replaced_revision"], "DCO-REV-1")
        self.assertLess(calls.index(("prepare", order.name)), calls.index(("approve_plan", order.name)))
        self.assertLess(
            calls.index(("approve_plan", order.name)),
            calls.index(("finalize", order.name, "context", "PLAN-REV-2")),
        )

    def test_dispatch_validates_revision_before_creating_production_stage(self) -> None:
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
            calls.index(("revision_guard", order.name)),
            calls.index(("dispatch", order.name, "Drawing", "worker@example.com")),
        )


if __name__ == "__main__":
    unittest.main()
