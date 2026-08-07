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
    def __init__(self, user: str = "worker@example.com"):
        super().__init__("frappe")
        self.session = SimpleNamespace(user=user)
        self.local = SimpleNamespace()
        self.cache = lambda: _FakeCache()
        self.get_roles = lambda user=None: ["Some Role"]
        self._ = lambda value: value
        self.PermissionError = PermissionError


class BootHarness:
    def __init__(self, granted, *, user: str = "worker@example.com"):
        self.granted = frozenset(granted)
        self.frappe = _FakeFrappe(user=user)

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
        self.assertEqual(bootinfo["home_page"], "almdina-erp")
        self.assertEqual(bootinfo["default_route"], "/desk/almdina-erp")
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            ["Almdina ERP"],
        )
        self.assertEqual([row["name"] for row in bootinfo["app_data"]], ["almdina_erp"])
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertTrue(context["navigation"]["app_only"])
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
        self.assertEqual(bootinfo["home_page"], "shop-floor-inbox")
        self.assertEqual(bootinfo["default_route"], "/app/shop-floor-inbox")
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            ["Shop Floor"],
        )
        self.assertEqual([row["name"] for row in bootinfo["app_data"]], ["almdina_erp"])
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertTrue(context["navigation"]["app_only"])
        self.assertNotIn("almdina_shop_floor_only", bootinfo)
        self.assertNotIn("almdina_order_entry_only", bootinfo)

    def test_supervisor_capabilities_expand_same_shell(self) -> None:
        boot = BootHarness(
            {
                Capability.VIEW_ORDERS,
                Capability.REASSIGN_WORKER,
                Capability.VIEW_COSTS,
                Capability.VIEW_FACTORY_SETTINGS,
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
        self.assertEqual(bootinfo["home_page"], "almdina-erp")
        self.assertEqual(bootinfo["default_route"], "/desk/almdina-erp")
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
        self.assertTrue(context["navigation"]["app_only"])
        self.assertFalse(context["navigation"]["sections"]["reports"])

    def test_builtin_administrator_keeps_complete_frappe_desktop(self) -> None:
        boot = BootHarness(
            {Capability.MANAGE_PERMISSIONS},
            user="Administrator",
        ).load()
        bootinfo = {
            "workspaces": {
                "pages": [
                    {"name": "Almdina ERP", "module": "Almdina ERP", "app": "almdina_erp"},
                    {"name": "Stock", "module": "Stock", "app": "erpnext"},
                ]
            },
            "app_data": [
                {"app_name": "almdina_erp", "app_route": "/desk"},
                {"app_name": "erpnext", "app_route": "/desk/accounting"},
            ],
            "module_wise_workspaces": {
                "Almdina ERP": ["Almdina ERP"],
                "Stock": ["Stock"],
            },
        }

        boot.boot_session(bootinfo)

        context = bootinfo["almdina_permissions"]
        self.assertEqual(bootinfo["home_page"], "desktop")
        self.assertEqual(bootinfo["default_route"], "/desk/desktop")
        self.assertFalse(context["navigation"]["app_only"])
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            ["Almdina ERP", "Stock"],
        )
        self.assertEqual(
            [row["app_name"] for row in bootinfo["app_data"]],
            ["almdina_erp", "erpnext"],
        )
        self.assertEqual(bootinfo["app_data"][0]["app_route"], "/desk/almdina-erp")
        self.assertEqual(bootinfo["app_data"][1]["app_route"], "/desk/accounting")
        self.assertNotIn("almdina_allowed_apps", bootinfo)

    def test_no_default_password_is_stored_in_install_or_provisioning_code(self) -> None:
        combined = INSTALL_PATH.read_text(encoding="utf-8") + PROVISION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_OPERATOR_PASSWORD", combined)
        self.assertNotIn("Almdina@123", combined)
        self.assertNotIn("update_password", INSTALL_PATH.read_text(encoding="utf-8"))

    def test_install_does_not_seed_fixed_roles_users_or_routes(self) -> None:
        source = INSTALL_PATH.read_text(encoding="utf-8")
        for token in (
            "ROLES =",
            "OPERATOR_USERS =",
            "ORDER_ENTRY_USERS =",
            "DEFAULT_ROUTING_NAME",
            "def seed_roles",
            "def seed_operator_users",
            "def seed_order_entry_users",
            "def seed_default_routing",
        ):
            self.assertNotIn(token, source)
        self.assertIn("without inventing roles, users, or routes", source)
        self.assertNotIn('"default_production_routing":', source)


if __name__ == "__main__":
    unittest.main()
