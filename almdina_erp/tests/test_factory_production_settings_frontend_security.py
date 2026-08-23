from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js"
MODULE_ROOT = ROOT / "public" / "js" / "factory_production_settings"
MODULES = tuple(MODULE_ROOT / name for name in (
    "api.js",
    "state.js",
    "view_model.js",
    "renderer.js",
    "interactions.js",
    "dialogs.js",
    "controller.js",
))


class FactoryProductionSettingsFrontendSecurityTest(unittest.TestCase):
    def test_page_local_modules_have_no_role_name_authority(self) -> None:
        surface = "\n".join(path.read_text(encoding="utf-8") for path in (PAGE, *MODULES))
        for role in (
            "Production Manager",
            "System Manager",
            "Accounts Manager",
            "Accounts User",
            "Order Entry",
            "CNC Worker",
            "Drawing Worker",
        ):
            self.assertNotIn(role, surface)
        for pattern in (
            r"frappe\.get_roles\(",
            r"frappe\.user_roles",
            r"has_role\(",
            r"require_roles\(",
            r"require_any_role",
        ):
            self.assertIsNone(re.search(pattern, surface), pattern)

    def test_section_editability_stays_server_payload_driven(self) -> None:
        view_model = (MODULE_ROOT / "view_model.js").read_text(encoding="utf-8")
        controller = (MODULE_ROOT / "controller.js").read_text(encoding="utf-8")

        self.assertIn("current.permissions.sections", view_model)
        self.assertIn("viewModel.sectionEditable(state.current, section)", controller)
        self.assertNotIn("frappe.call(", controller)


if __name__ == "__main__":
    unittest.main()
