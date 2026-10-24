"""Catalog and locale gates.

The row rules match ``frappe.translate.get_translation_dict_from_file``:
two or three columns, and a third column is the context key ``source:context``.
The integration test calls that parser on a site. This module stays importable
without Frappe so the static workflow can run it.

Retired paths are excluded from the active-source scan only. Do not add an
active screen here to hide a new language branch.
"""

from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "translations" / "ar.csv"
PUBLIC_JS = ROOT / "public" / "js"
PLACEHOLDER = re.compile(r"\{[0-9]+\}")
DISAMBIGUATED_KEY = re.compile(r" \([23]\)$")
TRANSLATION_CALL = re.compile(
    r"""(?:__|\b_|\bt)\(\s*(["'])((?:\\.|[^\\])*?)\1"""
)
LOWERCASED_LANGUAGE_CODE = '.strip().lower().replace("_", "-")'

# Locale foundation only. Legacy services may still translate at import;
# this gate does not require that wider cleanup.
LOCALE_FOUNDATION = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "language_catalog.py",
    ROOT / "almdina_erp" / "infrastructure" / "printing" / "measurements_print_document.py",
    ROOT / "almdina_erp" / "application" / "security" / "workforce_management.py",
    ROOT / "almdina_erp" / "services" / "workforce_service.py",
)

# Historical or retired trees. Active DCO, DXF, workforce, shop floor, and
# print documents are not on this list.
RETIRED_SOURCE_PREFIXES = (
    "almdina_erp/patches/",
    "almdina_erp/almdina_erp/report/",
)

LOCALE_AWARE_DOCUMENTS = (
    ROOT / "almdina_erp" / "infrastructure" / "printing" / "measurements_print_document.py",
    ROOT / "almdina_erp" / "print_format" / "door_cutting_measurements" / "door_cutting_measurements.json",
    ROOT / "almdina_erp" / "print_format" / "door_cutting_plan_official" / "door_cutting_plan_official.json",
    ROOT / "almdina_erp" / "print_format" / "door_cutting_plan_production_a4" / "door_cutting_plan_production_a4.json",
)


def _catalog_rows() -> list[tuple[int, list[str]]]:
    with CATALOG.open(encoding="utf-8", newline="") as handle:
        return [
            (index, row)
            for index, row in enumerate(csv.reader(handle), start=1)
            if row and any(cell.strip() for cell in row)
        ]


def _translation_key(row: list[str]) -> str:
    if len(row) == 3 and row[2]:
        return row[0] + ":" + row[2]
    return row[0]


class TestTranslationCatalogGate(unittest.TestCase):
    def test_catalog_rows_match_the_frappe_parser_shape(self) -> None:
        invalid = [
            (index, len(row))
            for index, row in _catalog_rows()
            if len(row) not in (2, 3)
        ]
        self.assertEqual(invalid, [])

    def test_catalog_has_no_duplicate_keys(self) -> None:
        seen: dict[str, int] = {}
        duplicates = []
        for index, row in _catalog_rows():
            key = _translation_key(row)
            if key in seen:
                duplicates.append((key, seen[key], index))
            else:
                seen[key] = index
        self.assertEqual(duplicates, [])

    def test_placeholders_match_between_source_and_translation(self) -> None:
        mismatches = []
        for index, row in _catalog_rows():
            if len(row) < 2:
                continue
            if PLACEHOLDER.findall(row[0]) != PLACEHOLDER.findall(row[1]):
                mismatches.append(index)
        self.assertEqual(mismatches, [])

    def test_board_fit_messages_keep_commas_inside_the_translation_key(self) -> None:
        rows = {row[0]: row for _, row in _catalog_rows()}
        for message in (
            "Piece dimensions exceed the board, even after allowed rotation.",
            "Row {0}: Piece dimensions {1} × {2} cm do not fit the board {3} × {4} cm, even after allowed rotation.",
        ):
            with self.subTest(message=message):
                self.assertIn(message, rows)
                self.assertEqual(len(rows[message]), 2)
                self.assertRegex(rows[message][1], r"[\u0600-\u06ff]")

    def test_active_code_has_no_fixed_language_set(self) -> None:
        offenders = []
        for path in (ROOT / "almdina_erp").rglob("*.py"):
            relative = str(path.relative_to(ROOT))
            if any(relative.startswith(prefix) for prefix in RETIRED_SOURCE_PREFIXES):
                continue
            text = path.read_text(encoding="utf-8")
            if "SUPPORTED_LANGUAGES" in text:
                offenders.append(relative)
        self.assertEqual(offenders, [])

    def test_active_ui_has_no_hardcoded_language_options_or_dom_translation(self) -> None:
        offenders = []
        for path in PUBLIC_JS.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            relative = str(path.relative_to(ROOT.parent))
            if '["ar", "en"]' in text or "['ar', 'en']" in text:
                offenders.append(relative + ": options")
            if "function isArabic" in text or "isArabic()" in text:
                offenders.append(relative + ": isArabic")
            if "MutationObserver" in text and "node.nodeValue" in text:
                offenders.append(relative + ": dom-translation")
        self.assertEqual(offenders, [])

    def test_locale_aware_documents_do_not_force_arabic_rtl(self) -> None:
        for path in LOCALE_AWARE_DOCUMENTS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('lang="ar"', text, path.name)
            self.assertNotIn('dir="rtl"', text, path.name)

    def test_catalog_and_calls_do_not_use_synthetic_disambiguation_keys(self) -> None:
        catalog_offenders = [
            index
            for index, row in _catalog_rows()
            if DISAMBIGUATED_KEY.search(row[0].strip())
        ]
        self.assertEqual(catalog_offenders, [])

        call_offenders = []
        roots = (
            ROOT / "almdina_erp",
            ROOT / "public" / "js",
            ROOT / "almdina_erp" / "print_format",
        )
        for root in roots:
            for path in root.rglob("*"):
                if path.suffix not in {".py", ".js", ".json"}:
                    continue
                relative = str(path.relative_to(ROOT))
                if relative.startswith("almdina_erp/patches/"):
                    continue
                text = path.read_text(encoding="utf-8")
                for _quote, message in TRANSLATION_CALL.findall(text):
                    if DISAMBIGUATED_KEY.search(message.strip()):
                        call_offenders.append(relative + ": " + message)
        self.assertEqual(call_offenders, [])

    def test_locale_foundation_keeps_message_ids_until_the_request(self) -> None:
        for path in LOCALE_FOUNDATION:
            text = path.read_text(encoding="utf-8")
            module_level = [
                line.strip()
                for line in text.splitlines()
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*_\(", line)
            ]
            self.assertEqual(module_level, [], path.name)
            self.assertNotIn(LOWERCASED_LANGUAGE_CODE, text, path.name)

        service = (ROOT / "almdina_erp" / "services" / "workforce_service.py").read_text(encoding="utf-8")
        messages = service.split("_LANGUAGE_ERROR_MESSAGES = {", 1)[1].split("}", 1)[0]
        self.assertNotIn("_(", messages)
        self.assertIn('"The language code is invalid."', messages)

        catalog = (ROOT / "almdina_erp" / "infrastructure" / "frappe" / "language_catalog.py").read_text(
            encoding="utf-8"
        )
        stored = catalog.split("def stored_language_code(", 1)[1].split("def ", 1)[0]
        self.assertNotIn(".lower(", stored)
        document = (
            ROOT / "almdina_erp" / "infrastructure" / "printing" / "measurements_print_document.py"
        ).read_text(encoding="utf-8")
        locale = document.split("def document_locale(", 1)[1].split("def ", 1)[0]
        assignment = next(line for line in locale.splitlines() if line.strip().startswith("code ="))
        self.assertNotIn(".lower(", assignment)

    def test_inner_layers_do_not_translate_with_frappe(self) -> None:
        offenders = []
        for layer in ("domain", "application"):
            root = ROOT / "almdina_erp" / layer
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                relative = str(path.relative_to(ROOT))
                if "import frappe" in text or "frappe._(" in text or "from frappe import _" in text:
                    offenders.append(relative)
        self.assertEqual(offenders, [])

    def test_third_language_fixture_is_not_a_production_catalog(self) -> None:
        translations = ROOT / "translations"
        self.assertFalse((translations / "fr.csv").exists())
        self.assertFalse((translations / "tr.csv").exists())
        fixture = Path(__file__).resolve().parent / "fixtures" / "pseudo_locale_fr.json"
        self.assertTrue(fixture.exists())
        self.assertNotIn("fr.csv", fixture.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
