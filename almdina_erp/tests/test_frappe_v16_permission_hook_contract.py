from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PERMISSIONS_PATH = Path(__file__).resolve().parents[1] / "permissions.py"
GATEWAY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
)


def load_permissions_module():
    fake_frappe = types.ModuleType("frappe")
    fake_frappe.session = SimpleNamespace(user="test@example.com")
    fake_frappe.db = SimpleNamespace()

    fake_gateway = types.ModuleType(GATEWAY_MODULE)
    fake_gateway.doctype_has_capability = lambda *_args, **_kwargs: False

    previous_frappe = sys.modules.get("frappe")
    previous_gateway = sys.modules.get(GATEWAY_MODULE)
    sys.modules["frappe"] = fake_frappe
    sys.modules[GATEWAY_MODULE] = fake_gateway
    try:
        spec = importlib.util.spec_from_file_location(
            "_almdina_frappe_v16_permission_hook_contract",
            PERMISSIONS_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load permission hooks")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_frappe is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = previous_frappe
        if previous_gateway is None:
            sys.modules.pop(GATEWAY_MODULE, None)
        else:
            sys.modules[GATEWAY_MODULE] = previous_gateway


permissions = load_permissions_module()


class TestFrappeV16PermissionHookContract(unittest.TestCase):
    def test_broad_scope_document_hooks_return_explicit_true(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")
        stage = SimpleNamespace(assigned_to="other@example.com")

        with patch.object(permissions, "_requires_assigned_scope", return_value=False):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="order@example.com",
                    ptype="read",
                ),
                True,
            )
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="order@example.com",
                    ptype="write",
                ),
                True,
            )
            self.assertIs(
                permissions.production_stage_has_permission(
                    stage,
                    user="order@example.com",
                    ptype="read",
                ),
                True,
            )

    def test_assigned_scope_still_denies_unassigned_documents(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        with (
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(permissions, "_assigned_order_exists", return_value=False),
        ):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="worker@example.com",
                    ptype="read",
                ),
                False,
            )

    def test_frappe_ptype_keeps_custom_actions_outside_read_scope(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        with (
            patch.object(permissions, "_requires_assigned_scope", return_value=True),
            patch.object(permissions, "_assigned_order_exists") as assigned,
        ):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="worker@example.com",
                    ptype="recalculate_plan",
                ),
                True,
            )
            assigned.assert_not_called()

    def test_legacy_permission_type_keyword_remains_compatible(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        with patch.object(permissions, "_requires_assigned_scope", return_value=False):
            self.assertIs(
                permissions.door_cutting_order_has_permission(
                    order,
                    user="order@example.com",
                    permission_type="read",
                ),
                True,
            )

    def test_guest_read_is_denied_explicitly(self) -> None:
        order = SimpleNamespace(name="DCO-TEST")

        self.assertIs(
            permissions.door_cutting_order_has_permission(
                order,
                user="Guest",
                ptype="read",
            ),
            False,
        )


if __name__ == "__main__":
    unittest.main()
