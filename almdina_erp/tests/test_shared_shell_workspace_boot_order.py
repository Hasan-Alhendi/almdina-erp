from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"
NAVIGATION = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "navigation_context.py"
)


class TestSharedShellWorkspaceBootOrder(unittest.TestCase):
    def test_client_does_not_mutate_workspace_boot_registry(self) -> None:
        source = SHARED_SHELL.read_text(encoding="utf-8")

        self.assertNotIn("trimBootMetadata", source)
        self.assertNotIn("frappe.boot.workspaces.pages =", source)
        self.assertNotIn("frappe.boot.allowed_workspaces =", source)

    def test_home_route_waits_for_frappe_workspace_registry(self) -> None:
        source = SHARED_SHELL.read_text(encoding="utf-8")

        self.assertIn('app_ready.almdinaSharedShell', source)
        self.assertIn("frappe.router.current_route !== null", source)
        self.assertIn("registeredWorkspace", source)
        self.assertIn("resolveHomeRoute", source)
        self.assertIn("Object.prototype.hasOwnProperty.call(frappe.workspaces, key)", source)
        self.assertLess(source.index("function deskIsReady"), source.index("function waitForDesk"))

    def test_main_profiles_use_real_workspace_slug(self) -> None:
        source = NAVIGATION.read_text(encoding="utf-8")

        self.assertIn('WORKSPACE_MAIN_ROUTE = "almadina-erp"', source)
        self.assertIn('else f"/desk/{WORKSPACE_MAIN_ROUTE}"', source)
        self.assertIn('else WORKSPACE_MAIN_ROUTE', source)


if __name__ == "__main__":
    unittest.main()
