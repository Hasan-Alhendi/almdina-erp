from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_PATH = ROOT / "resource_permissions.py"
HOOKS_PATH = ROOT / "hooks.py"
GATEWAY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
)


def load_resource_permissions(granted: set[str]):
    fake_frappe = types.ModuleType("frappe")
    fake_frappe.session = SimpleNamespace(user="worker@example.com")

    fake_gateway = types.ModuleType(GATEWAY_MODULE)
    fake_gateway.doctype_has_capability = (
        lambda capability, user=None: capability in granted
    )
    fake_gateway.doctype_has_any_capability = (
        lambda capabilities, user=None: any(capability in granted for capability in capabilities)
    )

    previous_frappe = sys.modules.get("frappe")
    previous_gateway = sys.modules.get(GATEWAY_MODULE)
    sys.modules["frappe"] = fake_frappe
    sys.modules[GATEWAY_MODULE] = fake_gateway
    try:
        spec = importlib.util.spec_from_file_location(
            "_almdina_resource_permission_hook_test",
            RESOURCE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load resource permission hooks")
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


class TestResourcePermissionHooks(unittest.TestCase):
    def test_empty_matrix_denies_direct_master_data_access(self) -> None:
        module = load_resource_permissions(set())
        doc = SimpleNamespace()

        self.assertEqual(module.customer_query("worker@example.com"), "1=0")
        self.assertFalse(
            module.customer_has_permission(doc, user="worker@example.com", ptype="read")
        )
        self.assertEqual(module.edge_banding_type_query("worker@example.com"), "1=0")
        self.assertEqual(module.production_routing_query("worker@example.com"), "1=0")

        for function in (
            module.edge_banding_type_has_permission,
            module.production_routing_has_permission,
        ):
            for ptype in ("read", "create", "write", "delete"):
                with self.subTest(function=function.__name__, ptype=ptype):
                    self.assertFalse(
                        function(doc, user="worker@example.com", ptype=ptype)
                    )

        self.assertFalse(
            module.factory_settings_has_permission(
                doc,
                user="worker@example.com",
                ptype="read",
            )
        )

    def test_order_input_capability_allows_lookup_but_not_administration_mutations(self) -> None:
        module = load_resource_permissions({Capability.CREATE_ORDER})
        doc = SimpleNamespace()

        self.assertEqual(module.customer_query("entry@example.com"), "")
        self.assertTrue(
            module.customer_has_permission(doc, user="entry@example.com", ptype="read")
        )
        for ptype in ("create", "write", "delete"):
            self.assertFalse(
                module.customer_has_permission(doc, user="entry@example.com", ptype=ptype)
            )

        self.assertEqual(module.edge_banding_type_query("entry@example.com"), "")
        self.assertTrue(
            module.edge_banding_type_has_permission(
                doc,
                user="entry@example.com",
                ptype="read",
            )
        )
        for ptype in ("create", "write", "delete"):
            self.assertFalse(
                module.edge_banding_type_has_permission(
                    doc,
                    user="entry@example.com",
                    ptype=ptype,
                )
            )

    def test_explicit_master_data_actions_map_one_to_one(self) -> None:
        module = load_resource_permissions(
            {
                Capability.VIEW_CUSTOMERS,
                Capability.CREATE_CUSTOMERS,
                Capability.VIEW_EDGE_BANDING_TYPES,
                Capability.EDIT_EDGE_BANDING_TYPES,
                Capability.VIEW_PRODUCTION_ROUTINGS,
                Capability.CREATE_PRODUCTION_ROUTINGS,
            }
        )
        doc = SimpleNamespace()

        self.assertTrue(
            module.customer_has_permission(doc, user="admin@example.com", ptype="read")
        )
        self.assertTrue(
            module.customer_has_permission(doc, user="admin@example.com", ptype="create")
        )
        self.assertFalse(
            module.customer_has_permission(doc, user="admin@example.com", ptype="write")
        )
        self.assertFalse(
            module.customer_has_permission(doc, user="admin@example.com", ptype="delete")
        )

        self.assertTrue(
            module.edge_banding_type_has_permission(
                doc,
                user="manager@example.com",
                ptype="write",
            )
        )
        self.assertFalse(
            module.edge_banding_type_has_permission(
                doc,
                user="manager@example.com",
                ptype="create",
            )
        )
        self.assertTrue(
            module.production_routing_has_permission(
                doc,
                user="manager@example.com",
                ptype="create",
            )
        )
        self.assertFalse(
            module.production_routing_has_permission(
                doc,
                user="manager@example.com",
                ptype="write",
            )
        )

    def test_settings_direct_write_is_denied_for_non_administrator(self) -> None:
        module = load_resource_permissions({Capability.VIEW_FACTORY_SETTINGS})
        doc = SimpleNamespace()
        self.assertTrue(
            module.factory_settings_has_permission(
                doc,
                user="settings@example.com",
                ptype="read",
            )
        )
        self.assertFalse(
            module.factory_settings_has_permission(
                doc,
                user="settings@example.com",
                ptype="write",
            )
        )

    def test_administrator_remains_explicit_superuser(self) -> None:
        module = load_resource_permissions(set())
        doc = SimpleNamespace()
        self.assertEqual(module.customer_query("Administrator"), "")
        self.assertEqual(module.edge_banding_type_query("Administrator"), "")
        self.assertEqual(module.production_routing_query("Administrator"), "")
        self.assertTrue(
            module.customer_has_permission(doc, user="Administrator", ptype="write")
        )
        self.assertTrue(
            module.factory_settings_has_permission(
                doc,
                user="Administrator",
                ptype="write",
            )
        )

    def test_hooks_register_every_direct_resource_guard(self) -> None:
        hooks = HOOKS_PATH.read_text(encoding="utf-8")
        for doctype, query_name, permission_name in (
            ("Customer", "customer_query", "customer_has_permission"),
            ("Edge Banding Type", "edge_banding_type_query", "edge_banding_type_has_permission"),
            ("Production Routing", "production_routing_query", "production_routing_has_permission"),
        ):
            self.assertIn(f'"{doctype}": "almdina_erp.resource_permissions.{query_name}"', hooks)
            self.assertIn(f'"{doctype}": "almdina_erp.resource_permissions.{permission_name}"', hooks)
        self.assertIn(
            '"Almdina ERP Settings": "almdina_erp.resource_permissions.factory_settings_has_permission"',
            hooks,
        )


if __name__ == "__main__":
    unittest.main()
