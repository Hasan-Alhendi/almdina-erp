from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
PRESENTATION = ROOT / "public" / "js" / "almdina_shortcut_presentation.js"
SIDEBAR_JS = ROOT / "public" / "js" / "almdina_desk_sidebar_ux.js"
SIDEBAR_CSS = ROOT / "public" / "css" / "almdina_desk_sidebar.css"
WORKSPACE_HOME = ROOT / "public" / "js" / "almdina_workspace_home_ux.js"


class TestAlmdinaDeskSidebarUX(unittest.TestCase):
    def test_assets_are_registered_in_dependency_order(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn("almdina_desk_sidebar.css", manifest)
        self.assertIn("almdina_shortcut_presentation.js", manifest)
        self.assertIn("almdina_desk_sidebar_ux.js", manifest)
        self.assertLess(manifest.index("almdina_desk_theme.css"), manifest.index("almdina_desk_sidebar.css"))
        self.assertLess(manifest.index("shared_shell.js"), manifest.index("almdina_shortcut_presentation.js"))
        self.assertLess(
            manifest.index("almdina_shortcut_presentation.js"),
            manifest.index("almdina_workspace_home_ux.js"),
        )
        self.assertLess(manifest.index("almdina_workspace_home_ux.js"), manifest.index("almdina_desk_sidebar_ux.js"))

    def test_shortcut_presentation_is_shared_icon_catalog(self) -> None:
        source = PRESENTATION.read_text(encoding="utf-8")
        self.assertIn("AlmdinaShortcutPresentation", source)
        self.assertIn("SHORTCUT_PRESENTATION", source)
        self.assertIn("LABEL_ICON_ALIASES", source)
        self.assertIn('"الزبائن"', source)
        self.assertIn("metaForLabel", source)
        self.assertIn("iconForLabel", source)
        self.assertNotIn("frappe.call", source)

    def test_desk_sidebar_owner_is_presentation_only(self) -> None:
        source = SIDEBAR_JS.read_text(encoding="utf-8")
        self.assertIn("AlmdinaDeskSidebarUX", source)
        self.assertIn("patchBootSidebarIcons", source)
        self.assertIn("hookSidebarRender", source)
        self.assertNotIn("if (!sharedShellActive()) return;", source)
        self.assertIn("applySidebarIcons", source)
        self.assertIn("sidebar-expand.almdinaDeskSidebar", source)
        self.assertIn("AlmdinaShortcutPresentation", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("frm.save", source)

    def test_boot_session_projects_sidebar_icons(self) -> None:
        boot_source = (ROOT / "boot.py").read_text(encoding="utf-8")
        self.assertIn("apply_sidebar_icon_catalog", boot_source)
        css = SIDEBAR_CSS.read_text(encoding="utf-8")
        self.assertIn("body.almdina-shared-shell", css)
        self.assertIn(".body-sidebar-container:not(.expanded)", css)
        self.assertIn(".sidebar-item-label", css)
        self.assertIn("scrollbar-width: thin", css)
        self.assertIn("--alm-on-primary", css)
        self.assertIn(".sidebar-item-icon.text-ink-gray-7", css)

    def test_workspace_home_uses_shared_presentation_module(self) -> None:
        source = WORKSPACE_HOME.read_text(encoding="utf-8")
        self.assertIn("AlmdinaShortcutPresentation", source)
        self.assertIn("presentationApi", source)
        self.assertNotIn("const SHORTCUT_PRESENTATION", source)


if __name__ == "__main__":
    unittest.main()
