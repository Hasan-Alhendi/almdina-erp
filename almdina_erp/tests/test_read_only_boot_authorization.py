from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.domain.security.authorization import Capability


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
BOOT_PATH = PACKAGE_ROOT / "boot.py"
HOOKS_PATH = PACKAGE_ROOT / "hooks.py"
INSTALL_PATH = PACKAGE_ROOT / "install.py"
PROVISION_PATH = (
    PACKAGE_ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "provision_user.py"
)


class _FakeCache:
    def get_value(self, key, generator=None):
        return generator() if generator else None


class _FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.session = SimpleNamespace(user="worker@example.com")
        self.local = SimpleNamespace()
        self.cache = lambda: _FakeCache()
        self.get_roles = lambda user=None: ["Some Role"]
        self._ = lambda value: value
        self.PermissionError = PermissionError


class BootHarness:
    def __init__(self, granted):
        self.granted = frozenset(granted)
        self.frappe = _FakeFrappe()

    def load(self):
        fake_gateway = types.ModuleType(
            "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
        )
        fake_gateway.granted_capabilities = lambda user=None: self.granted
        fake_context = types.ModuleType(
            "almdina_erp.almdina_erp.application.security.permission_context"
        )
        from almdina_erp.almdina_erp.application.security.permission_context import (
            build_permission_context,
        )

        fake_context.build_permission_context = build_permission_context
        module_name = "almdina_erp_test_boot"
        spec = importlib.util.spec_from_file_location(module_name, BOOT_PATH)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {
                "frappe": self.frappe,
                "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway": fake_gateway,
                "almdina_erp.almdina_erp.application.security.permission_context": fake_context,
            },
        ):
            assert spec and spec.loader
            spec.loader.exec_module(module)
        return module


class TestReadOnlyBootAuthorization(unittest.TestCase):
    def test_boot_adapter_contains_no_database_role_or_user_mutation(self) -> None:
        source = BOOT_PATH.read_text(encoding="utf-8")
        forbidden = (
            "frappe.get_doc(",
            "frappe.new_doc(",
            "frappe.db.set_value",
            "insert(ignore_permissions=True)",
            "save(ignore_permissions=True)",
            "update_password",
            "add_roles",
            "remove_roles",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertIn("granted_capabilities", source)
        self.assertIn("build_permission_context", source)

    def test_hooks_use_read_only_boot_adapter_and_shared_shell(self) -> None:
        source = HOOKS_PATH.read_text(encoding="utf-8")
        self.assertIn('boot_session = "almdina_erp.boot.boot_session"', source)
        self.assertIn('"/assets/almdina_erp/js/shared_shell.js"', source)
        self.assertNotIn("ensure_operator_account", source)
        self.assertNotIn('"/assets/almdina_erp/js/shop_floor_desk.js"', source)
        self.assertNotIn('"/assets/almdina_erp/js/order_entry_desk.js"', source)

    def test_order_entry_capabilities_keep_main_shared_shell(self) -> None:
        boot = BootHarness(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.EDIT_ORDER,
                Capability.SUBMIT_ORDER,
                Capability.PRINT_MEASUREMENTS,
            }
        ).load()
        bootinfo = {
            "workspaces": {
                "pages": [
                    {"name": "Almdina ERP", "module": "Almdina ERP", "app": "almdina_erp"},
                    {"name": "Shop Floor", "module": "Almdina ERP", "app": "almdina_erp"},
                    {"name": "Stock", "module": "Stock", "app": "erpnext"},
                ]
            },
            "app_data": [
                {"name": "almdina_erp"},
                {"name": "erpnext"},
            ],
            "module_wise_workspaces": {
                "Almdina ERP": ["Almdina ERP", "Shop Floor"],
                "Stock": ["Stock"],
            },
        }
        boot.boot_session(bootinfo)
        context = bootinfo["almdina_permissions"]
        self.assertEqual(context["profile"], "order_entry")
        self.assertEqual(bootinfo["home_page"], "almadina-erp")
        self.assertEqual(bootinfo["default_route"], "/desk/almadina-erp")
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            ["Almdina ERP"],
        )
        self.assertEqual([row["name"] for row in bootinfo["app_data"]], ["almdina_erp"])
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertNotIn("almdina_shop_floor_only", bootinfo)
        self.assertNotIn("almdina_order_entry_only", bootinfo)

    def test_operator_capabilities_use_shop_floor_home_without_hiding_desk(self) -> None:
        boot = BootHarness(
            {
                Capability.VIEW_ORDERS,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
                Capability.VIEW_CUTTING_PLAN,
                Capability.PRINT_CUTTING_PLAN,
                Capability.VIEW_DRAWING_WORKSPACE,
                Capability.UPLOAD_DXF,
            }
        ).load()
        bootinfo = {
            "workspaces": {
                "pages": [
                    {"name": "Almdina ERP", "module": "Almdina ERP", "app": "almdina_erp"},
                    {"name": "Shop Floor", "module": "Almdina ERP", "app": "almdina_erp"},
                    {"name": "Stock", "module": "Stock", "app": "erpnext"},
                ]
            },
            "app_data": [
                {"name": "almdina_erp"},
                {"name": "erpnext"},
            ],
            "module_wise_workspaces": {
                "Almdina ERP": ["Almdina ERP", "Shop Floor"],
                "Stock": ["Stock"],
            },
        }
        boot.boot_session(bootinfo)
        context = bootinfo["almdina_permissions"]
        self.assertEqual(context["profile"], "shop_floor")
        self.assertEqual(bootinfo["default_route"], "/app/shop-floor-inbox")
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            ["Shop Floor"],
        )
        self.assertEqual([row["name"] for row in bootinfo["app_data"]], ["almdina_erp"])
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertNotIn("almdina_shop_floor_only", bootinfo)
        self.assertNotIn("almdina_order_entry_only", bootinfo)

    def test_supervisor_capabilities_expand_same_shell(self) -> None:
        boot = BootHarness(
            {
                Capability.VIEW_ORDERS,
                Capability.REASSIGN_WORKER,
                Capability.VIEW_COSTS,
                Capability.MANAGE_FACTORY_SETTINGS,
            }
        ).load()
        bootinfo = {
            "workspaces": {
                "pages": [
                    {"name": "Almdina ERP", "module": "Almdina ERP"},
                    {"name": "Shop Floor", "module": "Almdina ERP"},
                    {"name": "Almdina Control Center", "module": "Almdina ERP"},
                    {"name": "Almdina Reports", "module": "Almdina ERP"},
                    {"name": "Almdina Settings", "module": "Almdina ERP"},
                ]
            }
        }
        boot.boot_session(bootinfo)
        context = bootinfo["almdina_permissions"]
        self.assertEqual(context["profile"], "full")
        self.assertEqual(bootinfo["home_page"], "almadina-erp")
        self.assertEqual(bootinfo["default_route"], "/desk/almadina-erp")
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            [
                "Almdina ERP",
                "Shop Floor",
                "Almdina Control Center",
                "Almdina Settings",
            ],
        )
        self.assertNotIn("Almdina Reports", context["navigation"]["workspaces"])
        self.assertTrue(context["navigation"]["sections"]["production"])
        self.assertTrue(context["navigation"]["sections"]["costing"])
        self.assertTrue(context["navigation"]["sections"]["factory_settings"])
        self.assertFalse(context["navigation"]["sections"]["reports"])

    def test_no_default_password_is_stored_in_install_or_provisioning_code(self) -> None:
        combined = INSTALL_PATH.read_text(encoding="utf-8") + PROVISION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_OPERATOR_PASSWORD", combined)
        self.assertNotIn("Almdina@123", combined)
        self.assertIn("temporary_password", combined)
        self.assertIn("Pass password explicitly", combined)

    def test_order_entry_seed_uses_least_privilege_profile(self) -> None:
        source = INSTALL_PATH.read_text(encoding="utf-8")
        self.assertIn('"profile": "order_entry"', source)
        order_entry_block = source.split("ORDER_ENTRY_USERS =", 1)[1].split("DEFAULT_ROUTING_NAME =", 1)[0]
        for broad_role in (
            "Production Manager",
            "Stock Manager",
            "Accounts Management",
            "Cutting Operator",
            "Edge Operator",
        ):
            self.assertNotIn(broad_role, order_entry_block)


if __name__ == "__main__":
    unittest.main()
