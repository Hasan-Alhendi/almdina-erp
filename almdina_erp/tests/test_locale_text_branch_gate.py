from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"
LOCALE_JS = PUBLIC_JS / "almdina_locale.js"
NESTED_TRANSLATION = re.compile(r"\bt\s*\(\s*__\s*\(")
STORED_VALUE_TRANSLATION = re.compile(r"(?:value|options)\s*:\s*(?:__|t)\s*\(")


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


if __name__ == "__main__":
    unittest.main()
