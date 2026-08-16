from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_workforce" / "factory_workforce.js"
MODULE_ROOT = ROOT / "public" / "js" / "factory_workforce"
MODULES = (
    MODULE_ROOT / "api.js",
    MODULE_ROOT / "state.js",
    MODULE_ROOT / "view_model.js",
    MODULE_ROOT / "renderer.js",
    MODULE_ROOT / "interactions.js",
    MODULE_ROOT / "dialogs.js",
    MODULE_ROOT / "controller.js",
)


class FactoryWorkforceFrontendSecurityTest(unittest.TestCase):
    def test_page_local_modules_have_no_browser_role_name_authority(self) -> None:
        surface = "\n".join(
            path.read_text(encoding="utf-8") for path in (PAGE, *MODULES)
        )
        fixed_roles = (
            "Production Manager",
            "System Manager",
            "Accounts Manager",
            "Accounts User",
            "Order Entry",
            "Sales Manager",
            "CNC Worker",
            "Drawing Worker",
        )
        for role in fixed_roles:
            self.assertNotIn(role, surface)
        for pattern in (
            r"frappe\.get_roles\(",
            r"frappe\.user_roles",
            r"has_role\(",
            r"require_roles\(",
            r"require_any_role",
        ):
            self.assertIsNone(re.search(pattern, surface), pattern)

    def test_actions_remain_server_payload_driven(self) -> None:
        view_model = (MODULE_ROOT / "view_model.js").read_text(encoding="utf-8")
        controller = (MODULE_ROOT / "controller.js").read_text(encoding="utf-8")

        self.assertIn("user.actions", view_model)
        self.assertIn('actionAllowed(user, "edit")', controller)
        self.assertIn('actionAllowed(user, "assign_roles")', controller)
        self.assertIn('actionAllowed(user, "reset_password")', controller)
        self.assertIn('actionAllowed(user, action)', controller)
        self.assertNotIn("frappe.call(", controller)


if __name__ == "__main__":
    unittest.main()
