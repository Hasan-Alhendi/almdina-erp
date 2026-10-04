from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
CSS = ROOT / "public" / "css" / "almdina_workspace_home.css"
JS = ROOT / "public" / "js" / "almdina_workspace_home_ux.js"
PRESENTATION = ROOT / "public" / "js" / "almdina_shortcut_presentation.js"
TOKENS = ROOT / "public" / "css" / "almdina_design_tokens.css"


class TestAlmdinaWorkspaceHomeUX(unittest.TestCase):
    def test_workspace_home_assets_are_registered_globally(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("almdina_workspace_home.css", manifest)
        self.assertIn("almdina_workspace_home_ux.js", manifest)
        self.assertIn("almdina_shortcut_presentation.js", manifest)
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
        self.assertIn("AlmdinaShortcutPresentation", source)
        self.assertIn("es-line-reports", source)
        # Stable identity: block id / link_to — not visible Arabic labels.
        self.assertIn("SHORTCUT_BLOCK_TO_LINK", source)
        self.assertIn('"factory-workforce"', source)
        self.assertIn("data-alm-link-to", source)
        self.assertIn("const observers = new Set()", source)
        self.assertIn("disposeObservers", source)
        self.assertIn("app_ready.almdinaWorkspaceHome", source)
        self.assertNotIn("waitForDesk", source)
        self.assertNotIn('label === "', source)
        self.assertNotIn("data-alm-control-watch", source)

    def test_shortcut_presentation_keys_by_stable_link_to(self) -> None:
        source = PRESENTATION.read_text(encoding="utf-8")
        self.assertIn("SHORTCUT_BY_LINK_TO", source)
        self.assertIn("metaForLinkTo", source)
        self.assertIn("metaForRoute", source)
        self.assertIn('"factory-workforce"', source)
        self.assertIn('"Door Cutting Order"', source)
        self.assertIn("LABEL_TO_LINK_TO", source)

    def test_workspace_home_css_is_scoped_to_main_workspace_route(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        tokens = TOKENS.read_text(encoding="utf-8")
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
        # Identity colors live in design tokens, not feature hex literals.
        self.assertIn("--alm-accent-purple", tokens)
        self.assertIn("--alm-accent-blue", tokens)
        self.assertIn("var(--alm-accent-purple)", css)
        self.assertNotIn("#7c3aed", css)
        self.assertNotIn("#2563eb", css)
        important_count = css.count("!important")
        self.assertLessEqual(important_count, 8)
        self.assertIn("var(--alm-canvas)", css)


if __name__ == "__main__":
    unittest.main()
