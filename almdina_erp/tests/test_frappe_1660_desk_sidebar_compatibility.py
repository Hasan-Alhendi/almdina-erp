"""Behavioral regressions for Frappe 16.60 desk Dock / module_sidebars compatibility."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.tests.test_read_only_boot_authorization import BootHarness


ROOT = Path(__file__).resolve().parents[1]
DOCK_JSON = ROOT / "dock" / "almdina_erp" / "almdina_erp.json"
DESK_SIDEBAR_UX = ROOT / "public" / "js" / "almdina_desk_sidebar_ux.js"
NATIVE_NAV = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "native_app_navigation.py"
)
PATCHES = ROOT / "patches.txt"


class TestFrappe1660DeskSidebarCompatibility(unittest.TestCase):
    def test_shipped_standard_dock_names_primary_almdina_shell(self) -> None:
        payload = json.loads(DOCK_JSON.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("doctype"), "Dock")
        self.assertEqual(payload.get("app"), "almdina_erp")
        self.assertEqual(int(payload.get("standard") or 0), 1)
        self.assertEqual(payload.get("name"), "almdina_erp")
        link_tos = [row.get("link_to") for row in payload.get("items") or []]
        self.assertIn("Almdina ERP", link_tos)
        self.assertIn("Almdina Reports", link_tos)

    def test_site_dock_reset_is_wired_and_surgical(self) -> None:
        patches = PATCHES.read_text(encoding="utf-8")
        nav = NATIVE_NAV.read_text(encoding="utf-8")
        patch = (ROOT / "patches" / "v1_0" / "reset_almdina_site_dock_layers.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("reset_almdina_site_dock_layers", patches)
        self.assertIn("list_incomplete_almdina_dock_layers", nav)
        self.assertIn("dock_layer_has_primary_shell", nav)
        self.assertIn("PRIMARY_SHELL", nav)
        self.assertIn("list_incomplete_almdina_dock_layers", patch)
        # after_migrate must filter to incomplete layers, not wipe every standard=0 row.
        self.assertIn("names = list_incomplete_almdina_dock_layers()", nav)
        self.assertNotIn(
            'filters={"app": ALMDINA_APP, "standard": 0},\n        pluck="name",\n    )\n    if not names:\n        return False\n\n    for name in names:\n        frappe.delete_doc("Dock", name, force=True, ignore_permissions=True)',
            nav,
        )

    def test_incomplete_dock_detection_keeps_complete_custom_layers(self) -> None:
        import importlib
        import sys
        import types

        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = types.SimpleNamespace(exists=lambda *args, **kwargs: True)

        def fake_get_all(doctype, filters=None, fields=None, pluck=None):
            if doctype == "Dock":
                return ["dock-complete", "dock-reports-only"]
            if doctype == "Dock Item":
                parent = (filters or {}).get("parent")
                if parent == "dock-complete":
                    return [
                        {"link_type": "Sidebar", "link_to": "Almdina ERP", "hidden": 0},
                        {"link_type": "Sidebar", "link_to": "Almdina Reports", "hidden": 0},
                    ]
                return [{"link_type": "Sidebar", "link_to": "Almdina Reports", "hidden": 0}]
            return []

        fake_frappe.get_all = fake_get_all
        previous = sys.modules.get("frappe")
        sys.modules["frappe"] = fake_frappe
        module_name = "almdina_erp.almdina_erp.infrastructure.frappe.native_app_navigation"
        sys.modules.pop(module_name, None)
        try:
            nav = importlib.import_module(module_name)
            self.assertTrue(nav.dock_layer_has_primary_shell("dock-complete"))
            self.assertFalse(nav.dock_layer_has_primary_shell("dock-reports-only"))
            self.assertEqual(
                nav.list_incomplete_almdina_dock_layers(),
                ["dock-reports-only"],
            )
        finally:
            sys.modules.pop(module_name, None)
            if previous is not None:
                sys.modules["frappe"] = previous
            else:
                sys.modules.pop("frappe", None)

    def test_app_only_boot_keeps_almdina_module_sidebars_and_home_shell(self) -> None:
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
            "home_shell": "Build",
            "module_sidebars": {
                "Build": {
                    "app": "frappe",
                    "module": "Build",
                    "items": [{"type": "Link", "link_type": "DocType", "link_to": "DocType", "label": "DocType"}],
                },
                "Almdina ERP": {
                    "app": "almdina_erp",
                    "module": "Almdina ERP",
                    "items": [
                        {
                            "type": "Link",
                            "link_type": "DocType",
                            "link_to": "Door Cutting Order",
                            "label": "طلبات قص الدرف",
                        },
                        {
                            "type": "Link",
                            "link_type": "Page",
                            "link_to": "factory-permissions",
                            "label": "إدارة الصلاحيات",
                        },
                        {
                            "type": "Link",
                            "link_type": "Workspace",
                            "link_to": "Almdina ERP",
                            "label": "الرئيسية",
                        },
                        {"type": "Section Break", "label": "صالة الإنتاج"},
                    ],
                },
                "Accounts": {
                    "app": "erpnext",
                    "module": "Accounts",
                    "items": [{"type": "Link", "link_type": "DocType", "link_to": "Account", "label": "Account"}],
                },
            },
            "dock": {
                "frappe": [{"link_type": "Sidebar", "link_to": "Build"}],
                "erpnext": [{"link_type": "Sidebar", "link_to": "Accounts"}],
                "almdina_erp": [{"link_type": "Sidebar", "link_to": "Almdina ERP"}],
            },
            "entity_module": {
                "Door Cutting Order": "Almdina ERP",
                "Account": "Accounts",
                "DocType": "Build",
            },
            "canonical_shell": {
                "DocType": {
                    "Door Cutting Order": "Almdina ERP",
                    "Account": "Accounts",
                }
            },
            "app_data": [
                {"app_name": "almdina_erp", "dock": [{"link_type": "Sidebar", "link_to": "Almdina ERP"}]},
                {"app_name": "erpnext", "dock": [{"link_type": "Sidebar", "link_to": "Accounts"}]},
                {"app_name": "frappe", "dock": [{"link_type": "Sidebar", "link_to": "Build"}]},
            ],
            "workspaces": {
                "pages": [
                    {"name": "Almdina ERP", "module": "Almdina ERP", "app": "almdina_erp"},
                    {"name": "Stock", "module": "Stock", "app": "erpnext"},
                ]
            },
        }

        boot.boot_session(bootinfo)

        self.assertEqual(set(bootinfo["module_sidebars"]), {"Almdina ERP"})
        items = bootinfo["module_sidebars"]["Almdina ERP"]["items"]
        link_tos = [row.get("link_to") for row in items if row.get("type") == "Link"]
        self.assertIn("Door Cutting Order", link_tos)
        self.assertIn("Almdina ERP", link_tos)
        self.assertNotIn("factory-permissions", link_tos)
        self.assertEqual(bootinfo["home_shell"], "Almdina ERP")
        self.assertEqual(set(bootinfo["dock"]), {"almdina_erp"})
        self.assertEqual(bootinfo["entity_module"], {"Door Cutting Order": "Almdina ERP"})
        self.assertEqual(
            bootinfo["canonical_shell"]["DocType"],
            {"Door Cutting Order": "Almdina ERP"},
        )
        self.assertEqual([row["app_name"] for row in bootinfo["app_data"]], ["almdina_erp"])
        self.assertEqual(bootinfo["almdina_allowed_apps"], ["almdina_erp"])

    def test_administrator_boot_keeps_foreign_shells(self) -> None:
        boot = BootHarness({}, user="Administrator").load()
        bootinfo = {
            "home_shell": "Accounts",
            "module_sidebars": {
                "Accounts": {"app": "erpnext", "module": "Accounts", "items": []},
                "Almdina ERP": {"app": "almdina_erp", "module": "Almdina ERP", "items": []},
            },
            "dock": {
                "erpnext": [{"link_type": "Sidebar", "link_to": "Accounts"}],
                "almdina_erp": [{"link_type": "Sidebar", "link_to": "Almdina ERP"}],
            },
            "app_data": [
                {"app_name": "erpnext", "app_route": "/desk/home"},
                {"app_name": "almdina_erp", "app_route": "/desk"},
            ],
        }
        boot.boot_session(bootinfo)
        self.assertEqual(set(bootinfo["module_sidebars"]), {"Accounts", "Almdina ERP"})
        self.assertEqual(set(bootinfo["dock"]), {"erpnext", "almdina_erp"})
        self.assertEqual(bootinfo["home_shell"], "Accounts")
        self.assertEqual(
            bootinfo["app_data"][1]["app_route"],
            "/desk/almdina-erp",
        )
        self.assertNotIn("almdina_allowed_apps", bootinfo)

    def test_desk_sidebar_ux_boots_on_module_sidebars(self) -> None:
        source = DESK_SIDEBAR_UX.read_text(encoding="utf-8")
        self.assertIn("module_sidebars", source)
        self.assertIn("sidebarBootContainer", source)
        self.assertIn("workspace_sidebar_item", source)


if __name__ == "__main__":
    unittest.main()
