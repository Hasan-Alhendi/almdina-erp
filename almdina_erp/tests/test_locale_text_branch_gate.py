from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"
LOCALE_JS = PUBLIC_JS / "almdina_locale.js"
PRINT_PRESENTER = (
    PUBLIC_JS
    / "door_cutting_order"
    / "printing"
    / "door_cutting_order_document_print_presenter.js"
)
NOTES_UI = (
    PUBLIC_JS / "notes" / "notes_panel.js",
    PUBLIC_JS / "notes" / "notes_dco_list_integration.js",
)
NESTED_TRANSLATION = re.compile(r"\bt\s*\(\s*__\s*\(")
STORED_VALUE_TRANSLATION = re.compile(r"(?:value|options)\s*:\s*(?:__|t)\s*\(")
ARABIC_TEXT = re.compile(r"[\u0600-\u06FF]")
# Stored quote phrases matched for compatibility. They are not displayed as UI.
PRINT_COMPATIBILITY_ARABIC = (
    "من القشاط الافتراضي",
    "يتضمن أطرافًا مخصصة",
)


class TestActiveUiHasNoLanguageTextBranches(unittest.TestCase):
    def test_is_arabic_is_not_used_to_choose_interface_text(self) -> None:
        offenders = []
        for path in PUBLIC_JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            if "function isArabic" in text or "isArabic()" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_dom_text_replacement_file_stays_removed(self) -> None:
        self.assertFalse((PUBLIC_JS / "arabic_operator_ui.js").exists())

    def test_javascript_does_not_wrap_translation_calls_or_stored_values(self) -> None:
        offenders = []
        for path in PUBLIC_JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            relative = str(path.relative_to(ROOT))
            if NESTED_TRANSLATION.search(text):
                offenders.append(relative + ": t(__())")
            if STORED_VALUE_TRANSLATION.search(text):
                offenders.append(relative + ": translated stored value")
        self.assertEqual(offenders, [])

    def test_locale_foundation_translates_inside_functions_and_keeps_official_codes(self) -> None:
        source = LOCALE_JS.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^(?:const|let|var)\s+\w+\s*=\s*__\(", source, re.M))
        official = source.split("function officialLanguageCode(", 1)[1].split("function ", 1)[0]
        self.assertNotIn("toLowerCase", official)
        self.assertNotIn('.toLowerCase().replace(/_/g, "-")', source)

    def test_browser_print_presenter_keeps_arabic_only_as_compatibility_values(self) -> None:
        leftovers = []
        for number, line in enumerate(PRINT_PRESENTER.read_text(encoding="utf-8").splitlines(), start=1):
            if not ARABIC_TEXT.search(line):
                continue
            visible = line
            for phrase in PRINT_COMPATIBILITY_ARABIC:
                visible = visible.replace(phrase, "")
            visible = visible.replace("،", "")
            if ARABIC_TEXT.search(visible):
                leftovers.append(f"{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_notes_ui_has_no_direct_arabic_literals(self) -> None:
        leftovers = []
        for path in NOTES_UI:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if ARABIC_TEXT.search(line):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_important_note_column_label_ignores_doctype_text(self) -> None:
        source = (PUBLIC_JS / "notes" / "notes_dco_list_integration.js").read_text(encoding="utf-8")
        self.assertNotIn("important.df.label ||", source)
        self.assertIn('label: __("Important note")', source)

    def test_workspace_navigation_visible_copy_uses_english_message_ids(self) -> None:
        home = (PUBLIC_JS / "almdina_workspace_home_ux.js").read_text(encoding="utf-8")
        title = home.split("const WORKSPACE_PAGE_TITLE", 1)[1].split("const ROOT_CLASS", 1)[0]
        sections = home.split("const SECTION_BY_BLOCK_ID", 1)[1].split("const SHORTCUT_BLOCK_TO_LINK", 1)[0]
        self.assertIsNone(ARABIC_TEXT.search(title))
        self.assertIsNone(ARABIC_TEXT.search(sections))
        self.assertIn("Factory management", title)
        self.assertIn("title:", sections)

        presentation = (PUBLIC_JS / "almdina_shortcut_presentation.js").read_text(encoding="utf-8")
        catalog = presentation.split("const SHORTCUT_BY_LINK_TO", 1)[1].split("const LABEL_TO_LINK_TO", 1)[0]
        compatibility = presentation.split("const LABEL_TO_LINK_TO", 1)[1].split(
            "const SHORTCUT_PRESENTATION", 1
        )[0]
        self.assertIsNone(ARABIC_TEXT.search(catalog))
        self.assertIn("label:", catalog)
        self.assertIsNotNone(ARABIC_TEXT.search(compatibility))

        shell = (PUBLIC_JS / "shared_shell.js").read_text(encoding="utf-8")
        self.assertIn('__("You do not have permission to access this section.")', shell)
        self.assertNotIn("لا تملك صلاحية الوصول إلى هذا القسم", shell)

    def test_special_shape_documentation_visible_copy_uses_english_message_ids(self) -> None:
        paths = (
            PUBLIC_JS / "special_shape_documentation" / "application" / "templates.js",
            PUBLIC_JS / "special_shape_documentation" / "presentation" / "workspace_shell.js",
            PUBLIC_JS / "special_shape_documentation" / "presentation" / "workspace_controller.js",
            PUBLIC_JS / "door_cutting_order" / "drawing" / "special_shape_facade.js",
            ROOT / "almdina_erp" / "page" / "door_drawing" / "door_drawing.js",
            ROOT / "almdina_erp" / "services" / "special_shape_workspace_service.py",
            ROOT / "almdina_erp" / "services" / "special_shape_drawing_validation_service.py",
        )
        leftovers = []
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if ARABIC_TEXT.search(line):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])

    def test_order_entry_visible_copy_uses_english_message_ids(self) -> None:
        paths = (
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "door_cutting_order_order_tab_layout_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "door_cutting_order_cutting_machine_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "door_cutting_order_whatsapp_delivery_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "measurements" / "door_cutting_order_measurement_actions_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "measurements" / "door_cutting_order_measurement_toolbar_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_edge_color_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_multi_edge_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_edge_profile_controls_ux.js",
            PUBLIC_JS / "door_cutting_order" / "order_entry" / "edge_banding" / "door_cutting_order_edge_profile_double_click_guard.js",
        )
        allowed = ("مشرحة", "لون القشاط")
        leftovers = []
        for path in paths:
            relative = path.relative_to(ROOT)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                visible = line
                for phrase in allowed:
                    visible = visible.replace(phrase, "")
                if ARABIC_TEXT.search(visible):
                    leftovers.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
