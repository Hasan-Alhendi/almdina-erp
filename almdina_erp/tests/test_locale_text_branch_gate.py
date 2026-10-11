from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"
# Removed in the DOM-replacement phase. Until then it is the only allowed caller.
DOM_REPLACEMENT = PUBLIC_JS / "arabic_operator_ui.js"


class TestActiveUiHasNoLanguageTextBranches(unittest.TestCase):
    def test_is_arabic_is_not_used_to_choose_interface_text(self) -> None:
        offenders = []
        for path in PUBLIC_JS.rglob("*.js"):
            if path.resolve() == DOM_REPLACEMENT.resolve():
                continue
            text = path.read_text(encoding="utf-8")
            if "function isArabic" in text or "isArabic()" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
