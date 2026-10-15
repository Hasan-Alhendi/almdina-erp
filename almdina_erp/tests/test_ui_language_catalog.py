from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.infrastructure.frappe.language_catalog import (
    present_enabled_languages,
)
from almdina_erp.almdina_erp.infrastructure.frappe.ui_language_catalog import (
    almdina_ui_languages,
    default_translations_directory,
    resolve_ui_language,
    translation_catalog_keys,
)


class _Catalog:
    def __init__(self, rows):
        self.rows = rows

    def enabled_languages(self):
        return present_enabled_languages(self.rows)


class TestUiLanguageCatalog(unittest.TestCase):
    def test_shipped_catalogs_are_arabic_only(self) -> None:
        directory = default_translations_directory()
        self.assertTrue((directory / "ar.csv").is_file())
        self.assertFalse((directory / "en.csv").is_file())
        self.assertEqual(translation_catalog_keys(), frozenset({"ar"}))

    def test_enabled_english_joins_existing_catalogs(self) -> None:
        catalog = _Catalog([
            {"language_code": "ar", "language_name": "العربية"},
            {"language_code": "en", "language_name": "English"},
            {"language_code": "fr", "language_name": "Français"},
        ])
        languages = almdina_ui_languages(catalog)
        self.assertEqual([language["code"] for language in languages], ["ar", "en"])
        arabic = languages[0]
        self.assertEqual(arabic["name"], "العربية")
        self.assertEqual(arabic["direction"], "rtl")
        self.assertEqual(languages[1]["direction"], "ltr")

    def test_temporary_catalog_file_adds_an_enabled_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ar.csv").write_text("Language,اللغة\n", encoding="utf-8")
            (root / "tr.csv").write_text("Language,Dil\n", encoding="utf-8")
            (root / "zu.csv").write_text("Language,Zulu\n", encoding="utf-8")
            catalog = _Catalog([
                {"language_code": "ar", "language_name": "العربية"},
                {"language_code": "en", "language_name": "English"},
                {"language_code": "tr", "language_name": "Türkçe"},
                {"language_code": "fr", "language_name": "Français"},
            ])
            codes = [
                language["code"]
                for language in almdina_ui_languages(catalog, root)
            ]
        self.assertEqual(codes, ["ar", "en", "tr"])

    def test_disabled_and_uncatalogued_languages_stay_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "zu.csv").write_text("Language,Zulu\n", encoding="utf-8")
            # fr is enabled and has no catalog file. zu has a file but is not
            # in the enabled catalog, so neither language is offered.
            enabled = _Catalog([
                {"language_code": "fr", "language_name": "Français"},
            ])
            self.assertEqual(almdina_ui_languages(enabled, root), [])

    def test_resolve_returns_the_catalog_code(self) -> None:
        languages = [
            {"code": "pt-BR", "name": "Português", "direction": "ltr"},
            {"code": "en", "name": "English", "direction": "ltr"},
        ]
        self.assertEqual(resolve_ui_language("PT_br", languages), "pt-BR")
        self.assertEqual(resolve_ui_language("en", languages), "en")
        self.assertIsNone(resolve_ui_language("fr", languages))
        self.assertIsNone(resolve_ui_language("  ", languages))
