from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
CSS = ROOT / "public" / "css" / "almdina_workspace_home.css"
JS = ROOT / "public" / "js" / "almdina_workspace_home_ux.js"


class TestAlmdinaWorkspaceHomeUX(unittest.TestCase):
    def test_workspace_home_assets_are_registered_globally(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("almdina_workspace_home.css", manifest)
        self.assertIn("almdina_workspace_home_ux.js", manifest)
        self.assertLess(manifest.index("almdina_desk_theme.css"), manifest.index("almdina_workspace_home.css"))
        self.assertLess(manifest.index("shared_shell.js"), manifest.index("almdina_workspace_home_ux.js"))

    def test_workspace_home_owner_is_presentation_only(self) -> None:
        source = JS.read_text(encoding="utf-8")
        self.assertIn("AlmdinaWorkspaceHomeUX", source)
        self.assertIn('WORKSPACE_SLUG = "almdina-erp"', source)
        self.assertIn("slugify", source)
        self.assertIn('WORKSPACE_NAME = "Almdina ERP"', source)
        self.assertNotIn("frappe.db", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("frappe.xcall", source)
        self.assertNotIn("hideUnauthorizedShortcuts", source)
        self.assertNotIn("workspace_api", source)
        self.assertNotIn("alm-workspace-hero", source)
        self.assertIn("SECTION_PRESENTATION", source)
        self.assertIn("assignShortcutSections", source)
        self.assertIn("normalizeWorkspaceTrail", source)
        self.assertIn("shortcutMeta", source)
        self.assertIn("es-line-chart", source)
        self.assertIn('"close"', source)

    def test_workspace_home_css_is_scoped_to_main_workspace_route(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("body.almdina-workspace-home", css)
        self.assertIn("#page-Workspaces", css)
        self.assertIn(".shortcut-widget-box", css)
        self.assertNotIn(".alm-workspace-hero", css)
        self.assertIn(".alm-workspace-section-meta", css)
        self.assertIn(".alm-workspace-shortcut-arrow", css)
        self.assertIn(".alm-workspace-shortcut-badge", css)
        self.assertIn("#page-Workspaces.page-container", css)
        self.assertNotRegex(css, r"\.page-head\s+\.page-title[^}]*display:\s*none")
        self.assertNotIn("#2490ef", css)


if __name__ == "__main__":
    unittest.main()
