from __future__ import annotations

import importlib.util
import runpy
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.domain.security.authorization import Capability


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BOOT_PATH = REPOSITORY_ROOT / "almdina_erp/boot.py"
HOOKS_PATH = REPOSITORY_ROOT / "almdina_erp/hooks.py"
INSTALL_PATH = REPOSITORY_ROOT / "almdina_erp/install.py"
PROVISION_PATH = (
    REPOSITORY_ROOT
    / "almdina_erp/almdina_erp/application/security/provision_user.py"
)
GATEWAY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
)


class BootHarness:
    def __init__(self, roles: set[str], grants: set[str]) -> None:
        self.roles = roles
        self.grants = grants

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.get_roles = lambda *args, **kwargs: list(self.roles)
        fake_frappe.session = SimpleNamespace(user="user@example.com")

        fake_gateway = types.ModuleType(GATEWAY_MODULE)
        fake_gateway.granted_capabilities = lambda *args, **kwargs: frozenset(
            self.grants
        )

        previous_frappe = sys.modules.get("frappe")
        previous_gateway = sys.modules.get(GATEWAY_MODULE)
        sys.modules["frappe"] = fake_frappe
        sys.modules[GATEWAY_MODULE] = fake_gateway
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_read_only_boot_test",
                BOOT_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load read-only boot adapter")
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


class TestReadOnlyBootAuthorization(unittest.TestCase):
    def test_hooks_use_read_only_boot_adapter_and_lifecycle_coordinator(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(hooks["boot_session"], "almdina_erp.boot.boot_session")
        self.assertEqual(hooks["extend_bootinfo"], ["almdina_erp.boot.extend_bootinfo"])
        self.assertEqual(hooks["after_install"], "almdina_erp.lifecycle.after_install")
        self.assertEqual(hooks["after_migrate"], "almdina_erp.lifecycle.after_migrate")

    def test_boot_adapter_contains_no_database_or_user_mutation(self) -> None:
        source = BOOT_PATH.read_text(encoding="utf-8")
        forbidden = (
            "frappe.db.",
            "frappe.get_doc(",
            ".save(",
            ".insert(",
            ".add_roles(",
            ".commit(",
            "apply_order_entry_user_restrictions",
            "apply_shop_floor_user_restrictions",
        )
        leaked = [fragment for fragment in forbidden if fragment in source]
        self.assertEqual(leaked, [])

    def test_order_entry_boot_uses_resolved_permission_grants(self) -> None:
        boot = BootHarness(
            {"Order Entry"},
            {Capability.CREATE_ORDER, Capability.PRINT_MEASUREMENTS},
        ).load()
        bootinfo = {
            "module_wise_workspaces": {
                "Almdina ERP": ["Almdina ERP"],
                "Stock": ["Stock"],
            },
            "workspaces": {
                "pages": [
                    {"name": "Almdina ERP", "module": "Almdina ERP"},
                    {"name": "Stock", "module": "Stock"},
                ]
            },
            "desktop_icons": [
                {"module_name": "Almdina ERP", "label": "Almdina ERP"},
                {"module_name": "Stock", "label": "Stock"},
            ],
        }
        boot.boot_session(bootinfo)
        self.assertEqual(bootinfo["almdina_order_entry_only"], 1)
        self.assertEqual(list(bootinfo["module_wise_workspaces"]), ["Almdina ERP"])
        context = bootinfo["almdina_permissions"]
        self.assertEqual(context["profile"], "order_entry")
        self.assertTrue(context["capabilities"][Capability.CREATE_ORDER])
        self.assertFalse(context["capabilities"][Capability.VIEW_COSTS])

    def test_shop_floor_boot_preserves_shared_almdina_shell(self) -> None:
        boot = BootHarness(
            {"عامل رسم"},
            {Capability.UPLOAD_DXF, Capability.APPROVE_DXF},
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
        self.assertEqual(bootinfo["almdina_shop_floor_only"], 1)
        self.assertEqual(bootinfo["default_route"], "/app/shop-floor-inbox")
        self.assertEqual(
            [row["name"] for row in bootinfo["workspaces"]["pages"]],
            ["Almdina ERP", "Shop Floor"],
        )
        self.assertEqual([row["name"] for row in bootinfo["app_data"]], ["almdina_erp"])
        context = bootinfo["almdina_permissions"]
        self.assertEqual(context["profile"], "shop_floor")
        self.assertTrue(context["capabilities"][Capability.UPLOAD_DXF])
        self.assertTrue(context["capabilities"][Capability.APPROVE_DXF])

    def test_full_profile_receives_only_assigned_capabilities(self) -> None:
        boot = BootHarness(
            {"Accounts Management"},
            {Capability.VIEW_COSTS},
        ).load()
        bootinfo: dict[str, object] = {}
        boot.boot_session(bootinfo)
        context = bootinfo["almdina_permissions"]
        self.assertEqual(context["profile"], "full")
        self.assertTrue(context["capabilities"][Capability.VIEW_COSTS])
        self.assertFalse(context["capabilities"][Capability.UPLOAD_DXF])

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
