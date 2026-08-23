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
BOOT = ROOT / "boot.py"
HOOKS = ROOT / "hooks.py"
PERMISSION_SERVICE = (
    ROOT
    / "almdina_erp"
    / "services"
    / "permission_context_service.py"
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
        self.assertIn("registeredPage", source)
        self.assertIn("resolveHomeRoute", source)
        self.assertIn("Object.prototype.hasOwnProperty.call(frappe.workspaces, key)", source)
        self.assertLess(source.index("function deskIsReady"), source.index("function waitForDesk"))

    def test_navigation_keeps_workspace_slug_but_does_not_own_landing(self) -> None:
        source = NAVIGATION.read_text(encoding="utf-8")

        self.assertIn('WORKSPACE_MAIN_ROUTE = "almdina-erp"', source)
        self.assertNotIn('default_route = f"/desk/{WORKSPACE_MAIN_ROUTE}"', source)
        self.assertNotIn("home_page = WORKSPACE_MAIN_ROUTE", source)
        self.assertNotIn('"home_page":', source)
        self.assertNotIn('"default_route":', source)

    def test_builtin_administrator_keeps_registered_desktop_ownership_in_frappe(self) -> None:
        navigation = NAVIGATION.read_text(encoding="utf-8")
        boot = BOOT.read_text(encoding="utf-8")
        service = PERMISSION_SERVICE.read_text(encoding="utf-8")

        self.assertIn('DESKTOP_PAGE_ROUTE = "desktop"', navigation)
        self.assertIn("system_administrator: bool = False", navigation)
        self.assertNotIn('default_route = f"/desk/{DESKTOP_PAGE_ROUTE}"', navigation)
        self.assertIn('SYSTEM_ADMINISTRATOR = "Administrator"', boot)
        self.assertIn("system_administrator=user == SYSTEM_ADMINISTRATOR", boot)
        self.assertIn('system_administrator=user == "Administrator"', service)
        self.assertNotIn('bootinfo["home_page"] =', boot)
        self.assertNotIn('bootinfo["default_route"] =', boot)

    def test_app_card_uses_native_frappe_workspace_route(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")

        self.assertIn('"route": "/desk/almdina-erp"', hooks)
        self.assertNotIn('"route": "/desk",', hooks)

    def test_administrator_app_card_is_not_rewritten_to_desktop(self) -> None:
        client = SHARED_SHELL.read_text(encoding="utf-8")
        boot = BOOT.read_text(encoding="utf-8")

        self.assertIn("!nav.app_only", client)
        self.assertIn('ALMDINA_WORKSPACE_ROUTE = "/desk/almdina-erp"', boot)
        self.assertIn("_set_almdina_app_route(bootinfo, ALMDINA_WORKSPACE_ROUTE)", boot)


if __name__ == "__main__":
    unittest.main()
