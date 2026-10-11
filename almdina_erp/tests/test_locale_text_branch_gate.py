from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"


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


if __name__ == "__main__":
    unittest.main()
