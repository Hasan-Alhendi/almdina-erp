"""Regression: whitelist approve_order_final_price must not shadow the use case."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.application.orders.final_price_approval import (
    approve_order_final_price as application_approve_order_final_price,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    fingerprint_final_price_basis,
    price_basis_token,
)
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_APPROVED,
)

from almdina_erp.tests.test_final_price_approval_phase2 import (
    FakeGateway,
    FakeOrder,
    FakePlan,
    _basis,
)

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "almdina_erp" / "services" / "final_price_approval_service.py"

AUTH_GATEWAY = "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
PLAN_AUTH = "almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization"
FP_GATEWAY = "almdina_erp.almdina_erp.infrastructure.frappe.final_price_approval_gateway"


class TestFinalPriceApprovalServiceRpc(unittest.TestCase):
    def test_browser_kwargs_reach_application_without_order_name_collision(self) -> None:
        """Browser sends order_name + expected_price_basis_token as kwargs.

        Before the alias fix, the service function shadowed the imported use case
        and recursively called itself as::

            approve_order_final_price(gateway, order_name=name, ...)

        which raises TypeError: got multiple values for argument 'order_name'.
        """

        basis = _basis()
        digest = fingerprint_final_price_basis(basis)
        token = price_basis_token(digest)
        order = FakeOrder(name="DCO-RPC-1")
        order.check_permission = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
        order.reload = lambda: order  # type: ignore[attr-defined]
        gateway = FakeGateway(
            order=order,
            plan=FakePlan(name="PLAN-1", door_cutting_order="DCO-RPC-1"),
            basis=basis,
        )

        fake_frappe = types.ModuleType("frappe")
        fake_frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        fake_frappe._ = lambda message: message
        fake_frappe.ValidationError = type("ValidationError", (Exception,), {})
        fake_frappe.PermissionError = type("PermissionError", (Exception,), {})

        def throw(message: str, *args: Any, **kwargs: Any) -> None:
            exc_type = args[0] if args else Exception
            raise exc_type(message)

        fake_frappe.throw = throw
        fake_frappe.get_doc = lambda doctype, name: order

        fake_auth = types.ModuleType(AUTH_GATEWAY)
        fake_auth.require_document_capability = lambda *a, **k: None
        fake_auth.document_has_capability = lambda *_a, **_k: True

        fake_plan_auth = types.ModuleType(PLAN_AUTH)
        fake_plan_auth.require_cutting_plan_capability = lambda *a, **k: None
        fake_plan_auth.cutting_plan_capability_allowed = lambda *_a, **_k: True

        fake_fp = types.ModuleType(FP_GATEWAY)
        fake_fp.FrappeFinalPriceApprovalGateway = lambda: gateway
        fake_fp.order_commercial_inputs_changed = lambda _order: False

        previous = {
            name: sys.modules.get(name)
            for name in ("frappe", AUTH_GATEWAY, PLAN_AUTH, FP_GATEWAY)
        }
        sys.modules["frappe"] = fake_frappe
        sys.modules[AUTH_GATEWAY] = fake_auth
        sys.modules[PLAN_AUTH] = fake_plan_auth
        sys.modules[FP_GATEWAY] = fake_fp

        # Ensure a fresh service module load binds Service → Application for real.
        sys.modules.pop(
            "almdina_erp.almdina_erp.services.final_price_approval_service",
            None,
        )
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_final_price_approval_service_rpc_test",
                SERVICE_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load final_price_approval_service")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Prove the service binds the real application callable, not itself.
            self.assertIs(
                module.run_approve_order_final_price,
                application_approve_order_final_price,
            )
            self.assertIsNot(
                module.approve_order_final_price,
                module.run_approve_order_final_price,
            )

            # Same kwargs shape as AlmdinaCostWorkspaceAPI.approveFinalPrice (+ optional note).
            result = module.approve_order_final_price(
                order_name="DCO-RPC-1",
                expected_price_basis_token=token,
                approval_note="ملاحظة RPC",
            )
            cancelled = module.cancel_order_final_price_approval(
                order_name="DCO-RPC-1",
                expected_current_price_approval=result["current_price_approval"],
            )
        finally:
            sys.modules.pop("_almdina_final_price_approval_service_rpc_test", None)
            sys.modules.pop(
                "almdina_erp.almdina_erp.services.final_price_approval_service",
                None,
            )
            for name, previous_module in previous.items():
                if previous_module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous_module

        self.assertEqual(result["order_name"], "DCO-RPC-1")
        self.assertEqual(result["price_approval_status"], PRICE_APPROVAL_STATUS_APPROVED)
        self.assertEqual(result["price_basis_token"], token)
        self.assertEqual(result["approval_note"], "ملاحظة RPC")
        self.assertTrue(result["current_price_approval"])
        self.assertTrue(cancelled["cancelled_now"])
        self.assertFalse(cancelled["final_price_approval_invalidated"])
        self.assertEqual(cancelled["price_approval_status"], "Unapproved")
        self.assertIn("approval:DCPA-", "".join(gateway.locks))

    def test_service_source_uses_explicit_use_case_alias(self) -> None:
        source = SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "approve_order_final_price as run_approve_order_final_price",
            source,
        )
        self.assertIn(
            "cancel_order_final_price_approval as run_cancel_order_final_price_approval",
            source,
        )
        approve_body = source.split("def approve_order_final_price", 1)[1]
        approve_body = approve_body.split("def cancel_order_final_price_approval", 1)[0]
        self.assertIn("run_approve_order_final_price(", approve_body)
        self.assertNotIn(
            "\n        result = approve_order_final_price(",
            approve_body,
        )
        cancel_body = source.split("def cancel_order_final_price_approval", 1)[1]
        cancel_body = cancel_body.split("def maybe_invalidate_final_price_approval", 1)[0]
        self.assertIn("run_cancel_order_final_price_approval(", cancel_body)
        self.assertNotIn(
            "\n        result = cancel_order_final_price_approval(",
            cancel_body,
        )


if __name__ == "__main__":
    unittest.main()
