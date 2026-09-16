from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.tests.frappe_test_stub import install_if_unavailable


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.py"

# Framework-free unit runs still need the small import surface, while Bench
# integration runs must keep the real process-wide Frappe module intact.
install_if_unavailable()

from almdina_erp import resource_permissions  # noqa: E402


@contextmanager
def resource_permissions_with(granted: set[str]):
    """Isolate capability decisions without mutating ``sys.modules``.

    Replacing the root ``frappe`` module in a running Bench process corrupts
    Frappe's package/import state for tests that execute afterwards.  Patch the
    two imported gateway functions at the module seam instead; ``patch.object``
    restores both functions deterministically when the assertion scope exits.
    """

    def has_capability(capability, user=None):
        del user
        return capability in granted

    def has_any_capability(capabilities, user=None):
        del user
        return any(capability in granted for capability in capabilities)

    with (
        patch.object(
            resource_permissions,
            "doctype_has_capability",
            side_effect=has_capability,
        ),
        patch.object(
            resource_permissions,
            "doctype_has_any_capability",
            side_effect=has_any_capability,
        ),
    ):
        yield resource_permissions


class TestResourcePermissionHooks(unittest.TestCase):
    def test_empty_matrix_denies_direct_master_data_access(self) -> None:
        doc = SimpleNamespace()

        with resource_permissions_with(set()) as module:
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
        doc = SimpleNamespace()

        with resource_permissions_with({Capability.CREATE_ORDER}) as module:
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
        doc = SimpleNamespace()
        granted = {
            Capability.VIEW_CUSTOMERS,
            Capability.CREATE_CUSTOMERS,
            Capability.VIEW_EDGE_BANDING_TYPES,
            Capability.EDIT_EDGE_BANDING_TYPES,
            Capability.VIEW_PRODUCTION_ROUTINGS,
            Capability.CREATE_PRODUCTION_ROUTINGS,
        }

        with resource_permissions_with(granted) as module:
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
        doc = SimpleNamespace()
        with resource_permissions_with({Capability.VIEW_FACTORY_SETTINGS}) as module:
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
        doc = SimpleNamespace()
        with resource_permissions_with(set()) as module:
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
