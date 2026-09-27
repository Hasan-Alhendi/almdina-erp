from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
UX = ROOT / "public" / "js" / "edge_banding_type_ux.js"
CSS = ROOT / "public" / "css" / "edge_banding_type_form.css"


class TestEdgeBandingTypeFormUX(unittest.TestCase):
    def test_form_assets_are_registered(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("edge_banding_type_form.css", manifest)
        self.assertIn('"Edge Banding Type": "public/js/edge_banding_type_ux.js"', manifest)

    def test_form_ux_is_presentation_only(self) -> None:
        source = UX.read_text(encoding="utf-8")
        self.assertIn("ebt-form-card", source)
        self.assertIn("configurePageActions", source)
        self.assertIn("bindLifecycle", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("frappe.db", source)

    def test_form_css_is_scoped_to_edge_banding_form(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("body.ebt-form-active", css)
        self.assertIn('[id="page-Edge Banding Type"]', css)
        self.assertIn(".ebt-form-callout", css)


if __name__ == "__main__":
    unittest.main()
