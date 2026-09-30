from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
UX = ROOT / "public" / "js" / "role_form_ux.js"
CSS = ROOT / "public" / "css" / "role_form.css"


class TestRoleFormUX(unittest.TestCase):
    def test_form_assets_are_registered(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("role_form.css", manifest)
        self.assertIn('"Role": "public/js/role_form_ux.js"', manifest)

    def test_form_ux_is_presentation_only(self) -> None:
        source = UX.read_text(encoding="utf-8")
        self.assertIn("role-form-top-grid", source)
        self.assertIn("expandSectionFullWidth", source)
        self.assertIn("role-form-section-full", source)
        self.assertIn("home_page", source)
        self.assertIn("restrict_to_domain", source)
        self.assertIn("two_factor_auth", source)
        self.assertIn('frappe.ui.form.on("Role"', source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("frappe.db", source)

    def test_form_css_defines_two_row_grid(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("body.role-form-layout-active", css)
        self.assertIn('[id="page-Role"]', css)
        self.assertIn(".role-form-section-full", css)
        self.assertIn(".role-form-row--inputs", css)
        self.assertIn(".role-form-row--checks", css)
        self.assertIn("grid-template-columns: repeat(2", css)
        self.assertIn("grid-template-columns: repeat(4", css)


if __name__ == "__main__":
    unittest.main()
